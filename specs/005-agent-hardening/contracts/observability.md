# Contract — Observability & Correlation (US5 / P5)

Behavioral contract for structured logs + correlation id. Implements FR-018..020. Backed by
ADR-031 (to be created in B9).

## Correlation id flow

```
nginx generates X-Request-ID (UUID) ─► API logs with request_id ─► agent (structlog JSON)
        │                                                                  │
        └──────────────── propagated via header ───────────────────► LangSmith run metadata
```

## Log line contract (structured JSON, every service)

| Field | Required | Example |
|-------|----------|---------|
| `request_id` | yes (after B9) | `"a0f5-..."` |
| `service` | yes | `"api"` \| `"agent"` \| `"nginx"` |
| `level` | yes | `"info"` \| `"error"` |
| `event` | yes | `"horarios.query"` |
| `ts` | yes | ISO-8601 |
| `pii` | — | MUST NOT contain raw patient PII (see guardrail contract) |

## MUST / MUST NOT

- Every request MUST carry one `request_id` end-to-end; if nginx did not set it, the API MUST
  generate it.
- The agent MUST attach `request_id` to the LangSmith run metadata so a trace is findable by id.
- Agent stdout log lines MUST include `request_id` (set via `ContextVar` in `detect_input_type`
  from `config["metadata"]["request_id"]`). Default value `"-"` when no metadata is present.
- Logs MUST NOT include secrets, stack traces shown to users, or raw PII.
- User-facing errors MUST remain pt-BR (FR-024) regardless of log content.

## Observable outcomes (testable)

1. One request → same `request_id` in nginx, API, and agent logs.
2. Search by `request_id` → retrieve full path + LangSmith trace in < 5 min (SC-012).
3. Forced error → correlation id present on the error log line.
4. `set_request_id("x")` → next logger call → JSON output contains `"request_id": "x"`.
5. No `set_request_id` call → logger output contains `"request_id": "-"` (never raises).
