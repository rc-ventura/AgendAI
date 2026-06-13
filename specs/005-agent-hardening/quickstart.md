# Quickstart — Validating Spec 005 Batches

This feature ships in **small batches** (one user story, or one Quick Win within US2). Each batch
follows the same loop, and **no commit happens until you approve**.

## The per-batch loop

```
1. Implement the batch (harness/API change + failing-first tests)
2. Run the suites locally
3. Present results for MANUAL VALIDATION  ◄── gate
4. You approve  ──► commit (+ ADR + learning-lesson)   |   You reject ──► iterate
```

## Standing commands

```bash
# Agent tests (70 baseline)
cd agent && uv run pytest --tb=short

# API tests (39 baseline, real Postgres)
export DATABASE_URL=postgres://agendai:agendai@localhost:5433/agendai_test
cd api && npm test

# Full stack up (manual smoke)
docker compose up --build -d   # UI at http://localhost:8080
```

## Per-batch validation

### B0 — Baseline + harness probe (read-only)
- Record P50/P99 for text + voice scenarios and durable-write count per turn (R1 protocol).
- Probe: does the managed server honor `durability` (R2) and `cache=` (R3)?
- **Validate**: a `latencia_baseline.md` learning-lesson exists with concrete numbers; R2/R3
  answered. **No production code committed** in B0.

### B1 — Parallel tool calls (US2/QW-1)
- **Validate**: a request needing 2+ lookups issues them concurrently (trace shows overlap);
  latency vs B0 baseline drops; 70 pytest green. → ADR-027 + lesson on approval.

### B2 — Reduce LLM rounds (US2/QW-4)
- **Validate**: standard scheduling resolves in ~2 rounds (trace); latency drop vs baseline;
  scheduling still correct (email gate, pt-BR rules intact). → ADR-027 update + lesson.

### B3 — Checkpoint exit/selective (US2/QW-3, harness)
- **Validate**: durable checkpoint rows/turn drop ≥80% (SC-006); conversation still resumes after
  restart; no email duplication. → extend ADR-025 + lesson.

### B4 — Redis node-output cache (US2/QW-7, harness)
- **Validate**: repeated `buscar_horarios` in one session served from cache (trace shows no
  re-exec); correctness unchanged. → extend ADR-025 + lesson. (Skip if R3 negative.)

### B5 — Audio model (US2/QW-6)
- **Validate**: voice transcription latency −≥50% (SC-007); pt-BR transcription quality acceptable
  on a fixed audio set. → ADR-028 + lesson.

### B6 — Retry + circuit breaker (US1/P1)
- **Validate**: the 5 outcomes in `contracts/resilience.md` (inject transient → masked; 3 fails →
  breaker pt-BR ≤1s; cold start → succeeds; 409 → no retry; suites green). → ADR-024 impl note.

### B7 — Guardrails (US3/P4)
- **Validate**: the 5 outcomes in `contracts/guardrail-decision.md` (injection blocked, off-scope
  refused, PII not logged, output redacted, corpus 100%/0). → ADR-029 (+ ADR-026 gate result).

### B8 — Context manager (US4/P6)
- **Validate**: 20+ turn conversation: no context-limit error, critical facts retained, latency
  stable; context within limit. → ADR-030 (+ ADR-026 gate result).

### B9 — Structured logs + correlation id (US5/P5)
- **Validate**: the 3 outcomes in `contracts/observability.md` (one id across nginx/API/agent;
  searchable in <5min; id on error lines). → ADR-031.

## Definition of done per batch

- [ ] Failing-first tests written, then passing
- [ ] 70 pytest + 39 Jest still green (FR-023)
- [ ] Manual validation outcomes met (contract/quickstart)
- [ ] **User approval received**
- [ ] ADR created/updated; learning-lesson created/updated
- [ ] Committed on `dev` (one batch = one commit)
