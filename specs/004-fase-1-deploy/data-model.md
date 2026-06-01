# Data Model: Phase 1 — Production Deploy

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Decisions**:
[research.md](./research.md) (D3–D6).

This phase **migrates the storage engine** for the existing domain model (SQLite →
Postgres) and **externalizes agent conversation state** to managed Postgres. The domain
entities and their relationships are unchanged; only types, identity generation, the
date filter, and the transaction mechanism change.

---

## A. API domain entities (Neon database `agendai_app`)

Relationships (unchanged):

```
medicos 1──* horarios 1──* agendamentos *──1 pacientes
pagamentos (standalone reference table)
```

### medicos
| Field | Type (Postgres) | Notes |
|---|---|---|
| id | `INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | was `INTEGER PK AUTOINCREMENT` |
| nome | `TEXT NOT NULL` | |
| especialidade | `TEXT NOT NULL` | |

### pacientes
| Field | Type | Notes |
|---|---|---|
| id | `INTEGER … IDENTITY PRIMARY KEY` | |
| nome | `TEXT NOT NULL` | |
| email | `TEXT NOT NULL UNIQUE` | natural key used by the LLM tools |
| telefone | `TEXT` | |

### horarios
| Field | Type | Notes |
|---|---|---|
| id | `INTEGER … IDENTITY PRIMARY KEY` | |
| medico_id | `INTEGER NOT NULL REFERENCES medicos(id)` | |
| data_hora | **`TEXT NOT NULL`** | ISO-8601 `"YYYY-MM-DDThh:mm:ss"`; kept as TEXT to preserve LLM/UI contract & ordering (D4) |
| disponivel | **`SMALLINT NOT NULL DEFAULT 1`** | 0/1; preserves `disponivel: 1` JSON and `WHERE disponivel = 1` (D4) |

### agendamentos
| Field | Type | Notes |
|---|---|---|
| id | `INTEGER … IDENTITY PRIMARY KEY` | |
| paciente_id | `INTEGER NOT NULL REFERENCES pacientes(id)` | |
| horario_id | `INTEGER NOT NULL REFERENCES horarios(id)` | |
| status | `TEXT NOT NULL DEFAULT 'ativo'` | `'ativo'` \| `'cancelado'` |
| criado_em | **`TIMESTAMPTZ NOT NULL DEFAULT now()`** | upgraded from TEXT (emit-only, safe) (D4) |

> Business rule (unchanged): appointments are never deleted; cancellation sets
> `status='cancelado'` and frees the slot (`horarios.disponivel = 1`).

### pagamentos
| Field | Type | Notes |
|---|---|---|
| id | `INTEGER … IDENTITY PRIMARY KEY` | |
| descricao | `TEXT NOT NULL` | |
| valor | **`NUMERIC(10,2) NOT NULL`** | was `REAL`; cast to Number on read if `pg` returns string (verify item D4) |
| formas | `TEXT NOT NULL` | JSON-encoded array string (unchanged) |

**Idempotency**: all tables created with `CREATE TABLE IF NOT EXISTS`; schema runs on every
startup (FR-007). Seed runs only when `SELECT count(*) FROM medicos = 0` (count-guard
preserved), so repeated startups do not duplicate rows.

---

## B. Validation rules (from requirements, unchanged behavior)

- `pacientes.email` unique; booking by unknown email → 404 (`Paciente não encontrado`).
- Booking a slot that is no longer available → 409 (`Horário não está mais disponível`),
  enforced by the atomic claim (Section D).
- Cancelling an already-cancelled appointment → 400; cancelling a missing one → 404.
- Date query param must match `YYYY-MM-DD` (validation middleware unchanged); the repo
  translates it to `left(data_hora, 10) = $1`.

---

## C. Agent conversation state (Neon database `agendai_lg`)

| Aspect | Detail |
|---|---|
| Owner | LangGraph Server (managed) — **not** application code |
| Storage | Postgres `agendai_lg` via `DATABASE_URI`; schema auto-created/migrated by the server |
| Contents | Threads, checkpoints, run state for the compiled graph `agendai_agent` |
| Streaming | Redis (`REDIS_URI`, Upstash) pub/sub for SSE token streaming (ephemeral) |
| Requirement satisfied | FR-006 — threads survive agent restarts (US2) |

No schema is defined or migrated by this repo for `agendai_lg`; the only contract is
supplying valid `DATABASE_URI` + `REDIS_URI` and not changing `graph.py`.

---

## D. Transaction & concurrency model (sync → async)

**Before (better-sqlite3)**: synchronous `db.transaction(() => { … })` closure;
`stmt.run().changes`, `stmt.run().lastInsertRowid`.

**After (pg)**: pooled client with explicit transaction control; `result.rowCount`,
`INSERT … RETURNING id`. Repository methods take an optional executor (`exec = pool`) so the
same method works standalone or inside a transaction (research D5).

Atomic booking (create) sequence:
1. `client = await pool.connect()`
2. `BEGIN`
3. `claimIfAvailable(horarioId, client)` → `UPDATE horarios SET disponivel = 0 WHERE id=$1 AND disponivel = 1` → `rowCount` must be 1, else `ROLLBACK` + throw 409.
4. `create(paciente.id, horarioId, 'ativo', client)` → `INSERT … RETURNING id`.
5. `COMMIT`; then `cache.delByPrefix('horarios')`; return `findById(newId)`.
6. On any error: `ROLLBACK`; always `client.release()`.

Cancel sequence (transactional): `updateStatus(id,'cancelado')` + `updateDisponivel(horario_id,1)` → `COMMIT` → `cache.delByPrefix('horarios')`.

**Concurrency invariant (preserved & strengthened)**: Postgres row locks serialize competing
`UPDATE … WHERE disponivel = 1` on the same slot. Two simultaneous bookings → exactly one
`rowCount=1` (201) and one `rowCount=0` (409). `concurrency.test.js`'s `[201, 409]` assertion
holds unchanged.

**Cache invariant (preserved)**: `cache.delByPrefix('horarios')` fires only after a successful
`COMMIT`, keeping availability reads consistent (FR-008).

---

## E. State transitions

```
horario.disponivel: 1 ──(booking commits)──> 0 ──(cancellation commits)──> 1
agendamento.status: (new) 'ativo' ──(cancel)──> 'cancelado'   [no further transitions]
```

---

## F. Test data lifecycle (real Postgres)

| Stage | Action |
|---|---|
| Test DB | Dedicated Postgres database via `DATABASE_URL` (local compose `postgres` or CI `postgres:16` service) |
| `beforeEach` | Reset: `DROP` (or `TRUNCATE … RESTART IDENTITY CASCADE`) → recreate schema → `seed` |
| `createTestApp()` | Async; `cache.clear()` then `createApp(pool)`; returns `{ app, pool }` |
| Serialization | `jest --runInBand` ensures one test touches the shared DB at a time |
| Seed parity | Same 3 médicos / 5 pacientes / 10 horários / 2 agendamentos / 1 pagamento as today |
