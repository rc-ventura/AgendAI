# Tasks: Agent Hardening (Production-Grade Resilience)

**Input**: Design documents from `/specs/005-agent-hardening/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [technical-design.md](./technical-design.md)

**Tests**: INCLUDED — Constitution Principle II (Test-First with Real DB) is **NON-NEGOTIABLE**, and FR-023 requires failing-first tests with the 70 pytest + 39 Jest suites staying green.

**Organization**: Tasks follow the plan's **user-mandated batch sequence (B0–B9)**, latency-first. Each batch maps to a user story label and ends in a **manual-approval gate** — per the Delivery Model, *no commit happens until the user explicitly approves*.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story (US1 reliability, US2 performance, US3 safety, US4 context, US5 observability)

## ⚠️ Governance (binding — from plan.md)

1. **One batch = one commit**, only after manual validation + **explicit user approval**.
2. **Latency first**: US2 (B1–B5) front-loaded; US1 reliability follows (P1-critical).
3. **Decision → ADR**: each batch creates/extends an ADR before/with its commit.
4. **Learning → learning-lesson**: each batch creates/appends a `docs/learning-lessons/` file.
5. **Tests failing-first**, then green; 70 pytest + 39 Jest never regress.

## Path Conventions

Polyglot: agent at `agent/agent/`, agent tests `agent/tests/`, API at `api/src/`, API tests `api/tests/`, gateway `nginx/`, docs `docs/adr|learning-lessons/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pin versions, build the measurement harness, confirm green baseline.

- [x] T001 [P] Pin & verify `langchain`/`langgraph` versions in `agent/pyproject.toml`; confirm `from langchain.agents import create_agent` and `PIIMiddleware`/`SummarizationMiddleware`/`ModelRetryMiddleware` import in the pinned version — **langchain==1.3.1 instalado; todos os imports OK; `langchain` ≠ `langchain-core` (pacotes PyPI distintos)**
- [x] T002 [P] Create a measurement harness `agent/tests/perf/measure_latency.py` capturing P50/P99 end-to-end + per-phase timings, durable checkpoint-write count per turn, **and token/model-cost per conversation** (research R1 protocol; enables SC-004/006/008)
- [x] T003 Confirm green baseline: run `cd agent && uv run pytest` (62 — actual count) and `cd api && npm test` (39 — needs Docker/Postgres); record pass

**Checkpoint**: tooling ready; suites green.

---

## Phase 2: Foundational — Batch B0 (Baseline + Harness Probe)

**Purpose**: Make SC-004/006/007 measurable and resolve whether the managed LangGraph Server exposes the checkpoint/cache config that gates B3/B4. **Read-only — no production code committed in B0.**

**⚠️ CRITICAL**: B3 depends on T005; B4 depends on T006; all US2 latency validation depends on T004.

- [x] T004 Measure baseline (text + voice scenarios, ≥20 runs each): latency, checkpoint writes/turn, **and token/model-cost per conversation** via the T002 harness + LangSmith; record in new `docs/learning-lessons/latencia_baseline.md` — **structure created; live numbers need system running**
- [x] T005 Probe: managed server DOES expose `durability` as per-run API param (`"sync"/"async"/"exit"`); default `"async"` (per-node). B3 = pass `durability="exit"` in SDK call (NOT a compile param). Recorded in research.md R2.
- [x] T006 Probe: `graph.compile(cache=RedisCache(...))` IS honored by managed server (`cache` attr preserved on Pregel; server only strips `checkpointer`/`store`). Recorded in research.md R3.
- [x] T007 Present B0 findings (baseline numbers + R2/R3 answers) for **manual validation**; on approval commit B0 docs (no production code)

**Checkpoint**: baseline recorded; harness capabilities known; B1–B5 can proceed informed.

---

## Phase 3: User Story 2 — Performance / Latency (Priority: front-loaded) 🎯 First delivery

**Goal**: Responses feel fast and fluid; ≥50% median latency reduction (SC-004), ≥80% fewer critical-path durable writes (SC-006), ≥50% audio latency reduction (SC-007), flat per-conversation cost (SC-008).

**Independent Test**: Re-run the T002 harness after each batch and compare to the T004 baseline; verify no multi-second stalls and unchanged correctness.

### Batch B1 — Parallel tool calls (QW-1)

- [x] T008 [P] [US2] Failing-first test in `agent/tests/test_nodes.py`: assert the LLM binds with `parallel_tool_calls=True` and multiple independent tool calls execute concurrently
- [x] T009 [US2] Enable `parallel_tool_calls=True` on `ChatOpenAI(...).bind_tools(...)` in `agent/agent/nodes/llm_core.py`; confirm `ToolNode` runs returned calls concurrently
- [ ] T010 [US2] Measure latency vs T004 baseline; create `docs/adr/ADR-027-latency-tactics.md` (parallel calls + round reduction) and a learning-lesson; **manual gate → commit on approval**

### Batch B2 — Reduce LLM rounds (QW-4)

- [x] T011 [P] [US2] Failing-first test in `agent/tests/test_graph.py`: a standard scheduling request resolves in ≤2 LLM rounds (count AIMessage tool-call cycles)
- [x] T012 [US2] Tighten the system prompt in `agent/agent/nodes/llm_core.py` to cut rounds 4→2 without weakening identity/PII/email-gate rules
- [ ] T013 [US2] Validate rounds + correctness (email gate, pt-BR) vs baseline; update `ADR-027` + learning-lesson; **manual gate → commit on approval**

### Batch B3 — Checkpoint exit/selective (QW-3) — *gated by T005/R2*

- [ ] T014 [US2] If R2 positive: configure durability/checkpoint-exit at graph compile or `agent/langgraph.json` so durable state is written at turn boundaries, not per node (FR-009)
- [ ] T015 [P] [US2] Test in `agent/tests/test_graph.py`: checkpoint writes/turn drop ≥80% (SC-006) and a conversation still resumes after restart
- [ ] T016 [US2] Validate SC-006 + resume + no email duplication; **extend** `docs/adr/ADR-025-langgraph-checkpoint-strategy.md` with the result + learning-lesson; **manual gate → commit on approval**

### Batch B4 — Redis node-output cache (QW-7) — *gated by T006/R3*

> **Constitution IV (cache consistency) — C1 fix**: availability/appointment reads change on write,
> so they MUST NOT be served stale. Scope the cache to **write-stable lookups only** (e.g.,
> `buscar_pagamentos`, static doctor data). `buscar_horarios`/appointment reads are either excluded
> from the cache OR invalidated on `criar_agendamento`/`cancelar_agendamento`.

- [ ] T017 [US2] If R3 positive: enable `graph.compile(cache=RedisCache(...))` using `REDIS_URI` in `agent/agent/graph.py` (FR-010/011), **scoped to write-stable lookups only**; exclude `buscar_horarios`/appointment reads from caching, or invalidate them on booking/cancel (Constitution IV — never serve stale). Else skip batch and record why
- [ ] T018 [P] [US2] Tests: (a) a repeated **write-stable** lookup (`buscar_pagamentos`) in one session is served from cache (no re-exec, unchanged result); (b) **cache-consistency guard** — after an in-session booking, a subsequent availability read is NOT served stale
- [ ] T019 [US2] Validate cache hit + **stale-safety** + correctness; **extend** `ADR-025` (record the Constitution IV scoping constraint) + learning-lesson; **manual gate → commit on approval**

### Batch B5 — Audio model (QW-6)

- [ ] T020 [US2] Spike: benchmark **Groq Whisper drop-in** vs **`gpt-4o-audio-preview` multimodal (REST, no WebSocket)** on latency + pt-BR quality; record in new `docs/adr/ADR-028-audio-model.md` + update learning-lesson `modelos_audio_multimodal_litellm.md`
- [ ] T021 [US2] Implement the chosen path in `agent/agent/nodes/transcriber.py` (and, if multimodal, remove `tts.py`/`transcribe` nodes and rewire `agent/agent/graph.py`)
- [ ] T022 [P] [US2] Test: voice-path latency meets SC-007 (−≥50%) and transcription correctness holds on a fixed audio set
- [ ] T023 [US2] Validate SC-007; finalize `ADR-028` + learning-lesson; **manual gate → commit on approval**

**Checkpoint**: latency targets demonstrably met vs baseline; US2 independently validated.

---

## Phase 4: User Story 1 — Reliability (Priority: P1-critical) — Batch B6

**Goal**: No patient message silently dropped on transient failure; clear pt-BR fail-fast when a dependency is genuinely down (FR-001..006).

**Independent Test**: The 5 outcomes in `contracts/resilience.md` (transient masked; breaker opens ≤1s; cold-start succeeds; 409 not retried; suites green).

- [ ] T024 [P] [US1] Failing-first tests in `agent/tests/test_nodes.py` + `api/tests/`: transient retry is masked, breaker opens after 3 fails, 4xx/409 is NOT retried, startup tolerates slow Postgres, **a retry around `email_sender` produces exactly one email (FR-006, no duplicate side effect)**, and **user-facing errors are pt-BR with no stack-trace/secret leakage (FR-024)** (per `contracts/resilience.md`)
- [ ] T025 [P] [US1] Add deps: `pybreaker` to `agent/pyproject.toml`; `p-retry` + `async-retry` to `api/package.json`
- [ ] T026 [US1] `agent/agent/nodes/llm_core.py`: `tenacity` retry (3×, exp) + `pybreaker` circuit breaker (fail_max=3, reset 30s) on the OpenAI call (ADR-024)
- [ ] T027 [P] [US1] `agent/agent/nodes/transcriber.py`: `tenacity` retry (3×) on Whisper
- [ ] T028 [P] [US1] `agent/agent/api_client.py`: `tenacity` retry on `httpx.ConnectError`/`TimeoutException` only — never on 4xx
- [ ] T029 [P] [US1] `api/src/db/connection.js`: `async-retry` startup (5×, ≤30s), bail on missing `DATABASE_URL`
- [ ] T030 [P] [US1] `api/src/repositories/*.js`: `p-retry` on transient query errors only (not constraint/4xx)
- [ ] T031 [US1] Validate the resilience contract; add an implementation note to `ADR-024` + learning-lesson; **manual gate → commit on approval**

**Checkpoint**: reliability contract green; US1 independently validated.

---

## Phase 5: User Story 3 — Safety & Privacy (Priority: P2) — Batch B7

**Goal**: Injection blocked, off-scope refused (pt-BR), PII redacted and never logged, no cross-patient leakage (FR-011..017). Introduces the `create_agent` + middleware scaffold (ADR-026).

**Independent Test**: The 5 outcomes in `contracts/guardrail-decision.md` (injection blocked pre-LLM, off-scope refused, CPF absent from logs, output redacted, corpus 100%/0).

- [ ] T032 [US3] Adopt `MessagesState` base for `AgendAIState` in `agent/agent/state.py` (additive — keep all existing fields; ADR-026); ensure 70 pytest stay green
- [ ] T033 [US3] Introduce `create_agent` scaffold wrapping the chat+tools loop as a subgraph in `agent/agent/graph.py`, preserving the audio/email/detect nodes around it (ADR-026); suites green
- [ ] T034 [P] [US3] Failing-first tests in `agent/tests/`: guardrail-decision contract — injection blocked before LLM, off-scope pt-BR refusal, PII not in logs, output redacted (per `contracts/guardrail-decision.md`)
- [ ] T035 [US3] Add `PIIMiddleware` (redact/block; input + output + tool results) to the agent — FR-014/016
- [ ] T036 [US3] Spike custom middleware vs **NeMo Guardrails** for injection/off-scope on a pt-BR corpus; implement the chosen one; record in new `docs/adr/ADR-029-guardrails.md` + learning-lesson `guardrails_langchain_middleware.md`
- [ ] T037 [US3] Validate guardrail contract (SC-009/010); finalize `ADR-029`; **manual gate → commit on approval**

**Checkpoint**: guardrail contract green; US3 independently validated.

---

## Phase 6: User Story 4 — Context Sustainability (Priority: P3) — Batch B8

**Goal**: Long conversations stay coherent and within the model limit; critical facts preserved (FR-016/017). Builds on the B7 `create_agent` scaffold.

**Independent Test**: A 20+ turn conversation: no context-limit error, key facts retained, latency stable (SC-011).

- [ ] T038 [P] [US4] Failing-first test in `agent/tests/`: a 20+ turn conversation stays within the context limit and retains critical facts (booking/cancellation/preference)
- [ ] T039 [US4] Add `SummarizationMiddleware` (token threshold) to the `create_agent` config; add `context_summary` field to state if needed (`agent/agent/state.py`) — FR-016/017
- [ ] T040 [US4] Validate SC-011 (no overflow, facts retained, latency stable) **and SC-008 (per-conversation model cost stays flat as history grows, ≤ baseline — via the T002 harness)**; create `docs/adr/ADR-030-context-management.md` + learning-lesson; **manual gate → commit on approval**

**Checkpoint**: long-conversation behavior validated; US4 independently validated.

---

## Phase 7: User Story 5 — Observability (Priority: P3) — Batch B9

**Goal**: One correlation id links nginx→API→agent and the LangSmith trace; structured logs; no PII in logs (FR-018..020).

**Independent Test**: The 3 outcomes in `contracts/observability.md` (one id across services, searchable < 5 min, id on error lines).

- [ ] T041 [P] [US5] Failing-first tests in `api/tests/`: one `request_id` propagates across services and appears on error log lines (per `contracts/observability.md`)
- [ ] T042 [US5] `nginx/nginx.conf.template`: generate/propagate `X-Request-ID` to upstreams
- [ ] T043 [P] [US5] New `api/src/middlewares/requestId.js`: accept inbound `X-Request-ID` or generate one; expose on `req`
- [ ] T044 [US5] `api/src/middlewares/requestLogger.js`: structured JSON logs including `request_id` (no PII)
- [ ] T045 [P] [US5] Add `structlog` to `agent/pyproject.toml`; configure JSON output in the agent
- [ ] T046 [US5] Agent: read inbound `X-Request-ID` (per research R7 SDK-metadata probe) and attach it to LangSmith run metadata so a trace is findable by id
- [ ] T047 [US5] Validate observability contract (SC-012); create `docs/adr/ADR-031-structured-logging.md` + learning-lesson; **manual gate → commit on approval**

**Checkpoint**: correlation id end-to-end; US5 independently validated.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T048 [P] Update `docs/adr/README.md` index with ADR-027, 028, 029, 030, 031
- [ ] T049 [P] Update `CLAUDE.md` Architecture section if the harness changed (audio nodes removed, `create_agent` scaffold)
- [ ] T050 Run full `quickstart.md` per-batch validation end-to-end
- [ ] T051 Final regression: 70 pytest + 39 Jest + all new tests green; confirm SC-001..013 met or recorded

---

## Dependencies & Execution Order

### Phase / batch dependencies

- **Setup (P1)** → no deps.
- **Foundational B0 (P2)** → after Setup. **Blocks B3 (T005) and B4 (T006); provides baseline (T004) for all US2 validation.**
- **US2 B1/B2** → after Setup (don't need B0 to *implement*, but need T004 baseline to *validate*).
- **US2 B3** → needs T005 (R2). **US2 B4** → needs T006 (R3).
- **US2 B5** → independent; its spike (T020) decides direction.
- **US1 B6** → independent (node-level tenacity/pybreaker; does not need `create_agent`).
- **US3 B7** → introduces `MessagesState` + `create_agent` scaffold (T032/T033).
- **US4 B8** → **depends on the B7 scaffold (T033)** for `SummarizationMiddleware`.
- **US5 B9** → independent (API/nginx/agent logging).
- **Polish (P8)** → after all desired batches.

### Story independence note

US1, US2, US5 are independently testable. US4 (B8) depends on the B7 `create_agent` scaffold — an intentional, honest dependency (both consume the same middleware host) rather than forced independence. The sequential batch model (one approved commit at a time) makes this safe.

### Within each batch

Tests fail-first → implementation → ADR/lesson → **manual gate → commit**.

---

## Parallel Opportunities

- **Setup**: T001, T002 in parallel.
- **B6 reliability**: after T024 (tests) + T025 (deps), the call-site edits T026/T027/T028/T029/T030 touch different files → parallelizable.
- **B9 observability**: T043 (API middleware) and T045 (agent dep) in parallel; T041 tests in parallel.
- Tasks marked **[P]** within a phase touch different files with no incomplete-task dependency.

---

## Implementation Strategy

### Latency-first delivery (user-mandated)

1. Phase 1 Setup + Phase 2 **B0 baseline/probe** (CRITICAL — makes latency falsifiable, gates B3/B4).
2. **B1 → B2** (biggest, lowest-risk latency wins) → validate vs baseline → approve → commit each.
3. **B3 → B4** (harness persistence, if R2/R3 positive) → validate SC-006 → approve → commit.
4. **B5** (audio spike + swap) → validate SC-007 → approve → commit.
5. **B6** reliability (P1-critical) → resilience contract → approve → commit.
6. **B7 → B8** safety + context (shared `create_agent` scaffold) → contracts → approve → commit.
7. **B9** observability → correlation contract → approve → commit.
8. **Polish**: ADR index, docs, full quickstart, final regression.

### Per-batch definition of done

- [ ] Failing-first tests written and then passing
- [ ] 70 pytest + 39 Jest still green (FR-023)
- [ ] Batch's manual-validation outcomes met (contracts/quickstart)
- [ ] **User approval received**
- [ ] ADR created/updated + learning-lesson created/updated
- [ ] One batch = one commit on `dev`

---

## Notes

- **Manual gate is mandatory** before every commit (Delivery Model). Do not auto-commit batches.
- `[P]` = different files, no dependency on an incomplete task.
- B3/B4 are contingent on the B0 probe; if the managed server doesn't expose the config, record the negative result and (per ADR-025) treat P10 (own runtime) as a separate, out-of-scope decision.
- **B4 cache scope (Constitution IV)**: only write-stable lookups are cached; availability/appointment reads are excluded or invalidated on write — never serve stale.
- **FR-012 scope (G3)**: only the **audio** model selection (B5) is in this cycle. Non-OpenAI **text** model selection via LiteLLM (research R10) is **deferred/out-of-scope this cycle** — FR-012 is a SHOULD; revisit in a future batch.
- **Priority note (I1)**: US2 is front-loaded for latency per the user mandate, but **US1 (reliability, P1-critical) must land at B6 and not be deferred further** — it is the first batch after the latency wins.
- Total: 51 tasks across 8 phases / 10 batches (B0–B9).
