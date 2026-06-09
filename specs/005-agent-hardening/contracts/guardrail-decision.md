# Contract — Guardrail Decision (US3 / P4)

Behavioral contract for input/output guardrails. Implements FR-011..017. Backed by ADR-029 (to
be created in B7) and the ADR-026 gate (manual nodes vs `PIIMiddleware`).

## Control points

```
input → [validate_input] → chat_with_llm ⇄ tools → [validate_output] → response
         block/refuse/redact                          refuse/redact
```

## Decision table

| Check | applies_to | action | reason | result |
|-------|-----------|--------|--------|--------|
| Prompt injection / jailbreak | input | block | `prompt_injection` | short-circuit → pt-BR fallback, LLM not called |
| Off-scope (non medical-scheduling) | input + output | refuse | `off_scope` | pt-BR clinic-scope fallback |
| PII (CPF / email / phone) | input + output | redact | `pii_detected` | redacted before model/log; never logged raw |
| Toxic content | output | refuse | `toxic` | replaced with pt-BR fallback |

## MUST / MUST NOT

- A `block`/`refuse` MUST fully prevent the action (no partial LLM call / no partial response).
- User-supplied PII MUST NOT appear in any application log (FR-016) — redaction happens before
  the structured logger sees the field.
- Output MUST NOT disclose another patient's data or off-scope/unsafe content (FR-017).
- A legitimate scheduling request MUST NOT be misclassified as off-scope (false-positive gate is
  part of the test corpus).

## Observable outcomes (testable)

1. Known injection pattern → blocked before LLM (verify no model call in trace).
2. "me ajude a escrever código" → pt-BR off-scope refusal.
3. Input with a CPF → CPF absent from logs.
4. Output containing PII → redacted before delivery.
5. Corpus: 100% of injection/off-scope blocked or refused (SC-009); 0 PII in logs (SC-010).
