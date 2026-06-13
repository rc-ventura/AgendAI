# QA Report v1.0 - Spec 005 Agent Hardening

**Date:** 2026-06-12  
**Scope:** `/specs/005-agent-hardening` artifacts + implemented codebase + tests + constitution alignment  
**Reviewer mindset:** QA gatekeeper (reject-first posture)

---

## Executive Verdict

**Production readiness:** **NOT APPROVED** (blocking issues found)

Top blockers:
- Potential duplicate irreversible side effect (email resend risk).
- Constitution Principle VII non-compliance on agent state model.

---

## Evidence Summary

- Artifacts reviewed:
  - `spec.md`, `plan.md`, `tasks.md`
  - contracts (`resilience.md`, `guardrail-decision.md`, `observability.md`, `agent-state.md`)
  - `.specify/memory/constitution.md`
- Code reviewed:
  - agent core (`graph.py`, `state.py`, `middleware.py`, `guardrails.py`, `resilience.py`, nodes)
  - API (`app.js`, middleware, db retry, cache, services/repositories)
  - BFF/nginx correlation and durability path
- Test execution:
  - Agent: `91 passed`
  - API: `48 passed` (with `DATABASE_URL` configured to local Postgres test DB)

---

## Findings (Ordered by Severity)

### CRITICAL-01 - Duplicate email side effect risk (FR-006)

`tool_result_processor` can still pick an old email-triggering tool call from previous turns if the current turn has no tool call, re-setting `email_pending` and potentially re-sending.

Impact:
- Breaks "no duplicate irreversible side effect" requirement.
- Can send wrong/duplicate patient communication.

Files:
- `agent/agent/nodes/tool_result_processor.py`

Status: **Blocking**

---

### CRITICAL-02 - Constitution VII mismatch (state model)

Constitution requires graph state to be `TypedDict` (or Pydantic). Current implementation uses class inheritance from `MessagesState`.

Impact:
- Governance non-compliance with a MUST principle.
- Release should not be approved without explicit constitution-compliant resolution.

Files:
- `.specify/memory/constitution.md`
- `agent/agent/state.py`

Status: **Blocking**

---

### HIGH-01 - Correlation ID is not present in agent infrastructure log lines

`request_id` is added to run metadata through BFF, but agent logger JSON schema does not include `request_id`.

Impact:
- Partial compliance with FR-020/FR-022.
- Slower cross-system troubleshooting from plain logs.

Files:
- `agent-ui-pro/src/app/api/[..._path]/route.ts`
- `agent/agent/logging_config.py`

Status: **High**

---

### HIGH-02 - Durability "exit" validation is mostly static

Current guard validates code presence (`durability` string in Route Handler), but runtime assertion for checkpoint write reduction and recovery behavior is not strongly automated in CI test flow.

Impact:
- SC-006 evidence is weaker than required for production confidence.

Files:
- `agent/tests/test_graph.py`
- `docs/learning-lessons/latencia_baseline.md`

Status: **High**

---

### MEDIUM-01 - Audio transient payload persistence pressure

Audio bytes are sent in state (`audio_data`) and transformed into `input_audio` message content. This increases pressure on context/checkpoint behavior and may conflict with "transient data should not persist beyond consumer node" intent.

Files:
- `agent-ui-pro/src/components/thread/index.tsx`
- `agent/agent/nodes/input_detector.py`
- `.specify/memory/constitution.md`

Status: **Medium**

---

### MEDIUM-02 - Performance success criteria evidence incomplete

Baseline and SC evidence still contain TBDs in historical/perf docs, so part of SC-004/005/006/008 remains not fully closed with objective measured deltas.

Files:
- `docs/learning-lessons/latencia_baseline.md`
- `specs/005-agent-hardening/spec.md`

Status: **Medium**

---

## Test Coverage Assessment

Strong areas:
- Retry/circuit breaker unit tests.
- Guardrail and PII middleware behavior.
- API validation, cache invalidation, and concurrency guard (double booking).

Gaps:
- No dedicated regression test for "old tool call must not trigger new email".
- No strict runtime test proving checkpoint write reduction in automated suite.
- No e2e assertion that agent log lines carry `request_id`.

---

## Security Assessment (Critical Focus)

Critical security-adjacent concerns:
- Duplicate patient notification risk (side effect integrity issue).
- TLS hardening TODO remains in DB connection (`rejectUnauthorized: false`) and should be treated as production hardening debt.

---

## Required Actions Before Approval

P0 (must fix before prod):
1. Patch `tool_result_processor` to guarantee same-turn matching only.
2. Add regression tests for duplicate-email prevention across turns.
3. Resolve Constitution VII compliance for agent state model.

P1 (strongly recommended before prod):
1. Add `request_id` propagation into agent structured logs.
2. Add runtime durability/write-count validation in automated verification flow.

P2 (next cycle acceptable with explicit risk acceptance):
1. Improve multimodal long-conversation perf/summarization validation.
2. Close remaining performance evidence TBDs with repeatable benchmark records.

---

## Final Gate Decision

**Spec 005 is not ready for production in current state.**  
Proceed only after P0 items are fixed and re-validated.
