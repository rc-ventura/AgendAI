# Research & Decisions: Phase 1 — Production Deploy

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Guideline**: `docs/AgendAI_Architecture_Roadmap.pdf` (Phase 1; sections 02, 03, 06, 08).

All NEEDS CLARIFICATION items are resolved. Each decision below records **what** was
chosen, **why**, and **alternatives considered**.

---

## D1 — Agent persistence: official LangGraph Server image (Option B)

**Decision**: Run the agent on the official `langchain/langgraph-server` Docker image,
built via `langgraph build` from the existing `agent/langgraph.json`. Do **not** keep
`langgraph dev`.

**Rationale**:
- The server provides Postgres-backed checkpointing (persistent threads) and Redis-backed
  SSE pub/sub *out of the box* — directly resolving the in-memory-state gap (roadmap gap
  P2: "Sessão persistente"). No application code is written for persistence.
- `agent/agent/graph.py` already compiles with `builder.compile()` **without** a
  checkpointer, which is exactly what the server expects (the server injects its own).
  Zero graph changes.
- It is the documented production path (roadmap p.19: "langgraph build + Docker = deploy
  real no Render"; `langgraph dev` is "só local/dev").

**Alternatives considered**:
- *Keep `langgraph dev` + add `PostgresSaver` manually in `graph.py`* — more code, diverges
  from the supported server, loses managed SSE streaming via Redis.
- *Agent Engine Sessions (GCP)* — that is the Phase 3 managed option, out of scope now.

**Consequences**: Requires `DATABASE_URI` (Neon `agendai_lg`), `REDIS_URI` (Upstash),
`LANGSMITH_API_KEY` (license, mandatory for the server), `LANGCHAIN_API_KEY` (tracing),
`OPENAI_API_KEY`, `API_BASE_URL`. The server owns/migrates the `agendai_lg` schema.

---

## D2 — Server port = 8123

**Decision**: Treat the LangGraph Server port as **8123** and keep the nginx upstream at
`agent:8123`.

**Rationale**: The roadmap's "langgraph build + Docker" column lists **8123** as the default
port (p.19), the current `nginx.conf.template` already proxies to `agent:8123`, and CLAUDE.md
documents the agent on 8123. (The original plan note guessed 8000; the roadmap supersedes
it.)

**Verification hook**: Confirm the built image's listen port at first `docker compose up`;
if it differs, update the single `proxy_pass` upstream and the compose `depends_on` only.

---

## D3 — Data layer: `pg.Pool` async, no ORM

**Decision**: Replace `better-sqlite3` with the `pg` driver using a single `Pool`. Keep raw,
parametrized SQL (no ORM/query builder), mirroring the current repository style.

**Rationale**:
- `pg` is the de-facto Postgres driver for Node; async-only (no synchronous production-grade
  alternative).
- The codebase already hand-writes SQL in repositories; an ORM would be a larger, riskier
  change and violates the "Simplicity & Minimal Abstraction" principle.
- Neon requires TLS, but local/CI Postgres does not. SSL MUST be **conditional**: enable
  `ssl: { rejectUnauthorized: false }` only for remote/managed hosts (detect via
  `sslmode=require` or a non-local host; honor `PGSSLMODE=disable`). Forcing `ssl` against
  the CI `postgres:16` service or local docker Postgres breaks the connection.

**Alternatives considered**:
- *`better-sqlite3` on a Render disk* — rejected: Render's filesystem is ephemeral; the data
  would reset on redeploy (violates FR-005). DB-in-container is an anti-pattern on Render.
- *Prisma/Knex* — rejected: unnecessary abstraction; large diff; the team controls SQL today.

**Consequences**: Every repository/service/controller method becomes `async`; placeholders
change `?` → `$1…$n`; `db.prepare(...).get/all/run` → `await pool.query(text, params)` reading
`.rows` / `.rowCount`. Detailed in [contracts/data-migration.md](./contracts/data-migration.md).

---

## D4 — Schema dialect translation (contract-preserving)

**Decision**: Translate SQLite DDL to Postgres while **preserving the JSON wire contract**
the agent and UI depend on:

| Column / construct | SQLite (today) | Postgres (target) | Why |
|---|---|---|---|
| Primary keys | `INTEGER PRIMARY KEY AUTOINCREMENT` | `INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Standard SQL identity; `RETURNING id` replaces `lastInsertRowid` |
| `horarios.data_hora` | `TEXT` ISO-8601 (`"2026-05-13T09:00:00"`) | **`TEXT`** (unchanged) | Preserves exact string the LLM/UI parse; keeps natural lexicographic ordering |
| `agendamentos.criado_em` | `TEXT DEFAULT (datetime('now'))` | `TIMESTAMPTZ DEFAULT now()` | Real timestamp; serialized to ISO on read |
| `horarios.disponivel` | `INTEGER DEFAULT 1` | **`SMALLINT DEFAULT 1`** (0/1) | Keeps `disponivel: 1` in JSON and `WHERE disponivel = 1` queries unchanged; avoids boolean churn in repos/tests |
| `pagamentos.valor` | `REAL` | `NUMERIC(10,2)` | Money precision; cast to Number on read if needed |
| Date filter | `date(h.data_hora) = ?` | `left(h.data_hora, 10) = $1` | Equivalent day match on the ISO text without a date type |
| Idempotency | `CREATE TABLE IF NOT EXISTS` | `CREATE TABLE IF NOT EXISTS` | Startup stays idempotent (FR-007) |

**Rationale**: The roadmap suggests `TIMESTAMPTZ`/booleans generically, but spec **FR-008**
requires *functional equivalence* and the agent prompt + UI consume `data_hora` as an ISO
string and `disponivel` as `1`. Minimizing contract drift keeps the 39 Jest + 70 pytest
green and avoids touching the agent. `criado_em` is safe to upgrade because it is only
emitted, never parsed by clients.

**Alternatives considered**: Full `TIMESTAMPTZ` for `data_hora` + boolean `disponivel` —
rejected for this phase: forces value reformatting on every read and risks agent/UI parsing
regressions for no functional gain. Can revisit in a later phase if a date type is needed.

---

## D5 — Transaction model (atomic booking preserved)

**Decision**: For multi-statement atomic operations (create/cancel appointment), acquire a
client from the pool and run `BEGIN`/`COMMIT`/`ROLLBACK`. Repository methods accept an
**optional executor** argument defaulting to the pool:

```js
async function claimIfAvailable(id, exec = pool) {
  return exec.query(
    'UPDATE horarios SET disponivel = 0 WHERE id = $1 AND disponivel = 1', [id]);
}
```

Service:
```js
const client = await pool.connect();
try {
  await client.query('BEGIN');
  const claimed = await horariosRepo.claimIfAvailable(horarioId, client);
  if (claimed.rowCount === 0) { /* throw 409 */ }
  const ins = await agendamentosRepo.create(paciente.id, horarioId, 'ativo', client);
  await client.query('COMMIT');
  cache.delByPrefix('horarios');
  return formatAgendamento((await agendamentosRepo.findById(ins.rows[0].id)));
} catch (e) { await client.query('ROLLBACK'); throw e; }
finally { client.release(); }
```

**Rationale**: Mirrors the current `db.transaction(() => …)` closure semantics. Postgres
row-level locking on `UPDATE … WHERE disponivel = 1` makes the double-booking guard *stronger*
than SQLite's single-writer serialization: two concurrent bookings on the same slot → one
`rowCount=1` (201), the other blocks then sees `disponivel=0` → `rowCount=0` (409). The
existing `concurrency.test.js` assertion (`[201, 409]`) holds without change.

**Cache invariant**: `cache.delByPrefix('horarios')` is called **after** a successful commit,
exactly as today — preserving FR-008 cache consistency.

---

## D6 — Test strategy: real Postgres, drop+seed per test

**Decision**: Replace `:memory:` SQLite with a dedicated Postgres test database. `setup.js`
exposes an async `createTestApp()` that connects a test pool, and a reset routine
(`DROP`/recreate schema + `seed`) runs in `beforeEach`. Keep `jest --runInBand --forceExit`.

**Rationale**: Fulfills the project's "Test-First with **Real DB**" principle literally
(spec FR-011). `--runInBand` serializes tests so a single shared test DB is safe; per-test
drop+seed guarantees deterministic state (handles the "dirty DB" edge case). The
`cache.clear()` call in `createTestApp` is retained to prevent cross-test cache leakage.

**Local source of the test DB**: the dev `docker-compose` `postgres` service (or any local
Postgres) via `DATABASE_URL`. **CI source**: a `postgres:16` `services:` container.

**Alternatives considered**: `pg-mem` (in-memory JS Postgres) — rejected: not a real engine,
defeats the principle and can mask dialect bugs. Testcontainers — heavier; the GitHub Actions
service container is simpler and free.

---

## D7 — nginx as the single public edge (path routing)

**Decision**: Evolve `nginx.conf.template` from "everything → agent" into a path-routing
reverse proxy and make it the **only** service with a published/public port:
- `location /` → `agent-ui-pro:3002` (Next.js), including `/_next/...` static assets and
  WebSocket upgrade headers.
- `location ~ ^/(threads|runs|assistants|store|info)` → `langgraph-server:8123`, retaining
  the existing `x-api-key` auth, `limit_req` rate limiting, and `proxy_buffering off` SSE
  settings.
- Remove the `map $http_origin … CORS` block and `Access-Control-*` headers (same-origin).

**Rationale**: One controlled entry point is baseline production security (spec US4/FR-002/
FR-003); same-origin removes CORS complexity; reuses the already-validated auth/rate-limit/SSE
config instead of introducing a new gateway.

**Consequences**: Auth + rate limiting must be **scoped to the agent location only** — the UI
and its static assets must not require `x-api-key`. The current template applies auth at
`location /`; that block moves to the agent location.

**Verification**: Confirm the exact set of SDK paths (`@langchain/langgraph-sdk` calls
`/info`, `/threads`, `/runs`, `/assistants`, `/store`) and ensure the regex covers them.

---

## D8 — Managed providers (free tier)

**Decision**:
- **Neon** — one project, **two databases**: `agendai_app` (API `DATABASE_URL`) and
  `agendai_lg` (server `DATABASE_URI`). 0.5 GB free, no card.
- **Upstash Redis** — one instance for the server's `REDIS_URI` (10k cmd/day free). May be
  shared with future API cache (different key prefixes) but Phase 1 uses it only for the
  server SSE.
- **LangSmith Developer** — `LANGSMITH_API_KEY` (server license) + `LANGCHAIN_API_KEY`
  (tracing); 5k traces/mo free.

**Rationale**: All free-tier, twelve-factor (state lives outside the app as separate managed
services), avoids the Render DB-in-container anti-pattern.

**Edge handling**: A missing/invalid `DATABASE_URL`/`DATABASE_URI`/`REDIS_URI`/license must
fail fast at startup with a clear message (spec FR-016, edge cases) rather than degrade.

---

## D9 — CI/CD shape

**Decision**: Two workflows (roadmap section 02):
- `ci.yml` (on `push` + `pull_request`): `test-api` job (Node 20 + `postgres:16` service →
  `cd api && npm ci && npm test`) and `test-agent` job (`astral-sh/setup-uv` →
  `cd agent && uv run pytest --tb=short`). Branch protection on `main` requires both green.
- `deploy.yml` (on merge to `main`, after tests): build + push images to **GHCR**
  (`langgraph build` for the agent; `docker build` for api/nginx/agent-ui-pro), then trigger
  Render via deploy hook.

**Rationale**: Tests-as-gate is the headline portfolio signal (spec US3). GHCR keeps images
in the GitHub ecosystem alongside the repo. Render deploy hooks are the simplest trigger.

**Out of scope (deferred)**: the roadmap's "evaluate agent quality (Vertex AI)" gate step is
a Phase 3 item; Phase 1 gates on the unit/integration suites only.

---

## D10 — Secrets management

**Decision**: No secret values in the repo. Runtime secrets live in **Render env vars**; CI
secrets in **GitHub Secrets**. `.env` stays gitignored; `.env.example` is updated to list all
required keys (no values): `OPENAI_API_KEY`, `DATABASE_URL`, `DATABASE_URI`, `REDIS_URI`,
`LANGSMITH_API_KEY`, `LANGCHAIN_API_KEY`, `LANGGRAPH_AUTH_TOKEN`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD`, plus the GHCR token for CI.

**Rationale**: Spec FR-014/FR-015/FR-016 and the roadmap's "mover secrets para GitHub Secrets
+ Render env vars".

---

## D11 — LLM Gateway (LangSmith) — deferred to Phase 3

**Decision**: Do not adopt an LLM Gateway in Phase 1.

**Rationale**: It is managed-only and in private beta; not generally available. Recorded as a
strong Phase 3 candidate (PII redaction + spend cap within the LangSmith ecosystem, an
alternative to Bedrock Guardrails). No Phase 1 work.

---

## Open verification items (carried into tasks/quickstart)

1. Confirm LangGraph Server listen port from the built image (assume 8123; D2).
2. Confirm the complete set of SDK URL paths to cover in the nginx agent-location regex (D7).
3. Confirm Render free web services tolerate cold starts acceptably for the demo (D8).
4. Confirm `pagamentos.valor` `NUMERIC` returns as a JS number where the UI/agent expect it
   (cast in repo if `pg` returns a string) (D4).
