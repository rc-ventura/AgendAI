# ADR-027: Latency Tactics — B1 Parallel Tool Calls + B2 Round Reduction

**Status**: Accepted  
**Date**: 2026-06-10  
**Spec**: 005-agent-hardening  
**Batch**: B1 (this record) → B2 (round reduction, to be appended after B2 commit)

---

## Context

Spec 005 SC-004 targets ≥50% median latency reduction for the text conversation path. Research R4 identified two quick wins that can be combined without architectural changes to the current `chat_with_llm + ToolNode` loop:

- **QW-1** (B1): Enable `parallel_tool_calls=True` on the LLM binding. When the model decides to call multiple tools, it issues them simultaneously and the `ToolNode` executes them concurrently. Without this flag, OpenAI defaults to sequential tool emission in some versions, adding one full round-trip per tool.
- **QW-4** (B2): Tighten the system prompt to reduce the number of LLM rounds from ~4 to ≤2. Each extra round adds ~600–900 ms.

These two tactics are additive and independent: B1 is a one-line change to `llm_core.py`; B2 is a prompt edit with no code path change.

---

## Decision

### B1 — Parallel tool calls (implemented)

```python
# agent/agent/nodes/llm_core.py
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2).bind_tools(
    ALL_TOOLS,
    parallel_tool_calls=True,   # ← QW-1
)
```

`parallel_tool_calls=True` is passed to the OpenAI API as a top-level parameter. When the model returns multiple tool-call objects in a single `AIMessage`, LangGraph's `ToolNode` executes them concurrently (asyncio gather). This eliminates sequential LLM → tool → LLM → tool chains for multi-step lookups that don't depend on each other (e.g., `buscar_horarios_disponiveis` + `buscar_paciente` in the same turn).

**Note**: `gpt-4o-mini` supports parallel function calling by default since late 2024. The flag makes the behavior explicit and survives future SDK/model upgrades that might change the default.

### B2 — Round reduction (to be completed)

System prompt optimisation will be documented in this ADR after B2's manual gate.

---

## Alternatives Considered

**A) Leave default (no `parallel_tool_calls`)**: Current behaviour before B1. Sequential per-tool latency. Rejected: meaningful latency cost with zero upside.

**B) Migrate to `create_agent` immediately for parallel calls**: `create_agent` (ADR-026) handles tool binding internally and respects parallel calling. Migration is B7; it would be premature here (adds B7 scope risk to a 1-line B1 fix). Rejected for B1.

**C) Pass `ChatOpenAI(model=..., parallel_tool_calls=True)` as constructor kwarg**: This sets the kwarg at the model level rather than the tool-binding level. Less explicit about the intent (it affects all model invocations, not just tool-bound ones). Rejected in favour of the `bind_tools` kwarg which is the canonical LangChain location.

---

## Consequences

- **Positive**: Multi-tool turns gain concurrency — expected latency improvement in turns where ≥2 independent tools are called simultaneously.
- **Positive**: Explicit flag documents intent; no silent regression if OpenAI changes the default.
- **Neutral**: Single-tool turns are unaffected (no overhead).
- **Neutral (B7 migration)**: When B7 replaces `bind_tools` with `create_agent`, the `ChatOpenAI` model object passed to `create_agent` must also be configured with `parallel_tool_calls=True` or the equivalent mechanism. ADR-026 will be updated at that time.
- **Risk (low)**: If a future tool-chain requires strict ordering (tool B must see tool A's output), parallel calls would be incorrect. No such dependency exists in the current 6-tool set. The `SYSTEM_PROMPT` already guards ordering logic (e.g., check email before booking).

---

## Verification

- `test_llm_bound_with_parallel_tool_calls` in `agent/tests/test_nodes.py` (T008) — passes after B1.
- Full suite: 63 pytest green.
- Live latency delta (baseline numbers TBD — system must be running for end-to-end measurement).
