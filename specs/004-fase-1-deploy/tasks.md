---
description: "Task list for Phase 1 — Production Deploy (Render + GitHub Actions)"
---
# Tasks: Phase 1 — Production Deploy (Public URL, Managed State, CI Gate)

**Input**: Design documents from `specs/004-fase-1-deploy/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅
(data-migration.md, render-blueprint.md, ci-cd.md), quickstart.md ✅

**Tests**: INCLUDED. Automated tests are a core deliverable of this feature (US3 — "broken
changes cannot be deployed", FR-009/011). The work is **test-guarded**: the existing 39 Jest +
70 pytest suites are the regression gate for the SQLite→Postgres migration and must stay green.

**Organization**: Tasks grouped by user story for independent implementation/testing. Because
this is an infrastructure feature, the data-layer migration is **foundational** (it blocks the
deploy, the persistence guarantee, and the real-DB test gate alike).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Obtain managed dependencies and swap the data-layer dependency.

- [X] T001 Provision managed dependencies (record connection strings into a local untracked `.env`): Neon project with two databases `agendai_app` → `DATABASE_URL` and `agendai_lg` → `DATABASE_URI`; Upstash Redis → `REDIS_URI`; LangSmith Developer → `LANGSMITH_API_KEY` (license) + `LANGCHAIN_API_KEY` (tracing). Reference `specs/004-fase-1-deploy/contracts/render-blueprint.md`
- [X] T002 [P] In `api/package.json`, remove `better-sqlite3` and add `pg` (`^8`); keep all other deps
- [X] T003 [P] Update `.env.example` to add `DATABASE_URL`, `DATABASE_URI`, `REDIS_URI`, `LANGSMITH_API_KEY` and document the new topology; keep existing keys (`OPENAI_API_KEY`, `LANGCHAIN_*`, `GMAIL_*`, `LANGGRAPH_AUTH_TOKEN`, `API_BASE_URL`)
- [X] T004 [P] Confirm `.env` is gitignored (it is, line 2) and add a local Postgres for dev/test by appending `postgres:16` + `redis` services to `docker-compose.yml` (dev-parity only; expose Postgres on `5432` locally for the test runner)

**Checkpoint**: `pg` installed; managed creds available; a local Postgres reachable via `DATABASE_URL`.

---

## Phase 2: Foundational — SQLite → Postgres data-layer migration (Blocking Prerequisites)

**Purpose**: Convert the entire API data layer from synchronous `better-sqlite3` to async
`pg.Pool`. This blocks **every** user story: the deploy (US1) needs a managed DB, persistence
(US2) needs durable storage, and the CI gate (US3) runs the suite against real Postgres.

**⚠️ CRITICAL**: No user-story work begins until all 39 Jest tests pass against Postgres (T020).

**Contract**: Apply `specs/004-fase-1-deploy/contracts/data-migration.md` mechanically. The HTTP
status codes and JSON shapes MUST NOT change.

- [X] T005 Rewrite `api/src/db/schema.sql` to Postgres dialect per data-model.md §A: `INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY`, keep `horarios.data_hora` as `TEXT` and `horarios.disponivel` as `SMALLINT DEFAULT 1`, `agendamentos.criado_em` as `TIMESTAMPTZ DEFAULT now()`, `pagamentos.valor` as `NUMERIC(10,2)`; keep all `CREATE TABLE IF NOT EXISTS` (idempotent)
- [X] T006 Rewrite `api/src/db/connection.js`: replace `better-sqlite3` with `pg.Pool`; export `getPool()` (singleton on `DATABASE_URL`, fail-fast if missing), `createConnection(connStr)` with **conditional SSL** (enable `{ rejectUnauthorized: false }` only for remote/managed hosts — Neon; disable for local/CI Postgres and honor `PGSSLMODE=disable`, per data-migration.md §2), and `async initSchema(pool)` that runs `schema.sql`
- [X] T007 Rewrite `api/src/db/seed.js` to `async function seed(pool)`: count-guard via `SELECT count(*)::int AS n FROM medicos`, wrap inserts in a `BEGIN/COMMIT` client transaction, use `INSERT … RETURNING id`, preserve the exact seed data and the local-time `formatLocalDate` weekday logic
- [X] T008 [P] Migrate `api/src/repositories/horariosRepository.js` to async + `$n` + optional `exec = pool`; `claimIfAvailable` returns result (`rowCount`); `findAvailableByDate` uses `left(h.data_hora,10) = $1`
- [X] T009 [P] Migrate `api/src/repositories/agendamentosRepository.js` to async + `$n` + optional `exec`; `create` uses `RETURNING id`; read `.rows`/`.rows[0]`
- [X] T010 [P] Migrate `api/src/repositories/pacientesRepository.js` to async + `$n` + optional `exec`
- [X] T011 [P] Migrate `api/src/repositories/pagamentosRepository.js` to async + `$n` + optional `exec`; **explicitly cast `valor` to Number** on read (`pg` returns `NUMERIC` as a string) so the JSON contract stays numeric (research D4)
- [X] T012 [P] Migrate `api/src/repositories/painelRepository.js` to async + `$n` + optional `exec`
- [X] T013 Migrate `api/src/services/agendamentosService.js`: `async`; replace `db.transaction(() => …)` with pooled-client `BEGIN/COMMIT/ROLLBACK` for `criarAgendamento` and `cancelarAgendamento` per data-migration.md §4; `claimed.rowCount === 0` → 409; `cache.delByPrefix('horarios')` stays **after** commit
- [X] T014 [P] Migrate `api/src/services/horariosService.js` to async (await repo calls)
- [X] T015 [P] Migrate `api/src/services/pacientesService.js` to async
- [X] T016 [P] Migrate `api/src/services/pagamentosService.js` to async
- [X] T017 [P] Migrate `api/src/services/painelService.js` to async
- [X] T018 Add `await` before every service call in all controllers: `api/src/controllers/{agendamentos,horarios,pacientes,pagamentos,painel}Controller.js` (already `async function`; keep `next(err)` flow)
- [X] T019 Update `api/src/app.js` (`createApp(pool)`) and `api/src/server.js` (async startup: `await initSchema(pool)` then `await seed(pool)` **before** `app.listen`; fail-fast `process.exit(1)` on startup error). Verify the fail-fast path: starting with `DATABASE_URL` unset exits with a clear message, not a hang or partial boot (FR-016)
- [X] T020 Migrate the test harness in `api/tests/setup.js`: async `createTestApp()` against `DATABASE_URL`, add `resetDb(pool)` (DROP CASCADE → `initSchema` → `seed`), `cache.clear()`, return `{ app, pool }`; close pool in shared `afterAll`
- [X] T021 [P] Update `api/tests/agendamentos.test.js` to `await createTestApp()` in `beforeEach`; assertions unchanged
- [X] T022 [P] Update `api/tests/horarios.test.js` to async setup
- [X] T023 [P] Update `api/tests/pacientes.test.js` to async setup
- [X] T024 [P] Update `api/tests/pagamentos.test.js` to async setup; add an assertion that `valor` is a `number` (not a string) to guard the `NUMERIC` cast from T011
- [X] T025 [P] Update `api/tests/cache.test.js` to async setup
- [X] T026 [P] Update `api/tests/validation.test.js` to async setup
- [X] T027 [P] Update `api/tests/concurrency.test.js` to async setup; confirm the Postgres row-lock path still yields exactly `[201, 409]`
- [X] T028 Run `cd api && DATABASE_URL=… npm test` and make all **39 Jest tests pass** against real Postgres; grep `api/src` to confirm no `better-sqlite3` import and no `?`/`.prepare(`/`.get(`/`.all(`/`.run(` remain

- [X] T028b [P] Confirm the agent baseline is unaffected by the migration: `cd agent && uv run pytest --tb=short` → all 70 tests pass (the migration touches only the API; this is a sanity check before the CI gate relies on it)

**Checkpoint**: API runs on Postgres locally; full Jest suite (39) + agent suite (70) green. Foundation ready.

---

## Phase 3: User Story 1 — Reach AgendAI at a Public URL (Priority: P1) 🎯 MVP

**Goal**: A first-time visitor opens one public HTTPS URL and completes a full scheduling
conversation (text + audio) with streaming — no local setup.

**Independent Test**: From a clean machine, open the public URL, complete a text and an audio
scheduling flow end to end; confirm an appointment + confirmation (quickstart.md check #1).

**Depends on**: Phase 2.

### Agent as managed LangGraph Server (Option B)

- [X] T029 [US1] Replace `agent/Dockerfile`'s `langgraph dev` approach: produce the server image via `langgraph build` (the image embeds the graph from `agent/langgraph.json`); verify the built image listens on **8123** (research D2) and document the exact build command
- [X] T030 [US1] Verify `agent/langgraph.json` graph id `agendai_agent` and entrypoint `./agent/graph.py:graph` are correct; confirm `agent/agent/graph.py` still compiles **without** a checkpointer (no code change expected)

### Single-edge nginx routing + local production-parity stack

- [X] T031 [US1] Rewrite `nginx/nginx.conf.template` into a path-routing reverse proxy: `location /` → `agent-ui-pro:3002` (incl. `/_next/...` and WebSocket upgrade); `location ~ ^/(threads|runs|assistants|store|info)` → `langgraph-server:8123` keeping `x-api-key` auth + `limit_req` + `proxy_buffering off`; **scope auth/rate-limit to the agent location only** (UI/assets unauthenticated); remove the `map $http_origin`/CORS block (research D7)
- [X] T032 [US1] Update `docker-compose.yml`: swap the `agent` build for the `langgraph-server` image with env `DATABASE_URI`/`REDIS_URI`/`LANGSMITH_API_KEY`/`LANGCHAIN_API_KEY`/`OPENAI_API_KEY`/`API_BASE_URL`; point `api` at local `postgres` via `DATABASE_URL`; make **nginx the only service publishing a host port**; `agent-ui-pro` and `langgraph-server` no longer publish ports
- [X] T033 [US1] Set `agent-ui-pro` build arg `NEXT_PUBLIC_API_URL` to the nginx origin (same-origin); keep `NEXT_PUBLIC_ASSISTANT_ID=agendai_agent` and `NEXT_PUBLIC_LANGGRAPH_API_KEY=${LANGGRAPH_AUTH_TOKEN}`
- [X] T034 [US1] Local verify: `docker compose up --build -d` brings up api + postgres + redis + langgraph-server + nginx + agent-ui-pro; open the app through nginx; complete a text and an audio scheduling flow; confirm streaming is not buffered (quickstart.md §1)

### Render deploy

- [X] T035 [US1] Create `infra/render/render.yaml` Blueprint per `contracts/render-blueprint.md`: `nginx` public; `api`, `langgraph-server`, `agent-ui-pro` private; correct ports and `sync:false` env keys
- [X] T036 [US1] Add `infra/render/README.md` documenting how to create Neon (2 DBs) + Upstash + LangSmith and paste secrets into Render
- [X] T037 [US1] Deploy the Blueprint to Render; set all `sync:false` env vars; set `agent-ui-pro` build args (`NEXT_PUBLIC_API_URL` = public nginx URL); confirm first boot creates the API schema+seed in `agendai_app` and the server schema in `agendai_lg`
- [X] T038 [US1] Public end-to-end verify from a clean machine: open the public URL, complete a text + audio scheduling flow, confirm appointment + confirmation (SC-001)

**Checkpoint**: Public URL serves a working AgendAI end to end. MVP delivered.

---

## Phase 4: User Story 2 — Conversations and Data Survive Restarts (Priority: P1)

**Goal**: Appointments and in-progress conversation threads survive backend restarts/redeploys.

**Independent Test**: Create an appointment + start a thread; restart `langgraph-server` (and
redeploy `api`); reopen the thread and re-query the appointment — both survive (quickstart §5 #2).

**Depends on**: Phase 2 (durable API data) + T029/T032 (server-backed checkpointer).

- [X] T039 [US2] Confirm idempotent startup: redeploy/restart `api` and verify schema runs without error and seed does **not** duplicate rows (count-guard) (FR-007)
- [X] T040 [US2] Local persistence test: with `docker compose` up, create an appointment and an in-progress thread; `docker compose restart langgraph-server`; reopen the thread → prior messages intact; re-query the appointment → still present (validates Postgres checkpointer, gap P2)
- [X] T041 [US2] Production persistence test: trigger a Render redeploy of `api` + `langgraph-server`; confirm previously created appointments remain retrievable and an active thread still shows prior messages (SC-002)

**Checkpoint**: State durability proven locally and in production.

---

## Phase 5: User Story 3 — Broken Changes Cannot Be Deployed (Priority: P1)

**Goal**: Every PR runs the full suite against real Postgres; failures block merge; passing
merges auto-deploy.

**Independent Test**: Open a PR with a deliberately failing test → CI red blocks merge; fix →
green unblocks (quickstart §5 #4).

**Depends on**: Phase 2 (Postgres test harness). `deploy.yml` additionally depends on T035 (render.yaml).

- [X] T042 [US3] Create `.github/workflows/ci.yml` per `contracts/ci-cd.md`: `test-api` job with a `postgres:16` service + `DATABASE_URL` → `cd api && npm ci && npm test`; `test-agent` job with `astral-sh/setup-uv` → `cd agent && uv run pytest --tb=short`; triggers on `push` + `pull_request`
- [X] T043 [US3] Create `.github/workflows/deploy.yml` per `contracts/ci-cd.md`: on push to `main`, log in to GHCR, `langgraph build` + push the agent image, `docker build` + push `api`/`nginx`/`agent-ui-pro`, then `curl` the `RENDER_DEPLOY_HOOK`
- [X] T044 [US3] Add GitHub secret `RENDER_DEPLOY_HOOK` (Render deploy hook URL); confirm GHCR `packages: write` permission is granted to the workflow
- [X] T045 [US3] Enable branch protection on `main` requiring `test-api` + `test-agent` to pass before merge (FR-010)
- [X] T046 [US3] Verify the gate: open a PR with a deliberately failing test → CI red, merge blocked; revert the break → CI green, merge allowed; confirm merge to `main` runs `deploy.yml` and the public URL serves the new build (SC-003, SC-004)

**Checkpoint**: Tests gate every change; passing merges auto-deploy.

---

## Phase 6: User Story 4 — Single Secure Public Entry Point (Priority: P2)

**Goal**: Only nginx is reachable publicly; api/agent are private; auth + rate-limit + SSE
enforced at the agent path.

**Independent Test**: Public URL serves UI + agent; api/langgraph-server have no public route
(quickstart §5 #7).

**Depends on**: T031 (nginx routing), T035 (render private services).

- [X] T047 [US4] Verify in `infra/render/render.yaml` that `api`, `langgraph-server`, and `agent-ui-pro` are private (no public URL) and only `nginx` is public; fix any service type that exposes a public route
- [X] T048 [US4] Verify auth scoping: requesting the UI/static assets through nginx needs no `x-api-key`, while agent paths (`/threads`,`/runs`,…) require it and are rate-limited; confirm SSE streams unbuffered (FR-004)
- [X] T049 [US4] Attempt to reach `api` and `langgraph-server` directly from the public internet and confirm there is no route (SC-007); confirm same-origin works with the CORS block removed

**Checkpoint**: Public surface reduced to the single gateway, verified.

---

## Phase 7: User Story 5 — Observable Production Behavior (Priority: P3)

**Goal**: Production conversations produce viewable LangSmith traces including tool calls.

**Independent Test**: Complete a production conversation and confirm a trace with tool calls in
LangSmith (quickstart §5 #6).

**Depends on**: Phase 3 (agent deployed).

- [X] T050 [US5] Confirm tracing env on the deployed `langgraph-server`: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=AgendAI` (render-blueprint.md)
- [X] T051 [US5] Run a production conversation; confirm a trace including the agent's tool calls appears in the LangSmith dashboard; capture a screenshot for the README (SC-008, FR-018)

**Checkpoint**: Production behavior is observable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Secrets finalization, documentation, and cleanup spanning all stories.

- [X] T052 [P] Finalize secrets migration: confirm no secret values are committed anywhere added by this feature; all runtime secrets live in Render env vars and all CI secrets in GitHub Secrets (FR-014/SC-006)
- [X] T053 [P] Update `README.md`: CI status badge (green), production URL, and the LangSmith traces screenshot from T051 (FR-019)
- [X] T054 [P] Update `CLAUDE.md` body to reflect SQLite→Postgres (`pg`), the LangGraph Server (Option B) topology, nginx single-edge routing, and the new env vars (the SPECKIT plan pointer is already set)
- [X] T055 [P] Remove dead references to `better-sqlite3`/`DB_PATH`/SQLite from docs and any leftover comments; ensure `.env.example` matches the deployed env matrix exactly
- [X] T056 Run the full `quickstart.md` verification table (checks #1–#7) end to end and confirm every Success Criterion (SC-001…SC-009) is met

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup (needs `pg` + a local Postgres). **BLOCKS all user stories.**
- **US1 (Phase 3)**: depends on Phase 2. Delivers the public deploy (MVP).
- **US2 (Phase 4)**: depends on Phase 2 + T029/T032 (server-backed state). Largely verification.
- **US3 (Phase 5)**: `ci.yml` depends only on Phase 2; `deploy.yml` (T043+) also depends on T035 (render.yaml).
- **US4 (Phase 6)**: depends on T031 + T035.
- **US5 (Phase 7)**: depends on Phase 3 (agent deployed).
- **Polish (Phase 8)**: depends on the targeted stories being complete.

### User Story Independence

- **US3's CI gate** is independently testable as soon as Phase 2 is green — it does not require the deploy to validate the red/green merge gate (only the auto-deploy step does).
- **US2** is independently testable **locally** (docker compose restart) without Render.
- **US4** is a property of the deployed topology and can be validated against either the local stack (auth scoping, same-origin) or Render (no public route).

### Within Foundational (Phase 2)

- Order: schema (T005) → connection (T006) → seed (T007) → repositories (T008–T012) → services (T013–T017) → controllers (T018) → app/server (T019) → test harness (T020) → test files (T021–T027) → green gate (T028).
- Repositories T008–T012 are `[P]` (different files). Services T014–T017 are `[P]` (T013 is the transactional one). Test files T021–T027 are `[P]`.

---

## Parallel Example: Foundational repositories

```bash
# After T005–T007, launch the five repository migrations together:
Task: "Migrate api/src/repositories/horariosRepository.js (T008)"
Task: "Migrate api/src/repositories/agendamentosRepository.js (T009)"
Task: "Migrate api/src/repositories/pacientesRepository.js (T010)"
Task: "Migrate api/src/repositories/pagamentosRepository.js (T011)"
Task: "Migrate api/src/repositories/painelRepository.js (T012)"
```

## Parallel Example: Foundational test files

```bash
# After T020 (setup.js), update all test files in parallel:
Task: "T021 api/tests/agendamentos.test.js"
Task: "T022 api/tests/horarios.test.js"
Task: "T023 api/tests/pacientes.test.js"
Task: "T024 api/tests/pagamentos.test.js"
Task: "T025 api/tests/cache.test.js"
Task: "T026 api/tests/validation.test.js"
Task: "T027 api/tests/concurrency.test.js"
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 Setup → Phase 2 Foundational (Postgres migration; **39 Jest green** at T028).
2. Phase 3 US1: agent as LangGraph Server + nginx single-edge + local parity (T034 checkpoint) → Render deploy (T038).
3. **STOP and VALIDATE**: public URL completes a scheduling flow. Demo-ready.

### Incremental Delivery

1. Foundation green → US1 deployed (MVP) → US2 persistence proven → US3 CI gate live → US4 security hardening → US5 observability → Polish.
2. Each story adds value without breaking prior ones.

### Risk note

The single largest risk is the sync→async migration (Phase 2). It is fully guarded by the
existing 39 Jest tests; do not proceed to any user story until T028 is green. The agent graph
and the 70 pytest tests are untouched by the migration.

---

## Notes

- `[P]` = different files, no dependency on incomplete tasks.
- `[Story]` labels (US1–US5) map tasks to spec user stories for traceability.
- Tests here are migration-guarding (keep existing suites green) + gate-verification, not new TDD.
- Commit after each task or logical group; stop at any checkpoint to validate independently.
- Confirm verification items from research.md (server port, SDK path set, NUMERIC casting) during T029/T031/T011.
- Spec edge cases **"free-tier limit reached"** and **"deploy triggered while a previous deploy is in flight"** are handled natively by the managed providers (Neon/Upstash quotas surface errors; Render serializes deploys and the latest successful build wins). No dedicated task; observe via LangSmith/Render dashboards (US5). Revisit if a quota becomes a real constraint.
