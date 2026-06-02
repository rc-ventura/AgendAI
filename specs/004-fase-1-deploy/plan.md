# Implementation Plan: Phase 1 — Production Deploy (Public URL, Managed State, CI Gate)

**Branch**: `004-fase-1-deploy` | **Date**: 2026-06-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-fase-1-deploy/spec.md`

**Guideline**: `docs/AgendAI_Architecture_Roadmap.pdf` — Phase 1 (Render + GitHub Actions).

## Summary

Take AgendAI from a local `docker compose` demo to a production-grade, portfolio-ready
deployment. Four moving parts, in order of effort:

1. **Data layer migration (largest effort)** — replace the synchronous `better-sqlite3`
   file store with an asynchronous `pg.Pool` against managed Postgres (Neon). The whole
   call chain (repositories → services → controllers → app/server startup) becomes
   `async`, placeholders move from `?` to `$1…$n`, and the in-memory test DB is replaced
   by a real Postgres test database (drop+seed per test).
2. **Agent as managed LangGraph Server (Option B)** — stop running `langgraph dev` and
   run the official `langchain/langgraph-server` image built via `langgraph build`. It
   brings Postgres-backed checkpointing (persistent threads, resolving the in-memory
   state gap) and Redis-backed SSE streaming out of the box, with **no change to
   `agent/agent/graph.py`** (it already compiles without a checkpointer).
3. **nginx as the single public edge** — evolve the existing gateway into a path-routing
   reverse proxy: `/` → `agent-ui-pro` (Next.js, private), `/threads|/runs|/assistants|…`
   → `langgraph-server` (private), keeping the existing `x-api-key` auth, rate limiting,
   and SSE buffering-off. API and agent become private (no public route). CORS is dropped
   (same-origin).
4. **CI/CD gate (GitHub Actions)** — `ci.yml` runs the full Jest + pytest suites against a
   real Postgres service on every PR and blocks merge on failure; `deploy.yml` builds and
   pushes images to GHCR and triggers a Render deploy on merge to `main`. Secrets move to
   GitHub Secrets + Render env vars.

Stateful dependencies are **managed, not containerized in production**: Neon Postgres (two
logical DBs — `agendai_app` for API data, `agendai_lg` for agent state), Upstash Redis,
and LangSmith. Local `docker-compose` adds throwaway `postgres` + `redis` containers only
for dev parity.

## Technical Context

**Language/Version**: Node.js 20 (API) · Python 3.11 (agent) · TypeScript 5 / Next.js 14
(UI) — unchanged.

**Primary Dependencies**:
- API: Express 4, **`pg` (replaces `better-sqlite3`)**, `node-cache`, `express-rate-limit`,
  `pino`.
- Agent: LangGraph ≥1.0 graph (unchanged) run under the `langchain/langgraph-server` image
  (built with `langgraph-cli` / `langgraph build`).
- UI: `@langchain/langgraph-sdk` (unchanged).
- Infra: nginx (existing template, re-routed), Render Blueprint (`render.yaml`), GitHub
  Actions, GHCR.

**Storage**: Managed PostgreSQL (Neon) — two databases: `agendai_app` (API domain data) and
`agendai_lg` (LangGraph Server checkpoints/threads, schema self-managed by the server).
Managed Redis (Upstash) for the LangGraph Server SSE pub/sub. `node-cache` (in-process TTL)
stays for API availability caching.

**Testing**: Jest + Supertest (API) against a **real Postgres** test database; pytest +
respx (agent) unchanged. CI provides Postgres via a `services:` container.

**Target Platform**: Render (Docker + Node web services) as the compute host; browsers as
clients. Single public HTTPS endpoint (nginx).

**Project Type**: Multi-service web application (API + agent + UI + gateway) + infra/CI.

**Performance Goals**: Streaming latency and scheduling round-trip perceived as equivalent
to the current local stack; no functional regression in availability/booking/cancel flows.

**Constraints**:
- Free-tier budgets: Neon 0.5 GB, Upstash 10k cmd/day, LangSmith Developer 5k traces/mo,
  Render free web services (cold-start after 15 min idle acceptable for portfolio).
- LangGraph Server **requires** `DATABASE_URI` + `REDIS_URI` + `LANGSMITH_API_KEY` (license)
  — it provisions/manages its own schema in `agendai_lg`.
- `NEXT_PUBLIC_*` are baked at UI build time → `NEXT_PUBLIC_API_URL` must be the public
  nginx origin (same-origin).
- The API's `data_hora` ISO-8601 string contract and JSON shapes consumed by the agent/UI
  MUST be preserved across the Postgres migration (see research.md "dialect" decision).
- LangGraph Server listens on **port 8123** in the built image (matches the existing
  `nginx` upstream `agent:8123` and CLAUDE.md); confirm against the built image and keep
  the nginx upstream in sync.

**Scale/Scope**: Portfolio / demo scale — low concurrency, single region. No multi-tenancy.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is ratified (v1.1.0). All six principles are evaluated below:

| Principle | Applies? | Status | Notes |
|-----------|----------|--------|-------|
| I. Layered Architecture | **Yes** | ✅ Pass | The routes→controllers→services→repositories layering is preserved; the migration changes each layer's *implementation* (sync→async) but not the boundaries or DI seams. |
| II. Test-First with Real DB | **Yes** | ✅ **Strengthened** | This phase *finally* makes "Real DB" literally true: tests move from `:memory:` SQLite to a real Postgres engine. Migration is test-guarded — the existing 39 Jest + 70 pytest must stay green. |
| III. Stateless Services via DI | **Yes** | ✅ Pass | `createApp(db)` becomes `createApp(pool)`; `createConnection(connStr)` still enables test injection. App/agent/nginx remain stateless containers; all state externalized to managed services (twelve-factor). |
| IV. Observability & Cache Consistency | **Yes** | ✅ Pass | `node-cache` `delByPrefix('horarios')` invalidation is retained verbatim around the new async transactions. LangSmith tracing is wired in production (FR-018). |
| V. Simplicity & Minimal Abstraction | **Yes** | ✅ Pass | Reuse the official LangGraph Server image instead of hand-rolling persistence; evolve the existing nginx rather than introducing a new gateway; no ORM (raw `pg` parametrized SQL, matching the current raw-SQL style). |
| VI. Security & Data Protection | **Yes** | ✅ Pass | Single public edge (nginx); API + agent become private services (FR-003, US4). Gateway auth fails closed; rate limiting + SSE retained (FR-004). Secrets externalized to Render/GitHub, never committed; missing secret fails fast (FR-014/016). Input validation middleware retained. Input guardrails on agent traffic remain a Phase 3/4 hardening item (out of scope here, tracked). |

**Tech Stack Constraint**: The constitution/CLAUDE.md describe SQLite (`better-sqlite3`).
This feature intentionally supersedes that for the data layer (SQLite → Postgres) as the
explicit Phase 1 production decision. CLAUDE.md and `.env.example` are updated as part of
this work. This is a *documented, approved* deviation, not an unjustified one.

**Complexity Tracking**: No violations requiring justification. The single largest source
of churn (sync→async across the API) is inherent to the chosen production-grade datastore,
not added abstraction; see Complexity Tracking table below.

## Project Structure

### Documentation (this feature)

```text
specs/004-fase-1-deploy/
├── plan.md              ← this file
├── spec.md              ← feature spec
├── research.md          ← Phase 0: decisions (Option B, sync→async, Neon/Upstash/LangSmith, port, dialect)
├── data-model.md        ← Phase 1: schema translation + entities + transaction model
├── quickstart.md        ← Phase 1: end-to-end deploy + local run + verification
├── contracts/
│   ├── data-migration.md   ← better-sqlite3 → pg translation contract (per-layer rules)
│   ├── render-blueprint.md ← render.yaml service topology + env var matrix
│   └── ci-cd.md            ← ci.yml + deploy.yml workflow contracts
├── checklists/
│   └── requirements.md     ← spec quality checklist (from /speckit-specify)
└── tasks.md             ← Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code Layout (repository root)

```text
api/
├── package.json                 ← MODIFIED: −better-sqlite3, +pg
├── src/
│   ├── db/
│   │   ├── connection.js         ← MODIFIED: pg.Pool singleton; getPool()/createConnection(connStr); async schema run
│   │   ├── schema.sql            ← MODIFIED: SQLite → Postgres dialect (IDENTITY, TIMESTAMPTZ, idempotent)
│   │   └── seed.js               ← MODIFIED: async + pooled INSERTs; count-guard preserved
│   ├── repositories/*.js         ← MODIFIED: async + await pool.query; $n placeholders; RETURNING id; rowCount
│   ├── services/*.js             ← MODIFIED: await repo calls; BEGIN/COMMIT/ROLLBACK via pooled client for transactions
│   ├── controllers/*.js          ← MODIFIED: await service calls
│   ├── cache/index.js            ← UNCHANGED
│   ├── middlewares/*             ← UNCHANGED (errorHandler, requestLogger, validation)
│   ├── app.js                    ← MODIFIED: createApp(pool)
│   └── server.js                 ← MODIFIED: async startup — schema + seed before listen()
└── tests/
    ├── setup.js                  ← MODIFIED: async createTestApp() against real Postgres; reset (drop+seed) helper
    └── *.test.js                 ← MODIFIED: await setup; beforeEach reset; same assertions

agent/
├── langgraph.json                ← UNCHANGED (env from Render in prod)
├── Dockerfile                    ← REPLACED conceptually: built via `langgraph build` (CI) → langgraph-server image
└── agent/graph.py                ← UNCHANGED (compiles without checkpointer)

agent-ui-pro/
└── (build args)                  ← NEXT_PUBLIC_API_URL = public nginx origin (same-origin); becomes private service

nginx/
└── nginx.conf.template           ← MODIFIED: path routing / → UI, /threads|… → langgraph-server; auth+rate-limit scoped to agent paths; CORS removed

infra/render/
└── render.yaml                   ← NEW: Blueprint (nginx public; api + langgraph-server + agent-ui-pro private)

.github/workflows/
├── ci.yml                        ← NEW: test gate (Jest+Postgres service, pytest)
└── deploy.yml                    ← NEW: build+push GHCR → Render deploy hook

docker-compose.yml                ← MODIFIED: + local postgres/redis; agent → langgraph-server image; only nginx publishes a port
.env.example                      ← MODIFIED: add DATABASE_URL/DATABASE_URI/REDIS_URI/LANGSMITH_API_KEY; document new topology
README.md                         ← MODIFIED: CI badge, production URL, LangSmith screenshot
CLAUDE.md                         ← MODIFIED: SQLite→Postgres, port/topology notes
```

**Structure Decision**: Keep the existing four-component layout; no new app directories
except `infra/render/` and `.github/workflows/`. The migration is in-place per layer to
keep diffs reviewable and the layering intact.

## Phase 0: Research ✅ Complete

See [research.md](./research.md). Decisions locked:

- **Agent persistence = Option B** (official `langgraph-server` image; graph unchanged).
- **Data layer = `pg.Pool` async** (no ORM; parametrized raw SQL mirroring current style).
- **`data_hora` stays TEXT (ISO-8601)**; `criado_em` → `TIMESTAMPTZ DEFAULT now()`;
  `disponivel` stays integer (`0/1`) to preserve the API/agent JSON contract and minimize
  test churn. Date filter `date(data_hora)=?` → `left(data_hora,10)=$1`.
- **Transactions** use a pooled client (`BEGIN`/`COMMIT`/`ROLLBACK`); repository methods
  accept an optional executor (`pool` or transaction `client`) so atomic
  `claimIfAvailable` still prevents double-booking (now via Postgres row locks).
- **Tests = real Postgres**, drop+seed per test, `--runInBand` for serialization; CI uses a
  `postgres:16` service container.
- **Managed providers**: Neon (2 DBs), Upstash Redis, LangSmith Developer.
- **LangGraph Server port = 8123** (per roadmap; matches existing nginx upstream).
- **LLM Gateway deferred** to Phase 3 (managed-only, private beta).

## Phase 1: Design ✅ Complete

Artifacts generated:
- [data-model.md](./data-model.md) — Postgres schema, entity definitions, sync→async
  transaction model, cache-invalidation invariants.
- [contracts/data-migration.md](./contracts/data-migration.md) — exact per-layer
  translation rules (`better-sqlite3` API → `pg` API).
- [contracts/render-blueprint.md](./contracts/render-blueprint.md) — Render service
  topology, public/private matrix, env var table.
- [contracts/ci-cd.md](./contracts/ci-cd.md) — `ci.yml` + `deploy.yml` contracts, branch
  protection, GHCR.
- [quickstart.md](./quickstart.md) — prerequisites, local run, deploy, 6-step end-to-end
  verification.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|------------|--------------------------------------|
| Full sync→async refactor across API layers | Managed Postgres driver (`pg`) is async-only; no synchronous production-grade Postgres client exists for Node | Keeping `better-sqlite3` rejected: file store is ephemeral on Render and not the production target (spec FR-005) |
| Repository methods accept optional executor (pool/client) | Atomic booking transaction must span multiple statements on one connection | Per-statement autocommit rejected: breaks the double-booking guard (concurrency.test.js) |
| Two Neon databases (`agendai_app`, `agendai_lg`) | LangGraph Server manages its own schema; mixing with API tables risks collisions | Single shared DB rejected: server migrations could clash with API schema; isolation is cleaner and free |
