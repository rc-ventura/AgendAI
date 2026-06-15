# Contract — Resilience Behavior (US1 / P1)

Behavioral contract for retry + circuit breaker. Implements FR-001..006. Backed by
[ADR-024](../../../docs/adr/ADR-024-retry-resilience-strategy.md).

## Retry policy per dependency

| Call site | Retry? | Attempts | Backoff | Retry-on | Breaker |
|-----------|--------|----------|---------|----------|---------|
| `llm_core.py` (OpenAI) | yes | 3 | exp 2→10s | `APIConnectionError`, `APITimeoutError`, `RateLimitError` | yes (fail_max=3, reset 30s) |
| `transcriber.py` (Whisper) | yes | 3 | exp 2→10s | `APIConnectionError`, `APITimeoutError` | no |
| `api_client.py` (→ API) | yes | 3 | exp 1→8s | `httpx.ConnectError`, `httpx.TimeoutException` only | no |
| `db/connection.js` (startup) | yes | 5 | 1→5s, factor 2 | transient (not "DATABASE_URL missing") | no |
| `repositories/*.js` (queries) | yes | 3 | — | `ECONNREFUSED`/timeout/conn-terminated | no |

## MUST / MUST NOT

- MUST NOT retry business errors: API 4xx (404 paciente, 409 horário), PG constraint violations,
  OpenAI `AuthenticationError`.
- MUST NOT duplicate irreversible side effects on retry (`email_sender` is idempotent-guarded).
- Circuit breaker open → MUST return a clear pt-BR unavailability message in ~≤1s (no hang).
- A successfully-retried transient failure MUST be invisible to the patient.

## Observable outcomes (testable)

1. Inject `APIConnectionError` once on the first LLM call → final answer correct, no error shown.
2. Force 3 consecutive LLM failures → breaker opens, pt-BR message within ~1s.
3. API cold-start (connection refused, then ok) → request succeeds after retry.
4. API 409 (slot taken) → no retry; business outcome relayed once.
5. 70 pytest + 39 Jest stay green.
