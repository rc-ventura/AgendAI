# Phase 1 Data Model — Agent Hardening (Spec 005)

This feature is mostly behavioral (resilience, latency, guardrails, observability). It introduces
no new API database tables. The data it does touch is: the **agent graph state** (`AgendAIState`),
in-memory **resilience/guardrail** structures, and the **correlation-id** that flows across
services. Entities map to the spec's Key Entities.

---

## Entity: Conversation Session

Maps to the spec's *Conversation Session*. Two tiers (FR-009/FR-010):

| Tier | What | Where | Lifetime |
|------|------|-------|----------|
| **Ephemeral session state** | in-flight working data of the current turn (messages buffer, tool results, pending email) | Redis (fast) / in-graph state | the turn / active session |
| **Durable recovery state** | the checkpoint needed to resume a conversation | Postgres (selective, at recovery points) | conversation thread |

**Current `AgendAIState`** (`agent/agent/state.py`, unchanged fields):

```python
class AgendAIState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input_type: Literal["text", "audio"]
    audio_data: bytes | None
    session_id: str
    email_pending: bool
    email_payload: dict | None
    final_response: str | bytes | None
```

**Planned deltas** (additive, per batch — each lands with the batch that needs it):

| Field | Type | Batch | Purpose |
|-------|------|-------|---------|
| `processed_tool_ids` | `list[str]` | (exists) | email dedup — already added |
| `blocked` | `bool` | B7 | guardrail blocked this input |
| `block_reason` | `Literal["prompt_injection","off_scope","pii_detected"] \| None` | B7 | why blocked (for fallback message + log) |
| `context_summary` | `str \| None` | B8 | compacted history injected into the prompt |
| `request_id` | `str \| None` | B9 | correlation id for trace/log linkage |

> `messages` may migrate to `MessagesState` base (ADR-026, stable part) — same shape, less
> boilerplate. No field removed. State growth stays bounded by B8 (context manager).

**State transitions (turn lifecycle with new gates)**:

```
detect_input → [B7 validate_input] → (blocked? → fallback → END)
            → transcribe(audio) → chat_with_llm ⇄ tools
            → [B7 validate_output] → (send_email?) → (tts?) → END
                                   ↑ durable checkpoint only at turn boundary (B3)
```

---

## Entity: Request Trace

Maps to the spec's *Request Trace* (US5 / FR-018–020). Not persisted as a row — it is the
correlation key that links log lines and the LangSmith trace.

| Field | Type | Origin | Notes |
|-------|------|--------|-------|
| `request_id` | UUID string | nginx (`X-Request-ID`), or API if absent | propagated nginx→API→agent |
| `service` | `"nginx"\|"api"\|"agent"` | each emitter | structured log field |
| `trace_id` | string | LangSmith | agent attaches `request_id` to run metadata |

No DB table. Lives in logs (JSON) + LangSmith metadata. Retention follows existing log retention.

---

## Entity: Guardrail Decision

Maps to the spec's *Guardrail Decision* (US3 / FR-011–017). Ephemeral, per input/output.

| Field | Type | Values |
|-------|------|--------|
| `action` | enum | `allow` \| `block` \| `refuse` \| `redact` |
| `reason` | enum \| null | `prompt_injection` \| `off_scope` \| `pii_detected` \| `toxic` \| null |
| `applies_to` | enum | `input` \| `output` |

**Rules** (from technical-design P4 table):

| Check | input | output | reason |
|-------|-------|--------|--------|
| prompt injection | block | — | `prompt_injection` |
| off-scope (non-medical) | refuse | refuse | `off_scope` |
| PII (CPF/email/phone) | redact (log-safe) | redact | `pii_detected` |
| toxic content | — | refuse | `toxic` |

A `block`/`refuse` short-circuits to a pt-BR fallback; PII is never written to logs (FR-016).

---

## Entity: Resilience State

Maps to the spec's *Resilience State* (US1 / FR-001–006). In-memory, per dependency.

| Field | Type | Notes |
|-------|------|-------|
| `dependency` | enum | `openai_llm` \| `whisper` \| `internal_api` \| `postgres` |
| `retry_policy` | struct | attempts, backoff (exponential), retry-on exception types (ADR-024) |
| `breaker_state` | enum | `closed` \| `open` \| `half_open` (LLM only, `pybreaker`) |
| `fail_count` | int | recent consecutive failures feeding the breaker |

**Policy matrix** (ADR-024): retry transient (`APIConnectionError`, `APITimeoutError`,
`RateLimitError`, `ConnectError`, `TimeoutException`, transient PG); **never** retry business
errors (4xx, 404/409, constraint violations) or auth errors. Circuit breaker only on
`openai_llm` (fail_max=3, reset=30s).

---

## Validation rules (cross-entity)

- A `block`/`refuse` guardrail decision MUST prevent the LLM call (input) or replace the response
  (output) — never partially applied.
- A retried transient failure MUST NOT duplicate an irreversible side effect (`email_sender`,
  already retry-guarded) — FR-006.
- Durable checkpoint writes MUST occur at recovery points only; ephemeral state MUST NOT require a
  durable write to advance a node — FR-009/010.
- `request_id` MUST be present on every log line once B9 lands; absence is a defect.

## No API schema changes

The five API tables (`medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos`) are
**unchanged**. Retry wraps existing queries; logging wraps existing requests. This keeps
constitution I (layering) and II (real-DB tests) intact with no migration.
