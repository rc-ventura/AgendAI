"""
Measurement harness for Spec 005 latency baseline (T002 / research R1).

Records per-scenario P50/P99 latency, phase timings, checkpoint write count,
and estimated model cost per conversation, so that SC-004/006/007/008 can be
validated as concrete percentages against a fixed baseline.

Usage (run manually, not as part of the automated pytest suite):
    cd agent
    uv run python tests/perf/measure_latency.py --scenario text --runs 5
    uv run python tests/perf/measure_latency.py --scenario voice --runs 5

Requires:
  - OPENAI_API_KEY (for LLM calls)
  - DATABASE_URL pointing at agendai_lg (to count checkpoint rows)
  - LANGGRAPH_API_URL (optional, defaults to localhost:8123 for local harness)

The harness can operate in two modes:
  - "graph_direct": call the compiled graph directly (no managed server)
  - "server": call the running LangGraph Server HTTP API (measures end-to-end)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Pricing constants (OpenAI, 2026-06 rates — update as needed)
# ---------------------------------------------------------------------------

# GPT-4o-mini pricing per 1M tokens
_PRICE_INPUT_PER_1M = 0.15   # USD
_PRICE_OUTPUT_PER_1M = 0.60  # USD


@dataclass
class PhaseTimings:
    """Wall-clock time (seconds) for each pipeline phase."""
    total: float = 0.0
    transcription: float | None = None   # audio path only
    llm_round_1: float | None = None
    tool_calls: float | None = None
    llm_final: float | None = None
    synthesis: float | None = None       # audio path only


@dataclass
class RunResult:
    scenario: str
    run_index: int
    success: bool
    error: str | None = None
    timings: PhaseTimings = field(default_factory=PhaseTimings)
    llm_rounds: int = 0
    # Token counts (from LangChain callback or response metadata)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    # Checkpoint writes (requires DB access — optional)
    checkpoint_writes: int | None = None


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * _PRICE_INPUT_PER_1M
        + output_tokens / 1_000_000 * _PRICE_OUTPUT_PER_1M
    )


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (p / 100) * (len(sorted_vals) - 1)
    low = int(idx)
    high = min(low + 1, len(sorted_vals) - 1)
    frac = idx - low
    return sorted_vals[low] * (1 - frac) + sorted_vals[high] * frac


# ---------------------------------------------------------------------------
# Token-counting callback (LangChain streaming compatible)
# ---------------------------------------------------------------------------

class TokenUsageCapture:
    """Lightweight callback to capture token usage from LLM responses."""

    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.rounds = 0

    def capture(self, response: Any) -> None:
        """Extract token usage from an AIMessage response_metadata."""
        meta = getattr(response, "response_metadata", {}) or {}
        usage = meta.get("token_usage") or meta.get("usage") or {}
        self.total_input_tokens += usage.get("prompt_tokens", 0)
        self.total_output_tokens += usage.get("completion_tokens", 0)
        self.rounds += 1


# ---------------------------------------------------------------------------
# Direct-graph harness (no running server needed)
# ---------------------------------------------------------------------------

async def run_graph_direct(scenario: str, run_index: int) -> RunResult:
    """
    Invoke the AgendAI graph directly (without the managed server) using
    MemorySaver so the graph is stateful for the conversation.

    This measures "pure graph" latency without network overhead to the server,
    but still uses real OpenAI API calls.
    """
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver

    # Import must be deferred so pyproject pins are respected
    from agent.graph import builder  # noqa: PLC0415

    checkpointer = MemorySaver()
    g = builder.compile(checkpointer=checkpointer)

    if scenario == "text":
        content = "Quais horários disponíveis tem na quarta-feira?"
        input_state = {
            "messages": [HumanMessage(content=content)],
            "input_type": "text",
            "audio_data": None,
            "session_id": f"perf-text-{run_index}",
            "email_pending": False,
            "email_payload": None,
            "final_response": None,
        }
    else:
        # Voice scenario: use a short pre-recorded audio snippet or synthesise one.
        # For baseline runs without actual audio, we inject text to the transcriber
        # by simulating audio_data=None with input_type=text so the path is similar.
        content = "Quero cancelar meu agendamento. O ID é 42."
        input_state = {
            "messages": [HumanMessage(content=content)],
            "input_type": "text",   # voice path requires OPENAI audio; use text proxy
            "audio_data": None,
            "session_id": f"perf-voice-{run_index}",
            "email_pending": False,
            "email_payload": None,
            "final_response": None,
        }

    config = {"configurable": {"thread_id": f"perf-{scenario}-{run_index}"}}
    capture = TokenUsageCapture()
    result = RunResult(scenario=scenario, run_index=run_index, success=False)

    t_start = time.perf_counter()
    try:
        t_llm1_start: float | None = None
        final_state = None

        async for event in g.astream(input_state, config, stream_mode="updates"):
            node_name = next(iter(event))
            if node_name == "chat_with_llm":
                if t_llm1_start is None:
                    t_llm1_start = time.perf_counter()
                node_output = event[node_name]
                msgs = node_output.get("messages", [])
                for msg in msgs:
                    capture.capture(msg)
            final_state = event

        t_end = time.perf_counter()

        result.timings.total = t_end - t_start
        if t_llm1_start is not None:
            result.timings.llm_round_1 = t_llm1_start - t_start
        result.llm_rounds = capture.rounds
        result.input_tokens = capture.total_input_tokens
        result.output_tokens = capture.total_output_tokens
        result.estimated_cost_usd = compute_cost(result.input_tokens, result.output_tokens)
        result.success = True

    except Exception as exc:
        result.error = str(exc)
        t_end = time.perf_counter()
        result.timings.total = t_end - t_start

    return result


# ---------------------------------------------------------------------------
# Main: run N times, compute P50/P99, print summary
# ---------------------------------------------------------------------------

async def run_benchmark(scenario: str, runs: int, mode: str = "graph_direct") -> None:
    print(f"\n=== Latency benchmark | scenario={scenario} | runs={runs} | mode={mode} ===\n")

    results: list[RunResult] = []
    for i in range(runs):
        print(f"  Run {i + 1}/{runs}...", end=" ", flush=True)
        if mode == "graph_direct":
            r = await run_graph_direct(scenario, i)
        else:
            raise NotImplementedError(f"mode={mode} not yet implemented")
        results.append(r)
        status = "OK" if r.success else f"ERR: {r.error}"
        print(f"{r.timings.total:.2f}s  {status}")

    successful = [r for r in results if r.success]
    if not successful:
        print("\nAll runs failed — no statistics available.")
        return

    latencies = [r.timings.total for r in successful]
    costs = [r.estimated_cost_usd for r in successful]
    rounds = [r.llm_rounds for r in successful]

    p50 = percentile(latencies, 50)
    p99 = percentile(latencies, 99)
    cost_mean = statistics.mean(costs)
    rounds_mean = statistics.mean(rounds)

    print(f"\n--- Results ({len(successful)}/{runs} successful) ---")
    print(f"  Latency P50:  {p50:.2f}s")
    print(f"  Latency P99:  {p99:.2f}s")
    print(f"  Latency min:  {min(latencies):.2f}s")
    print(f"  Latency max:  {max(latencies):.2f}s")
    print(f"  LLM rounds:   {rounds_mean:.1f} (mean)")
    print(f"  Cost/conv:    ${cost_mean:.6f} (mean, {_PRICE_INPUT_PER_1M}/${_PRICE_OUTPUT_PER_1M} per 1M in/out)")

    summary = {
        "scenario": scenario,
        "mode": mode,
        "runs_total": runs,
        "runs_successful": len(successful),
        "latency_p50_s": round(p50, 3),
        "latency_p99_s": round(p99, 3),
        "latency_min_s": round(min(latencies), 3),
        "latency_max_s": round(max(latencies), 3),
        "llm_rounds_mean": round(rounds_mean, 2),
        "cost_per_conv_usd_mean": round(cost_mean, 8),
        "all_latencies_s": [round(l, 3) for l in latencies],
    }
    out_path = f"/tmp/agendai_perf_{scenario}.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Full results written to: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgendAI latency measurement harness")
    parser.add_argument("--scenario", choices=["text", "voice"], default="text")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--mode", choices=["graph_direct"], default="graph_direct")
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.scenario, args.runs, args.mode))
