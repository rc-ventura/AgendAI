# Phase 0 Research — Agent Hardening (Spec 005)

This resolves the open unknowns from the plan's Technical Context. Items that require a live
probe against the deployed managed LangGraph Server record the **investigation method** and the
**decision contingent on the outcome** — these are executed in Batch B0 before the dependent
batches.

---

## R1 — Latency baseline (resolves Performance Goals "baseline TBD")

**Decision**: Establish a baseline with a fixed measurement protocol before any optimization, so
SC-004/006/007 become concrete percentages against a recorded number.

**Protocol**:
- Scenario A (text): a standard scheduling request ("quais horários quarta?") → measure
  end-to-end wall time from request to final streamed token, and per-phase (input→LLM round 1,
  tool calls, LLM round N, final), via LangSmith trace timestamps.
- Scenario B (voice): an audio message → measure transcription, LLM, synthesis separately.
- Metric: capture median (P50) and P99 over ≥20 runs per scenario, from the Brazil→Oregon path.
- Record durable-write count per turn (checkpoint writes) from LangSmith/Postgres for SC-006.

**Rationale**: The spec deliberately deferred the number to planning. Without a recorded P50/P99
baseline and write-count, "−50%" / "−80%" are unfalsifiable. Baseline is committed as a learning
lesson (`latencia_baseline.md`) so later batches compare against a fixed reference.

**Alternatives considered**: Synthetic local timing (rejected — hides geographic + Neon latency
that dominate prod); guessing from prior session estimates (rejected — not reproducible).

---

## R2 — Does the managed LangGraph Server expose checkpoint durability/frequency? (gates B3)

**Decision (contingent)**: Prefer configuring `durability` / checkpoint-mode at graph compile or
runtime; if the managed image ignores it, fall back to selective-state writes within node design;
if neither works, defer to ADR-025's P10 (own runtime) — explicitly out of immediate scope.

**Investigation method (B0)**:
- Inspect the `langgraph build` image surface: does `graph.compile(...)` accept a `durability`
  arg in the pinned LangGraph version, and does the server honor it (vs injecting its own)?
- Probe with a 2-node test graph: count Postgres checkpoint rows per run under default vs
  `durability="exit"` (or the version's equivalent), via the `agendai_lg` database.
- Check LangGraph release notes for the pinned version's durability-mode support.

**Rationale**: This is the single highest-leverage latency item (~8s potential per ADR-025) and
the core "mexer no harness" question. Everything in B3 depends on the answer.

**Alternatives considered**: Reduce node count to cut writes (partial — limited by the audio
pipeline); move to `async` durability (smaller win, some crash-loss risk) — kept as fallback.

> **B0 OUTCOME (2026-06-09) — POSITIVE ✅**
>
> `graph.compile()` does **NOT** accept a `durability` parameter (not a compile-time config).
> However, the managed LangGraph Server API exposes `durability` as a **per-run request parameter**:
>
> - Values: `"sync"` (per-node, ~N writes), `"async"` (default — async per-node), `"exit"` (write only at run end)
> - Source: `langgraph_api/models/run.py` — `RunCreateDict.durability: str | None`
> - Default: `"async"` when `checkpoint_during` is `None` or `True` (i.e. every node)
> - To get exit-mode: client calls `client.runs.stream(..., durability="exit")`
>
> **Implementation path for B3**: Pass `durability="exit"` in the agent-ui-pro SDK call when creating
> runs. This does NOT require changing `graph.py`. Expected: ~80% reduction in checkpoint writes per
> turn (6-node graph → 1 write instead of 6+).

**Outcome → extend [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md).**

---

## R3 — Does the managed server support node-output cache (`cache=RedisCache`)? (gates B4)

**Decision (contingent)**: If `graph.compile(cache=...)` is honored by the managed server, use the
**already-deployed Redis** for node-output caching (ADR-025 Pattern D); otherwise skip B4 (no new
infra for a 0.5–2s win).

**Investigation method (B0)**:
- Confirm `RedisCache` (or `InMemoryCache`) is available in the pinned LangGraph and that the
  managed server respects a `cache=` passed at compile time.
- Validate cache key behavior with a repeated `buscar_horarios` call in one session.

**Rationale**: Zero-infra reuse of existing Redis; but only worth it if the managed server honors
the compile-time cache. Low priority within US2 (smallest win).

**Constitution IV constraint (cache consistency)**: the node-output cache MUST be scoped to
**write-stable lookups** (e.g., `buscar_pagamentos`). Availability/appointment reads
(`buscar_horarios`) MUST be excluded or invalidated on booking/cancel — caching them would risk
serving stale availability after an in-session write, violating "never serve stale". This bounds
the win to stable lookups, which is acceptable given B4 is the smallest latency item.

> **B0 OUTCOME (2026-06-09) — POSITIVE ✅**
>
> Static probe confirmed:
> - `from langgraph.cache.redis import RedisCache` — available in langgraph 1.2.0
> - `from langgraph.cache.memory import InMemoryCache` — available
> - `graph.compile(cache=cache)` stores the cache on the compiled `Pregel` object (`g.cache is cache`)
> - The managed server loads the pre-compiled `graph` object and **does NOT strip `cache`** (it only
>   warns about `checkpointer` and `store` — `cache` passes through unchanged)
> - `RedisCache(redis=<async_redis_client>, prefix="langgraph:cache:")` — constructor signature confirmed
>
> **Implementation path for B4**: Add `cache=RedisCache(redis_client)` to `builder.compile()` in
> `agent/agent/graph.py`. Wire `REDIS_URI` via an async Redis client at startup. Scope cache to
> write-stable tool nodes only (Constitution IV — `buscar_pagamentos`, static doctor/patient data);
> exclude `buscar_horarios` / appointment reads.

---

## R4 — B10-A: How to clear transient state in a LangGraph node (MEDIUM-01)

**Decision**: Return cleared fields (`None`) from the consuming node. LangGraph state is
immutable-update-based — returning `{"audio_data": None}` from a node merges that value into
state, replacing the bytes. No special LangGraph API is needed.

**Rationale**: The simplest correct approach. The node already returns a dict; adding two
`None` keys costs zero runtime overhead and removes the bytes from all downstream checkpoints.

**Alternatives considered**: Clearing in a dedicated "cleanup" node after `detect_input_type`
(rejected — more graph complexity for a one-liner fix); storing audio outside state (rejected —
violates the TypedDict contract without adding value).

---

## R5 — B10-B: How to propagate request_id into Python agent logs (HIGH-01)

**Decision**: `contextvars.ContextVar` set in `detect_input_type` (the first node), read by
`_JsonFormatter` at log-time. No third-party dependency added.

**Implementation details**:
- `detect_input_type` already runs first (directly after `START`) in all paths.
- LangGraph injects `config: RunnableConfig` into any node that declares it as a parameter —
  no graph wiring change required, only a parameter addition.
- `config["metadata"]["request_id"]` is the value the BFF already injects (ADR-031 B9).
- `ContextVar` default `"-"` ensures the formatter never raises `LookupError`.
- In asyncio, `ContextVar` values are inherited by the current task but NOT automatically
  copied to child tasks created with `asyncio.create_task`. LangGraph runs all nodes in the
  same asyncio event loop context (not in separate tasks), so the contextvar set by
  `detect_input_type` is visible to all subsequent nodes in the same invocation.

**Alternatives considered**:
- `LoggerAdapter` per module (rejected — requires refactoring every `logger = getLogger(...)` site).
- Adding `request_id` as a state field (rejected — observability concern leaking into business state).
- Structlog processors (rejected — we use stdlib logging; adding structlog was in scope originally but implementation used stdlib for simplicity).

---

## R6 — B10-C: Runtime test for checkpoint write count (HIGH-02)

**Decision**: `CountingCheckpointer(MemorySaver)` subclass that increments a counter in both
`put` and `aput`. Tests compile `builder` (not the module-level `graph`) with this checkpointer.

**Why not test `durability="exit"` directly**: `durability` is a per-run request parameter
processed by the managed LangGraph Server — it is not a graph compile option and cannot be
tested without the server. The unit test instead verifies the weaker but meaningful claim:
checkpointing is active (`put_count >= 1`) and bounded (`put_count <= N_NODES`).

**Boundary**: `N_NODES = 4` for the text path (input_detector → text_agent → process_text_results
→ END). With `durability="async"` (default, all nodes), the server writes once per super-step.
With `durability="exit"`, it writes once at the end. Both satisfy `1 ≤ put_count ≤ 4` with
a real MemorySaver, so the assertion is valid regardless of the server-side config.

**What the static test (`test_bff_route_handler_sets_durability_exit`) covers**: that the BFF
TypeScript code sends `durability: "exit"` in the request body — the correct server-side config.
The runtime test covers that the underlying checkpointing mechanism works and is bounded.

**Alternatives considered**: Full integration test against Docker Postgres (`agendai_lg`) with
write-count query (rejected — adds Docker dependency to pytest unit suite, slow, complex);
monkey-patching the module-level `graph`'s checkpointer (rejected — the module-level graph has
no checkpointer, patching it would be a no-op).

**Outcome → extend [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) (record the
cache-scoping constraint).**

---

## R4 — Parallel tool calls (QW-1, B1)

**Decision (updated for `create_agent` pattern)**: With `create_agent`, tool binding is internal
— tools are passed directly as `tools=[...]`. The parallel tool calls behavior is controlled by
the model's capabilities + whether the model is invoked with `parallel_tool_calls=True` in its
tool binding config. Since `create_agent` handles this internally, B1 implementation becomes:
verify that `create_agent` enables parallel tool calls by default (gpt-4o-mini supports it), and
if not, pass a `ChatOpenAI` instance configured with `parallel_tool_calls=True` as the `model` arg.

**Original decision**: Enable `parallel_tool_calls=True` on `ChatOpenAI(...).bind_tools(...)` in
`llm_core.py`, and ensure `tool_node` executes returned calls concurrently.

**Rationale**: `gpt-4o-mini` supports parallel function calling; LangGraph's `ToolNode` already
runs multiple tool calls concurrently. The change is a binding flag plus verification — lowest-risk
latency win (1–3s). Direct, no harness-runtime dependency.

**Alternatives considered**: Manual `asyncio.gather` of tool calls (rejected — `ToolNode` already
does this; don't reinvent). **Risk**: some prompts cause the model to over-parallelize dependent
calls — covered by the manual validation gate and tests.

**Outcome → ADR-027 (new): latency tactics — parallel calls + round reduction.**

---

## R5 — Reducing LLM rounds (QW-4, B2)

**Decision (updated for `create_agent` pattern)**: With `create_agent`, the system prompt is
passed as `system_prompt=SYSTEM_PROMPT` directly. The `llm_core.py` node is replaced by the
`create_agent` subgraph, so prompt changes happen in the `system_prompt` argument to `create_agent`.

**Original decision**: Tighten the system prompt so a standard scheduling request resolves in ~2 rounds
instead of ~4, by making the tool-use contract explicit (when to call which tool, what to gather
first) — building on the already-strong prompt in `llm_core.py`.

**Rationale**: Each round adds 0.8–2s; halving rounds is the largest single latency lever (5–7s),
zero infra. The current prompt already enforces identity/PII rules; round reduction extends it.

**Alternatives considered**: Few-shot examples (rejected first pass — adds input tokens/cost,
conflicts with SC-008); fine-tuning (rejected — out of scope, cost). Measured against R1 baseline.

**Outcome → ADR-027 (new).**

---

## R6 — `create_agent` + middleware: adopt (CORRECTED — no stability gate)

**Decision**: Adopt `create_agent` + middleware as the standard implementation path for P1/P4/P6.
It is the **official, stable** way to build agents in LangChain v1.

> **Correction (2026-06-09)**: an earlier version of this item (and ADR-026) claimed
> `create_agent` "was removed in v1.1.0 without notice" and built a stability gate on it. **That
> was false** — primary-source check shows `create_agent` is the recommended method and v1.1
> *expands* it; the "removed" report was a user's stale-venv error, debunked by the community. The
> gate is dropped, replaced by normal engineering prudence.

**Remaining checks (normal prudence, not a gate)**: pin `langchain`/`langgraph` versions; verify
`from langchain.agents import create_agent` and `PIIMiddleware`/`SummarizationMiddleware`/
`ModelRetryMiddleware` import in the pinned version; confirm the managed LangGraph Server accepts
the `create_agent` graph as a subgraph (integration check); keep tests green.

> **T001 OUTCOME (2026-06-09) — CORREÇÃO FINAL ✅**
>
> Probe revelou que o pacote `langchain` base **não estava instalado** — apenas `langchain-core`.
> São dois pacotes PyPI distintos (`langchain` ≠ `langchain-core`). Após instalar `langchain==1.3.1`:
>
> - `from langchain.agents import create_agent` → **OK** ✅
> - `from langchain.agents.middleware import PIIMiddleware` → **OK** ✅
> - `from langchain.agents.middleware import SummarizationMiddleware` → **OK** ✅
> - `from langchain.agents.middleware import ModelRetryMiddleware` → **OK** ✅
> - `from langchain.agents.middleware import LLMToolSelectorMiddleware` → **OK** ✅
> - `from langchain.agents.middleware import HumanInTheLoopMiddleware` → **OK** ✅
>
> **`create_agent` aceita** (verificado): `model` (string `"openai:gpt-4o-mini"` OU `BaseChatModel`),
> `tools`, `system_prompt`, `middleware=[]`, `cache=BaseCache`. Sem `bind_tools` manual —
> tool binding é interno.
>
> **Pacote adicionado ao projeto**: `langchain>=1.0` em `agent/pyproject.toml`.
> **Lição de processo**: `langchain-core` e `langchain` são PyPI packages distintos. Sempre instalar
> e testar os imports no ambiente correto antes de documentar disponibilidade.

**Outcome → ADR-026 (3ª revisão — correta): `create_agent` + middleware é o caminho padrão. ADR-029/030
para a configuração específica dos guardrails/context middleware.**

---

## R7 — Structured logging + correlation-id propagation (P5, B9)

**Decision**: Generate `X-Request-ID` at nginx (or API if absent), propagate via header to API and
agent; API logs JSON with the id; agent uses `structlog` JSON and attaches the id to LangSmith run
metadata so a trace is findable by correlation id.

**Rationale**: Matches constitution IV and the existing nginx/API topology. `structlog` is the
standard structured-logging choice for Python; nginx can emit/forward a request id with existing
directives.

**Open question (B0/B9)**: Can the agent read the inbound `X-Request-ID` through the managed
server's request handling, or must it be threaded via run metadata from the UI/SDK? Resolve by
inspecting how the SDK passes metadata to `/runs`.

**Alternatives considered**: OpenTelemetry full tracing (rejected for now — heavier than needed at
this scale; LangSmith already provides agent tracing). 

**Outcome → ADR-031 (new).**

---

## R8 — Audio model evaluation (QW-6, B5) — REVISED after research

> **User was right (and I was wrong)**: "multimodal/realtime doesn't necessarily need WebSocket —
> maybe just adjust the call; a realtime/multimodal version can drop transcribe and maybe TTS."
> Research confirms a **REST multimodal path that needs no WebSocket**.

**Three distinct paths (not just Groq):**

| Path | Transport | Eliminates | Latency | Cost | Architecture change |
|------|-----------|-----------|---------|------|---------------------|
| **(a) Groq Whisper drop-in** | REST | nothing (still Whisper→LLM→TTS) | STT ~0.3s (10× faster) | $0.111/h audio | none — swap `transcriber.py` provider |
| **(b) `gpt-4o-audio-preview` multimodal** | **REST (no WebSocket)** | **`transcriber.py` AND `tts.py`** | single call, slower than realtime but fine for async | ~$0.06/min in, ~$0.24/min out (`mini-audio` cheaper) | **simplifies graph** — 2 nodes → 0 |
| **(c) GPT-4o Realtime** | WebSocket/WebRTC | transcribe + TTS | lowest (streaming, full-duplex) | same audio pricing | **biggest** — replaces SSE harness |

**Key correction**: WebSocket is required **only** for path (c) Realtime (true full-duplex
conversation). Path (b) — `gpt-4o-audio-preview` / `gpt-4o-mini-audio-preview` in the **Chat
Completions REST API** — takes base64 audio in and returns audio out in a single normal call,
**removing both the Whisper transcription node and the TTS node**. AgendAI's voice flow is
asynchronous (record → answer), not full-duplex, so path (b) fits without WebSocket.

**Decision (revised, spike in B5)**: benchmark **(a) vs (b)**:
- (a) is the safest minimal win (provider swap, keeps the pipeline).
- (b) is the bigger architectural simplification (deletes 2 nodes, one provider does STT+LLM+TTS)
  — evaluate latency and pt-BR quality before committing. (c) Realtime stays deferred (architecture).

**Alternatives considered**: keep `whisper-1` + `tts-1` (slowest); Gemini Live multimodal
(provider switch — see R10). Transcription/synthesis quality in pt-BR is a hard gate before any swap.

**Outcome → ADR-028 (new): audio model selection — Groq drop-in vs gpt-4o-audio multimodal.**

---

## R10 — Multi-provider abstraction via LiteLLM (QW-6 text, B-future)

> **User raised it**: "using any non-OpenAI model probably needs LiteLLM with an API router."

**Decision (research recorded, not yet scheduled)**: if/when we move off OpenAI for the **text**
LLM (Nemotron, Grok, Gemini — QW-6 text table in technical-design), route through **LiteLLM**
rather than swapping SDKs per provider.

**Findings**:
- **LiteLLM** = unified gateway to 100+ providers in OpenAI format, with cost tracking, fallbacks,
  load-balancing, caching ([BerriAI/litellm](https://github.com/BerriAI/litellm/)).
- **LangChain integration is first-party**: `ChatLiteLLM` (drop-in for `ChatOpenAI`) and
  **`ChatLiteLLMRouter`** (adds load-balancing + fallbacks across providers) via the
  `langchain-litellm` package ([LangChain LiteLLM docs](https://docs.langchain.com/oss/python/integrations/chat/litellm)).
- **Two deployment shapes**: (i) **SDK** — replace `ChatOpenAI` with `ChatLiteLLM` in
  `llm_core.py` (minimal); (ii) **Proxy** — a self-hosted FastAPI gateway exposing
  `/chat/completions`, `/audio/speech`, `/audio/transcriptions` with virtual keys/budgets/fallbacks
  (heavier, but central control + observability).

**Rationale**: keeps tool-calling reliability as the hard gate while making provider swaps a config
change, not a rewrite. The router's fallback also complements P1 resilience (provider outage →
fallback model).

**Alternatives considered**: per-provider LangChain classes (`ChatGroq`, `ChatGoogleGenerativeAI`,
etc.) — fine for a single swap, but no unified fallback/cost layer; OpenRouter (similar idea,
hosted, less self-host control).

**Outcome → ADR-028 or a new ADR when a non-OpenAI text model is actually chosen (deferred — not
in the front-loaded latency batches).**

---

## R9 — Guardrails approach (P4, B7) — REVISED after research

> **User was right**: before building anything custom, check LangChain's built-in guardrails.
> Research finding ([LangChain Guardrails docs](https://docs.langchain.com/oss/python/langchain/guardrails)):
> the framework ships some guardrails built-in and explicitly leaves others to custom middleware.

**What is built-in (do NOT reinvent):**
- **`PIIMiddleware`** — detects PII (email, credit card, IP, MAC, URL) with strategies
  `redact` / `mask` / `hash` / `block`, operating on **input, output, and tool results**. Directly
  covers FR-014/016 (PII redaction + keep PII out of logs). HIPAA-relevant.
- **`HumanInTheLoopMiddleware`** — human approval before sensitive ops (this is Spec 007's HITL,
  not P4, but confirms the middleware path).
- Also relevant from the same family: `SummarizationMiddleware` (P6/B8), `ModelRetryMiddleware`
  (P1/B6), `LLMToolSelectorMiddleware` (latency — fewer tools per call).

**What is NOT built-in (needs custom or external):**
- **Prompt injection**, **jailbreak**, **off-topic/off-scope refusal** are *not* shipped by
  LangChain — they require either a custom middleware (deterministic regex/term lists, or a
  model-based check) **or** an external framework.
- **External option**: **NVIDIA NeMo Guardrails** has a documented LangChain *agent middleware*
  integration and covers injection/jailbreak/topical rails out of the box.

**Decision (revised, still a spike in B7)**:
1. PII (FR-014/016) → use **`PIIMiddleware`** built-in. No custom regex for PII.
2. Off-scope + prompt-injection (FR-013, FR-011) → spike **custom middleware vs NeMo Guardrails**
   in B7 and pick based on accuracy on a pt-BR test corpus + footprint. The existing system prompt
   already hardens injection at the model layer; this adds a deterministic layer on top.
3. This collapses into the **ADR-026 gate**: if the middleware stack is stable, P4 is *mostly*
   built-in (PII) + one custom/NeMo middleware (injection/off-scope) — far less manual code than
   the originally-planned `validate_input`/`validate_output` nodes.

**Alternatives considered**: hand-rolled `validate_input`/`validate_output` nodes (now the
*fallback*, not the default — built-in PIIMiddleware supersedes the PII part); AWS Bedrock
Guardrails (deferred — Phase 3, managed); LLM-as-judge output check (deferred — adds a round,
conflicts with latency goal).

**Outcome → ADR-029 (new): guardrails design — built-in PIIMiddleware + custom/NeMo for
injection/off-scope; cross-references ADR-026.**

---

## Summary of contingent gates

| Research | Gates batch | Resolved by | Feeds ADR |
|----------|-------------|-------------|-----------|
| R1 baseline | all US2 SCs | B0 probe + lesson | — (lesson) |
| R2 durability mode | B3 | B0 probe | ADR-025 extend |
| R3 node cache | B4 | B0 probe | ADR-025 extend |
| R4 parallel calls | B1 | direct | ADR-027 |
| R5 round reduction | B2 | direct + R1 | ADR-027 |
| R6 middleware gate | B7/B8 | version check | ADR-026 |
| R7 correlation id | B9 | SDK metadata probe | ADR-031 |
| R8 audio model | B5 | benchmark Groq vs gpt-4o-audio | ADR-028 |
| R9 guardrails | B7 | built-in PIIMiddleware + spike injection/off-scope | ADR-029 |
| R10 multi-provider (LiteLLM) | deferred | recorded; decide when off-OpenAI | ADR-028/new |

All NEEDS CLARIFICATION are either resolved (R4/R5 — direct decisions; R8/R9/R10 — research
done, now **spike-before-commit** with informed options) or assigned a B0 investigation method
with a contingent decision (R1/R2/R3/R6/R7). No blocking ambiguity remains.

> **Research-before-implement note** (per user): R8 (Groq drop-in vs gpt-4o-audio multimodal
> vs Realtime), R9 (built-in vs NeMo vs custom for injection/off-scope), and R10 (LiteLLM SDK vs
> proxy) are each resolved to a small set of options with a spike step in their batch — no
> single solution is locked in before the comparative spike.
