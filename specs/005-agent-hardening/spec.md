# Feature Specification: Agent Hardening (Production-Grade Resilience)

**Feature Branch**: `005-agent-hardening`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "analyze the artifacts in specs/005-agent-hardening/spec.md then build the spec 005 utilizing the SDD framework. Additionally read the relevant docs/adr/ and docs/learning-lessons/"

**Supporting artifacts**:
[technical-design.md](./technical-design.md) ·
[ADR-024 (retry/resilience)](../../docs/adr/ADR-024-retry-resilience-strategy.md) ·
[ADR-025 (checkpoint strategy)](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) ·
[learning-lessons/arquitetura_redis_postgress.md](../../docs/learning-lessons/arquitetura_redis_postgress.md)

---

## Why This Feature Exists

AgendAI runs in production (Phase 1 on Render), but production observation revealed it is not
yet production-grade: a transient backend hiccup can silently drop a patient's message, the
streamed response stutters noticeably, untrusted input reaches the model unguarded, long
conversations risk overflowing the model's context, and incidents are hard to trace end-to-end.

This feature hardens the agent along five dimensions that **do not require user
authentication**: reliability, performance, content safety, context sustainability, and
observability. Identity-dependent work (per-user sessions, long-term memory, human-in-the-loop)
is deliberately deferred to **Spec 006** (auth + session) and **Spec 007** (memory + HITL).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A patient always gets an answer (Priority: P1)

A patient sends a scheduling request through the chat. Even when the model provider or the
internal scheduling API has a transient failure or is waking from a cold start, the patient
still receives a correct answer. When a provider is genuinely unavailable, the patient gets a
clear, fast message in Portuguese instead of a hang or a blank failure.

**Why this priority**: A patient who sends a message and receives nothing is the single worst
outcome — it erodes trust and loses the booking. Reliability is the foundation; nothing else
matters if the system silently fails. This is the MVP slice.

**Independent Test**: Inject transient failures (provider connection error, internal API cold
start, slow database) during a scheduling flow and confirm the patient still receives the
correct response with no visible error. Separately, force sustained provider failure and
confirm the patient receives a clear pt-BR message within roughly one second rather than a
long timeout.

**Acceptance Scenarios**:

1. **Given** the model provider returns a transient connection error on the first attempt,
   **When** the patient asks for available times, **Then** the system retries and the patient
   receives the correct list without seeing any error.
2. **Given** the internal scheduling API is cold-starting, **When** the agent needs to call it,
   **Then** the agent waits and retries within a bounded window and the request still succeeds.
3. **Given** the model provider has failed repeatedly beyond the failure threshold, **When** a
   patient sends a message, **Then** the patient receives a clear pt-BR unavailability message
   quickly instead of waiting for a timeout.
4. **Given** the internal API returns a business error (e.g., slot already taken), **When** the
   agent receives it, **Then** the system does NOT retry and relays the correct business
   outcome to the patient.

---

### User Story 2 - Responses feel fast and fluid (Priority: P2)

A patient interacting with the chat experiences responses that begin quickly and stream
smoothly, without the multi-second stalls ("engasgo") observed in production between
conversation phases. A significant share of that stall comes from the system writing the full
conversation state to durable storage after **every** internal processing step — most of which
contributes nothing to recovery. Responses feel fluid when that persistence cost is taken off
the patient's critical path.

**Why this priority**: Latency is the most-felt day-to-day complaint. The system "works"
without this slice, so it ranks below reliability — but perceived speed strongly shapes whether
patients complete a booking.

Speed also depends on the AI models chosen and the voice path: the current transcription and
speech-synthesis steps add several seconds to a voice interaction, and faster/cheaper models
exist for both text and audio. Choosing models that minimize latency and cost — without losing
reliable tool-calling or transcription quality — is part of making responses feel fast and
keeping the per-conversation cost sustainable.

**Independent Test**: Measure end-to-end latency for a standard text scheduling request against
the current production baseline, and confirm a meaningful reduction with no perceptible
multi-second stalls between phases of the streamed answer. Separately, count the durable-storage
write operations on the critical path and confirm they drop substantially while conversation
recovery still works. For the voice path, measure the added transcription+synthesis latency and
confirm it stays within an acceptable bound.

**Acceptance Scenarios**:

1. **Given** the model requests several independent lookups, **When** it fulfills a request,
   **Then** those lookups happen concurrently rather than one after another.
2. **Given** a standard text scheduling request, **When** the patient submits it, **Then** the
   median end-to-end latency is meaningfully lower than the measured baseline.
3. **Given** the same lookup is needed twice within one conversation, **When** it recurs,
   **Then** the system reuses the earlier result instead of recomputing it.
4. **Given** a multi-step conversation turn, **When** the agent processes it, **Then** the
   system persists durable state only at the points needed for recovery (e.g., turn boundaries)
   rather than after every internal step.
5. **Given** an active conversation, **When** the patient continues it, **Then** ephemeral
   session state is served from fast storage while only selected long-lived data is written
   durably — the patient does not wait on full-state writes between phases.
6. **Given** a voice message, **When** it is transcribed, processed, and answered, **Then** the
   latency added by the audio steps stays within an acceptable bound and does not dominate the
   interaction.

---

### User Story 3 - Interactions stay safe and private (Priority: P2)

Patient input that is malicious (prompt injection/jailbreak), off-scope (not about medical
scheduling), or that contains sensitive personal data is handled safely. The agent never leaks
another patient's data and never persists user-supplied sensitive data into logs.

**Why this priority**: AgendAI handles patient PII; the constitution requires input guardrails
to land before the system processes unmoderated public input at scale. It is a safety and
privacy gate, ranked alongside performance.

**Independent Test**: Run a corpus of injection, off-scope, and PII-bearing inputs and confirm
each is blocked, refused with a clear pt-BR fallback, or redacted as appropriate; inspect logs
to confirm no sensitive data was written.

**Acceptance Scenarios**:

1. **Given** an input containing a known prompt-injection pattern, **When** it is received,
   **Then** it is blocked before reaching the model.
2. **Given** an off-scope request (e.g., "help me write code"), **When** it is received,
   **Then** the agent declines with a clear pt-BR message scoped to the clinic.
3. **Given** an input containing sensitive personal data, **When** it is processed, **Then**
   that data does not appear in any application log.
4. **Given** a generated response, **When** it is returned, **Then** it contains no other
   patient's data and no off-scope or unsafe content.

---

### User Story 4 - Long conversations stay coherent and sustainable (Priority: P3)

A patient in a long back-and-forth keeps getting coherent answers. The conversation never
breaks because of context overflow, and latency and cost do not balloon as history grows.

**Why this priority**: Most conversations are short, so this is lower priority — but unbounded
context will eventually break long sessions and inflate cost, so it must be addressed before
scale.

**Independent Test**: Drive a conversation past 20 turns and confirm no context-limit failure,
that key facts (bookings made, cancellations, stated preferences) are still honored, and that
latency remains stable.

**Acceptance Scenarios**:

1. **Given** a conversation exceeding the configured turn threshold, **When** the patient sends
   another message, **Then** older history is compacted (not abruptly truncated) and the
   response remains coherent.
2. **Given** a long conversation, **When** the working context is assembled, **Then** it stays
   within the model's limit.
3. **Given** earlier critical facts (a booking was made, a preference stated), **When** history
   is compacted, **Then** those facts are preserved.

---

### User Story 5 - Incidents are traceable end-to-end (Priority: P3)

When a patient reports a problem, an operator can reconstruct the exact request as it traveled
through the gateway, the API, and the agent, and link it to the corresponding trace — quickly
and unambiguously.

**Why this priority**: This delivers operational value rather than direct patient value, so it
ranks lower — but it is what turns production incidents into diagnosable events.

**Independent Test**: Trigger a known error in a request and confirm a single correlation id
links every log line across components and the agent trace, and that an operator can find the
full path within minutes.

**Acceptance Scenarios**:

1. **Given** an incoming request, **When** it enters the system, **Then** it is assigned a
   unique correlation id propagated to every component.
2. **Given** an error occurred on a specific request, **When** an operator searches by its
   correlation id, **Then** they retrieve the complete request path and the agent trace.

---

### Edge Cases

- **Sustained outage vs transient blip**: the system must retry transient failures but fail
  fast (clear message) once a dependency is repeatedly down — it must not retry forever.
- **Business error masquerading as failure**: a "slot unavailable" (409) or "patient not found"
  (404) must never be retried as if it were transient.
- **Retry on an already-applied side effect**: retries must not duplicate an irreversible action
  (e.g., a confirmation email already sent).
- **Compaction losing a just-made booking**: history summarization must not drop a fact the
  patient will rely on later in the same conversation.
- **Guardrail false positive**: a legitimate medical-scheduling request must not be wrongly
  blocked as off-scope.
- **Audio flow**: reliability, guardrails, and latency improvements must hold for the
  voice/transcription path as well as text.

---

## Requirements *(mandatory)*

### Functional Requirements

**Reliability (US1)**

- **FR-001**: System MUST automatically retry transient external failures (model provider,
  internal scheduling API, database) with backoff before surfacing an error to the patient.
- **FR-002**: System MUST distinguish transient infrastructure failures from business errors
  and MUST NOT retry business errors (e.g., slot unavailable, patient not found, validation
  failures).
- **FR-003**: System MUST fail fast with a clear pt-BR message when a critical dependency is
  unavailable beyond a defined failure threshold, instead of hanging until timeout.
- **FR-004**: System startup MUST tolerate a slow-to-start datastore for a bounded warm-up
  period before failing with a diagnostic.
- **FR-005**: A transient failure that is successfully retried MUST NOT be visible to the
  patient.
- **FR-006**: System MUST NOT repeat an irreversible side effect (e.g., a confirmation email)
  when retrying a step.

**Performance (US2)**

- **FR-007**: When the model requests multiple independent lookups, System MUST execute them
  concurrently rather than sequentially.
- **FR-008**: System MUST minimize the number of model round-trips needed to fulfill a standard
  scheduling request.
- **FR-009**: System MUST NOT persist the full conversation/execution state after every internal
  processing step. Durable state MUST be written only at the points required for recovery (e.g.,
  at turn or conversation boundaries), not after each node.
- **FR-010**: System MUST keep ephemeral active-session state in low-latency storage and MUST
  persist durably only the selected long-lived data needed for recovery — full-state writes MUST
  NOT block the patient's response between conversation phases.
- **FR-011**: System SHOULD reuse the result of an identical, repeated lookup within the same
  conversation instead of recomputing it.
- **FR-012**: System SHOULD select the AI models (for text and for the voice path) that minimize
  response latency and per-request cost while preserving reliable tool-calling and acceptable
  transcription/synthesis quality.
- **FR-013**: The voice path MUST keep the latency added by transcription and speech synthesis
  within an acceptable bound so it does not dominate the interaction.

**Safety & Privacy (US3)**

- **FR-014**: System MUST validate patient input before acting on it and MUST block recognized
  prompt-injection/jailbreak attempts before they reach the model.
- **FR-015**: System MUST refuse off-scope (non medical-scheduling) requests with a clear pt-BR
  fallback message.
- **FR-016**: System MUST prevent user-supplied sensitive personal data from being persisted in
  application logs.
- **FR-017**: System MUST ensure generated responses never disclose another patient's data or
  off-scope/unsafe content.

**Context Sustainability (US4)**

- **FR-018**: System MUST keep the working context within the model's limit regardless of
  conversation length.
- **FR-019**: System MUST compact (summarize) older history rather than truncate it abruptly,
  preserving critical facts (bookings made, cancellations, stated preferences).

**Observability (US5)**

- **FR-020**: System MUST assign a unique correlation id to each request and propagate it across
  the gateway, API, and agent.
- **FR-021**: System MUST emit structured logs that let an operator reconstruct a single
  request's end-to-end path.
- **FR-022**: Agent interactions (including tool calls) MUST be traceable and linkable to the
  request's correlation id.

**Cross-cutting (constitution)**

- **FR-023**: All existing automated tests (API + agent) MUST remain green, and new behavior
  MUST ship with tests that fail before and pass after implementation.
- **FR-024**: User-facing errors MUST be clear pt-BR messages and MUST NEVER expose raw stack
  traces, secrets, or internal detail.

### Key Entities *(include if feature involves data)*

- **Conversation Session**: the ongoing exchange with one patient — its turns/messages and the
  working context sent to the model. Its state has two tiers: **ephemeral session state** (the
  in-flight working data, kept in low-latency storage) and **durable recovery state** (the
  selected long-lived data persisted only at recovery points, not after every step).
- **Request Trace**: a single inbound request's journey, identified by a correlation id that
  links gateway, API, agent, and observability records.
- **Guardrail Decision**: the outcome of validating an input or output — allow, block, refuse,
  or redact — together with the reason.
- **Resilience State**: per-dependency health used to decide retry vs. fail-fast (recent
  failure count and whether the circuit is open or closed).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under transient-failure injection, at least 99% of patient messages receive a
  correct answer or a clear failure message, and 0 messages are silently dropped.
- **SC-002**: In transient-failure test scenarios, the patient sees no error 100% of the time
  (the retry fully masks the blip).
- **SC-003**: When a dependency is genuinely down, the patient receives a clear pt-BR message
  within ~1 second rather than waiting for a timeout.
- **SC-004**: Median end-to-end latency for a standard text scheduling request is reduced by at
  least 50% versus the measured production baseline.
- **SC-005**: No multi-second stalls are perceptible between phases of the streamed response in
  the standard scheduling flow.
- **SC-006**: The number of durable-storage write operations on the critical path of a standard
  multi-step turn is reduced by at least 80% versus the current per-step baseline, with
  conversation recovery still functioning.
- **SC-007**: For a voice interaction, the latency added by transcription and speech synthesis
  is reduced by at least 50% versus the current baseline.
- **SC-008**: The average AI-model cost per conversation does not grow as conversation length
  increases, and does not exceed the current per-conversation baseline.
- **SC-009**: 100% of prompt-injection and off-scope inputs in the test corpus are blocked or
  safely refused before reaching the model.
- **SC-010**: 0 occurrences of user-supplied sensitive personal data appear in application logs
  across the test corpus.
- **SC-011**: Conversations of 20+ turns complete with 0 context-limit failures and retain 100%
  of critical facts (bookings, cancellations, preferences) in the test scenarios.
- **SC-012**: Any reported patient issue can be traced to its complete request path via a single
  correlation id in under 5 minutes.
- **SC-013**: The full automated test suite (API + agent) passes on every change.

---

## Assumptions

- **Baseline measurement**: the current end-to-end latency baseline (overall and per phase) will
  be measured at planning time; the 50% reduction target (SC-004) is relative to that
  measurement.
- **No authentication in scope**: this spec uses the existing shared service token; per-user
  identity and isolation are delivered in [Spec 006](../006-auth-session/spec.md).
- **No long-term memory or HITL in scope**: those are delivered in
  [Spec 007](../007-memory-hitl/spec.md).
- **Guardrails are in-system for this phase**: lightweight checks (pattern/list based) run
  inside the agent; managed cloud guardrails are a later-phase upgrade.
- **State-persistence strategy** (FR-009/FR-010): the agent runtime today writes the full graph
  state to durable Postgres after every node — for a ~6-node turn that is ~62 writes / ~8s of
  overhead, and ADR-025 / the Redis-Postgres learning lesson show ~75% of those writes carry no
  recovery value. The strategy is: (a) write durably only at recovery points instead of after
  each node (checkpoint "exit"/selective mode), and (b) layer persistence — keep ephemeral
  session state in fast storage (Redis, already deployed for streaming) and persist only
  selected long-lived data durably (Postgres). See
  [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md) and
  [the learning lesson](../../docs/learning-lessons/arquitetura_redis_postgress.md).
- **Managed runtime retained**: the managed LangGraph Server remains the runtime. The first move
  is to tune checkpoint frequency within it (exit/selective mode); reusing the existing Redis as
  a node-output cache is investigated next. Migrating off the managed server for full control of
  state persistence is conditional and out of immediate scope — only revisited if checkpoint
  frequency cannot be tuned within the managed server AND it remains the dominant latency cost
  after the other performance work.
- **Model evaluation is exploratory** (FR-012/FR-013, SC-007/SC-008): faster/cheaper text and
  audio models are evaluated via benchmark before any swap. Reliable tool-calling is a hard
  gate — a cheaper model that mis-calls tools is rejected. The voice path is the clearest win
  (a faster transcription provider can cut several seconds with no architecture change); a fully
  real-time voice model is a larger, later change. Details in
  [technical-design.md](./technical-design.md) (QW-6).
- **Framework modernization (P8) is the preferred implementation approach, not a user story**:
  the safety (FR-014/015), context (FR-018/019) and retry (FR-001) requirements are intended to
  be delivered via the newer agent middleware (prebuilt PII, summarization, and retry behaviors)
  rather than hand-written nodes — one implementation instead of repeated manual code. This is a
  *how*, not a *what*, so it is an approach decision, not a requirement. It is **conditional on a
  stability gate**: the middleware API was removed once without notice, so if it is unstable when
  P4/P6 are implemented, those requirements fall back to manual nodes (fully specified in the
  technical design). The stable, gate-independent part (adopting `MessagesState`) proceeds
  regardless. Decision and gate recorded in
  [ADR-026](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md).
- **Cold-start keep-alive is optional**: on the free hosting tier, an external uptime pinger can
  keep services awake to avoid cold-start delay. It is an operational workaround (no code) that
  becomes unnecessary on a paid tier; reliability against cold starts is already required via
  retry (FR-001).
- **Established retry pattern**: the retry approach already used by the TTS and email senders is
  the pattern extended to the remaining external calls (see ADR-024).
- **Audio and text share the hardening**: improvements apply to both the text and the
  voice/transcription paths.

---

## Out of Scope

- Authentication and per-user session isolation → [Spec 006](../006-auth-session/spec.md)
- Long-term memory (patient facts) and Human-in-the-Loop confirmations →
  [Spec 007](../007-memory-hitl/spec.md)
- Managed cloud guardrails (e.g., provider-side moderation) → later phase
- Migrating off the managed agent runtime → conditional, later phase
- Infrastructure-as-code / cloud provisioning → separate spec

---

## Dependencies

- [ADR-024 — Retry & Resilience Strategy](../../docs/adr/ADR-024-retry-resilience-strategy.md)
  underpins US1 / FR-001–FR-006.
- [ADR-025 — LangGraph Checkpoint Strategy](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md)
  underpins US2 / FR-009–FR-010.
- [ADR-026 — create_agent + middleware vs. manual nodes](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md)
  records the preferred implementation approach (with stability gate) for FR-001 / FR-014–FR-015 /
  FR-018–FR-019.
- [learning-lessons/arquitetura_redis_postgress.md](../../docs/learning-lessons/arquitetura_redis_postgress.md)
  — latency hierarchy and Redis/Postgres findings informing US2.
- [AgendAI Constitution](../../.specify/memory/constitution.md) — Principles II (TDD), IV
  (observability), and VI (security) are directly exercised by this feature.
- [technical-design.md](./technical-design.md) — the detailed gap analysis, Quick Wins, and
  model evaluation that feed `/speckit-plan`.
