# Implementation Plan: Agent Hardening (Production-Grade Resilience)

**Branch**: `dev` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-agent-hardening/spec.md`

**Supporting**: [technical-design.md](./technical-design.md) · [ADR-024](../../docs/adr/ADR-024-retry-resilience-strategy.md) · [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) · [ADR-026](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md) · [learning-lessons/](../../docs/learning-lessons/)

## Summary

Harden the production agent along five auth-independent dimensions — reliability, **performance
(primary)**, safety/privacy, context sustainability, and observability — by modifying the
LangGraph **harness** (graph, nodes, state, runtime config) and the API edges. Latency is the
declared dominant bottleneck, so the performance user story (US2) is front-loaded. Delivery is
**incremental in small batches** (one user story, or one Quick Win within US2): each batch is
manually validated and **waits for explicit approval before being committed**. Every technical
decision becomes (or extends) an ADR; every learning becomes (or extends) a learning-lesson.

## Technical Context

**Language/Version**: Python 3.11 (agent) · Node.js 20 (API) · Next.js 14 (UI, untouched here)

**Primary Dependencies**: LangGraph v1.0+, LangChain, `langchain-openai` (agent); Express 4, `pg`
(API). New per ADR-024: `pybreaker`, `tenacity` (present), `p-retry`, `async-retry`. P5 adds
`structlog`. Persistence work uses the **already-deployed Redis** (`REDIS_URI`) and Postgres/Neon.

**Storage**: Postgres/Neon (durable: API data + LangGraph checkpoints) · Redis (ephemeral session
state + SSE streaming + candidate node-output cache). No new storage engines introduced.

**Testing**: pytest (70, agent) + Jest (39, API) against **real Postgres** — must stay green
(constitution II); new behavior ships with failing-first tests.

**Target Platform**: Linux containers on Render (managed LangGraph Server image + nginx edge).

**Project Type**: Polyglot web service (API + agent + UI + nginx gateway).

**Performance Goals** (from spec Success Criteria, baseline measured in Phase 0):
- SC-004: median text scheduling latency **−≥50%** vs baseline
- SC-006: critical-path durable writes **−≥80%** vs per-node baseline (recovery intact)
- SC-007: voice-path transcription+synthesis latency **−≥50%**
- SC-008: per-conversation model cost flat as history grows, ≤ baseline

**Constraints**: managed LangGraph Server limits checkpoint control (must verify what config it
exposes — see research); SSE streaming must keep working; user-facing errors pt-BR only; **no
authentication in scope** (Spec 006); ephemeral state must remain external (twelve-factor).

**Scale/Scope**: early production, single clinic, low concurrency. Five user stories, ~24 FRs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is ratified (v1.1.0). All six principles evaluated:

| Principle | Applies? | Status | Notes |
|-----------|----------|--------|-------|
| I. Layered Architecture | **Yes** | ✅ Pass | API retry lives in repositories/connection; correlation-id + structured logging are middleware/cross-cutting modules — no responsibility leaks across layers. Agent changes stay within `nodes/`, `graph.py`, `state.py`. |
| II. Test-First (TDD) with Real DB | **Yes** | ✅ **Strengthened** | This is a hardening feature — every batch ships failing-first tests; the 70 pytest + 39 Jest stay green (FR-023). Retry/guardrail/context behaviors are unit + integration tested against real Postgres. |
| III. Stateless Services via DI | **Yes** | ✅ Pass | Retry wraps existing singletons without changing their interfaces (ADR-012); correlation id flows via headers, not hidden state; ephemeral session state is externalized to Redis, not container memory. |
| IV. Observability & Cache Consistency | **Yes** | ✅ **Strengthened** | P5 (US5) *is* this principle: correlation id nginx→API→agent, structlog JSON, LangSmith trace linkage. Existing availability cache-after-commit invalidation retained verbatim. **B4's new agent-side node-output cache is scoped to write-stable lookups only** — availability/appointment reads are excluded or invalidated on write, so it never serves stale (analysis finding C1). |
| V. Simplicity & Minimal Abstraction | **Yes** | ✅ Pass | Reuse `tenacity`/`p-retry` (ecosystem standard, ADR-024) over custom; reuse the **existing** Redis for cache rather than new infra; prefer runtime checkpoint config over migrating off the managed server (P10 deferred); ADR-026 adopts the official `create_agent` middleware (`PIIMiddleware`/`SummarizationMiddleware`) instead of hand-rolled equivalents. New deps justified in Complexity Tracking. |
| VI. Security & Data Protection | **Yes** | ✅ **Strengthened** | P4 (US3) **fulfills the constitution's own mandate** that input guardrails land before processing unmoderated public input at scale. FR-016 keeps user PII out of logs; FR-024 keeps pt-BR errors with no stack/secret leakage; fail-closed/edge model unchanged. |

**Complexity Tracking**: New dependencies (`pybreaker`, `p-retry`, `async-retry`, `structlog`)
are minimal, ecosystem-standard, and justified by ADR-024/P5 — not new abstractions. No
unjustified violations. See table at the end.

**Result**: ✅ **PASS** — no gate violations. Several principles are *strengthened* by this feature.

## Delivery Model & Governance *(user-mandated)*

> These rules govern HOW the feature is built and are binding for `/speckit-tasks` and
> `/speckit-implement`.

1. **Small batches**: the unit of delivery is **one user story** — and, within the latency story
   (US2), **one Quick Win at a time**. No big-bang commits.
2. **Manual validation gate**: each batch is implemented, its tests run, and the result presented
   for **manual validation**. **No commit happens until the user explicitly approves.** (Overrides
   the session's usual auto-commit habit for this feature.)
3. **Latency first**: US2 (performance) is front-loaded — it is the declared dominant bottleneck.
   US1 (reliability) remains P1 by criticality and follows immediately; the manual gate decides
   ordering if they compete.
4. **Decision → ADR**: every technical decision either **extends an existing ADR** or **creates a
   new one** before/with the code that implements it. Decision→ADR map below.
5. **Learning → learning-lesson**: every interaction that produces a reusable learning creates a
   new file in `docs/learning-lessons/` or appends to an existing one.
6. **Harness changes are explicit**: edits to `agent/agent/graph.py`, `nodes/`, `state.py`,
   `langgraph.json`, or runtime/compile config are called out per batch (the "mexer no harness").

### Proposed batch sequence (each = one validated, approved commit)

| Batch | User story / item | Touches harness? | Primary artifacts |
|-------|-------------------|------------------|-------------------|
| **B0** | Baseline + harness investigation (Phase 0 research) | read-only probe | research.md, instrumentation |
| **B1** | US2 · QW-1 parallel tool calls | `llm_core.py` (bind) | ADR-027, lesson |
| **B2** | US2 · QW-4 reduce LLM rounds (prompt eng.) | `llm_core.py` (prompt) | ADR-027, lesson |
| **B3** | US2 · QW-3 checkpoint exit/selective | `graph.py`/`langgraph.json`/compile | extend ADR-025, lesson |
| **B4** | US2 · QW-7 Redis node-output cache | graph compile (`cache=`) | extend ADR-025, lesson |
| **B5** | US2 · QW-6 audio: spike Groq drop-in **vs** `gpt-4o-audio` multimodal (REST, no WebSocket, drops transcribe+tts) | `transcriber.py`/`tts.py`/`graph.py` | ADR-028, lesson |
| **B6** | US1 · P1 retry + circuit breaker | `llm_core`/`transcriber`/`api_client` + API | ADR-024 (impl) |
| **B7** | US3 · P4 guardrails: built-in `PIIMiddleware` + spike custom-vs-NeMo for injection/off-scope (per ADR-026) | middleware / new nodes | ADR-026, ADR-029, lesson |
| **B8** | US4 · P6 context manager (`SummarizationMiddleware`) | `context_manager.py` / middleware | ADR-026, ADR-030 |
| **B9** | US5 · P5 structured logs + correlation id | API middleware + agent `structlog` | ADR-031 |

> B0 must complete first (it makes SC-004/006/007 measurable and resolves whether the managed
> server exposes checkpoint/cache config — which gates B3/B4). B1–B2 are the lowest-risk, highest-
> impact latency wins and should land before the harder harness changes.

### Decision → ADR map

| Decision | ADR | Status |
|----------|-----|--------|
| Retry & circuit-breaker strategy | [ADR-024](../../docs/adr/ADR-024-retry-resilience-strategy.md) | exists (Proposed) |
| Checkpoint frequency + layered persistence (exit, Redis cache) | [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) | exists — **extend** with B3/B4 results |
| `create_agent` middleware vs manual nodes (P4/P6 approach) | [ADR-026](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md) | exists — adopt (revised) |
| Parallel tool calls + LLM-round reduction (latency) | **ADR-027** (new) | to create in B1/B2 |
| Audio model (Groq drop-in vs `gpt-4o-audio` multimodal) + multi-provider via LiteLLM | **ADR-028** (new) | to create in B5; LiteLLM/text deferred (R10) |
| Guardrails — built-in `PIIMiddleware` + custom/NeMo for injection/off-scope | **ADR-029** (new) | to create in B7 |
| Context-management strategy (window + summarization) | **ADR-030** (new) | to create in B8 |
| Structured logging + correlation-id propagation | **ADR-031** (new) | to create in B9 |

> ADR numbers 027–031 are reserved here; created when the batch's decision is finalized, not
> pre-stubbed empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-agent-hardening/
├── spec.md              # SDD requirements (done)
├── technical-design.md  # detailed gap analysis + Quick Wins (done)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output — per-batch validation guide
├── contracts/           # Phase 1 output — behavioral contracts
│   ├── agent-state.md
│   ├── resilience.md
│   ├── guardrail-decision.md
│   └── observability.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root — real paths touched)

```text
agent/
├── agent/
│   ├── graph.py             # B3/B4: checkpoint/cache config; B7: guardrail nodes wiring
│   ├── state.py             # B8: context fields (and MessagesState eval per ADR-026)
│   ├── langgraph.json       # B3: durability/runtime config if exposed
│   └── nodes/
│       ├── llm_core.py      # B1 parallel calls · B2 prompt · B6 retry+breaker
│       ├── transcriber.py   # B5 audio model · B6 retry
│       ├── api_client.py    # B6 retry (conn errors only)
│       ├── validate_input.py    # B7 (new, if manual path)
│       ├── validate_output.py   # B7 (new, if manual path)
│       └── context_manager.py   # B8 (new, if manual path)
└── tests/                   # failing-first tests per batch

api/
├── src/
│   ├── db/connection.js     # B6 startup retry (async-retry)
│   ├── repositories/*.js    # B6 query retry (p-retry)
│   └── middlewares/
│       ├── requestId.js     # B9 (new) correlation id
│       └── requestLogger.js # B9 structured JSON + correlation id
└── tests/

nginx/
└── nginx.conf.template      # B9: generate/propagate X-Request-ID

docs/
├── adr/                     # ADR-024..026 exist; 027..031 created per batch
└── learning-lessons/        # appended/created per batch
```

**Structure Decision**: Reuse the existing polyglot layout verbatim. No new top-level modules;
new agent nodes live under `agent/agent/nodes/`, new API cross-cutting concerns under
`api/src/middlewares/`, consistent with constitution I and the existing patterns.

## Complexity Tracking

| Violation / Addition | Why Needed | Simpler Alternative Rejected Because |
|----------------------|------------|--------------------------------------|
| New dep `pybreaker` (agent) | Circuit breaker for LLM fail-fast (ADR-024) — distinct from retry | Pure retry hangs every node when the provider is down; no stdlib breaker exists |
| New deps `p-retry` + `async-retry` (API) | Backoff retry for transient query/startup failures (ADR-024) | driver-native retry lacks exponential backoff + per-error-type control |
| New dep `structlog` (agent) | Structured JSON logs + correlation-id linkage (P5) | stdlib logging can't carry structured correlation context cleanly |
| `create_agent` middleware (P4/P6) | Less manual code for PII/summarization — official LangChain v1 path (ADR-026) | Hand-rolled validate/summarize nodes: more code, reimplements built-ins (manual nodes kept only as legacy fallback) |

All additions are ecosystem-standard, minimal, and tied to a specific FR/ADR — no speculative
abstraction. The largest churn (retry across call sites) is inherent to the resilience goal.
