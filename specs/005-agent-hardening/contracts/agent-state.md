# Contract — Agent State Schema (harness)

Contract for `AgendAIState` evolution. The state is the harness's data interface; changes are
**additive** and land with the batch that needs them. Backed by [ADR-026](../../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md)
(MessagesState adoption) and [ADR-025](../../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md)
(persistence tiers).

## Invariants

- Changes are **additive only** — no existing field removed or retyped (protects thread
  compatibility). The orphaned-ToolMessage guard formerly in `llm_core.py`
  (`_sanitize_messages`) was removed with the `create_agent` migration (ADR-026): the
  chat+tools loop now lives inside the `text_agent` subgraph, which owns the
  `AIMessage`/`ToolMessage` lifecycle. External messages entering the subgraph are
  `HumanMessage`s only.
- `messages` keeps `add_messages` reducer semantics (whether as `TypedDict` or `MessagesState`).
- New fields default to `None`/empty so existing in-flight threads remain valid.

## Field contract (current + planned)

| Field | Type | Status | Batch |
|-------|------|--------|-------|
| `messages` | `Annotated[list[AnyMessage], add_messages]` | stable | — |
| `input_type` | `Literal["text","audio"]` | stable | — |
| `audio_data` | `bytes \| None` | stable | — |
| `session_id` | `str` | stable | — |
| `email_pending` | `bool` | stable | — |
| `email_payload` | `dict \| None` | stable | — |
| `final_response` | `str \| bytes \| None` | stable | — |
| `processed_tool_ids` | `list[str]` | exists | — |
| `blocked` | `bool` | planned | B7 |
| `block_reason` | `Literal[...] \| None` | planned | B7 |
| `context_summary` | `str \| None` | planned | B8 |
| `request_id` | `str \| None` | planned | B9 |

## Persistence contract (B3/B4)

- Durable checkpoint of state occurs **at recovery points** (turn boundary), not per node.
- Ephemeral working state may live in Redis between nodes without a durable write.
- Node-output cache (if enabled, B4) keys on tool name + args within a session, and is **scoped to
  write-stable lookups only** (e.g., `buscar_pagamentos`). Availability/appointment reads
  (`buscar_horarios`) MUST be excluded or invalidated on `criar_agendamento`/`cancelar_agendamento`
  — the cache MUST NOT serve stale availability (Constitution IV).

## Observable outcomes (testable)

1. An existing thread created before a field is added still loads (additive compatibility).
2. After B3, durable checkpoint rows per turn drop ≥80% (SC-006) with resume still working.
3. The `text_agent` subgraph (create_agent) keeps the `AIMessage`/`ToolMessage` sequence
   consistent when a thread is reloaded from a checkpoint — a turn does not fail with an
   orphaned-ToolMessage 400 (this guard was previously `_sanitize_messages`).
