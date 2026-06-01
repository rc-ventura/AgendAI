# Quickstart: Phase 1 — Production Deploy

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contracts**:
[render-blueprint.md](./contracts/render-blueprint.md), [ci-cd.md](./contracts/ci-cd.md),
[data-migration.md](./contracts/data-migration.md).

---

## 0. Prerequisites (obtain before executing)

All free-tier:

| Provider | What to create | Yields |
|---|---|---|
| **Neon** (neon.tech) | 1 project, 2 databases: `agendai_app`, `agendai_lg` | `DATABASE_URL`, `DATABASE_URI` |
| **Upstash** (upstash.com) | 1 Redis database | `REDIS_URI` |
| **LangSmith** (Developer plan) | API keys | `LANGSMITH_API_KEY` (license), `LANGCHAIN_API_KEY` (tracing) |
| **Render** | account (Blueprint deploy of 4 services) | — |
| **GitHub** | repo + GHCR enabled; `RENDER_DEPLOY_HOOK` secret | image registry + deploy trigger |
| **OpenAI** | existing key | `OPENAI_API_KEY` |

---

## 1. Local dev run (parity with production)

`docker compose up --build -d` now also starts local `postgres` + `redis` (dev stand-ins for
Neon/Upstash) and runs the agent on the `langgraph-server` image. **Only nginx publishes a
port.**

```bash
cp .env.example .env        # fill keys (see Phase E vars)
docker compose up --build -d
docker compose ps           # api, postgres, redis, langgraph-server, nginx, agent-ui-pro
```

Open the app through the nginx edge (e.g. `http://localhost:8080`). Verify:
- Text chat schedules an appointment end to end.
- Audio (mic + file upload) works.
- Responses **stream** through nginx (no buffering stall).

---

## 2. Run the test suites locally (the deploy gate)

```bash
# API — real Postgres (use the local compose postgres or any local PG)
export DATABASE_URL=postgres://agendai:agendai@localhost:5432/agendai_test
cd api && npm ci && npm test          # 39 Jest tests, drop+seed per test

# Agent
cd ../agent && uv run pytest --tb=short   # 70 tests
```

Both green is the precondition for merge (CI enforces the same).

---

## 3. Deploy to Render

1. Create the managed dependencies (Section 0) and copy their connection strings.
2. Connect the repo to Render and deploy the Blueprint `infra/render/render.yaml`.
3. Set the `sync: false` env vars in the Render dashboard for `api`, `langgraph-server`, and
   `nginx` per [render-blueprint.md](./contracts/render-blueprint.md).
4. Set `agent-ui-pro` build args (`NEXT_PUBLIC_API_URL` = the public nginx URL).
5. First deploy: confirm the API created its schema + seed in `agendai_app`, and the
   LangGraph Server created its own schema in `agendai_lg`.

---

## 4. Enable the CI gate

1. Add `.github/workflows/ci.yml` + `deploy.yml`.
2. Add GitHub secret `RENDER_DEPLOY_HOOK` (Render service deploy hook URL).
3. Enable **branch protection** on `main` requiring `test-api` + `test-agent` to pass.

---

## 5. End-to-end verification (maps to Success Criteria)

| # | Check | Verifies |
|---|---|---|
| 1 | From a clean machine, open the public URL; complete a text **and** audio scheduling flow; streaming works through nginx | SC-001, US1, FR-001/002/004 |
| 2 | Create an appointment + start a thread; **restart** the `langgraph-server` (and redeploy api); reopen the thread and re-query the appointment — both survive | SC-002, US2, FR-005/006 |
| 3 | `cd api && npm test` (39, Postgres) and `cd agent && uv run pytest` (70) pass locally and in CI | SC-005, FR-009/011 |
| 4 | Open a PR with a deliberately failing test → CI red blocks merge; fix → green unblocks | SC-003, US3, FR-010 |
| 5 | Merge to `main` → `deploy.yml` builds/pushes to GHCR + triggers Render; public URL serves the new version; complete a booking end to end | SC-004, FR-012/013 |
| 6 | Confirm a production conversation trace (with tool calls) appears in LangSmith; capture screenshot | SC-008, FR-018 |
| 7 | Attempt to reach `api` / `langgraph-server` directly — no public route exists | SC-007, FR-003 |

---

## 6. Portfolio finishing (README)

- Green CI badge.
- Production URL.
- LangSmith traces screenshot (from check #6).
- Note the architectural decisions (link this spec folder).

---

## Out of scope (Phases 2/3)

Terraform / GCP / AWS; Bedrock Guardrails; Vertex AI Memory Bank / Evaluation; Amazon Cognito;
LLM Gateway; circuit breaker (P1), input guardrails (P4), structured logs + correlation IDs
(P5). These are independent agent hardening items and may proceed in parallel if desired.
