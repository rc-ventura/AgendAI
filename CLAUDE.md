# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/005-agent-hardening/plan.md
<!-- SPECKIT END -->


# Documentation (truth source)

In @docs folder you can find the documentation for the project.

In @docs/adr you can find the architectural decision records.

In @docs/roadmap you can find the roadmap for the project.



## Project Overview

AgendAI is a medical scheduling automation system with five components:

1. **REST API** (`api/`) — Node.js 20 + Express 4 + **Postgres** (`pg`) managing doctors, patients, time slots, appointments, and payments.
2. **LangGraph Agent** (`agent/`) — Python 3.11 + LangGraph v1.0+ StateGraph: GPT-4o-mini with tool calling, Whisper/TTS audio pipeline, Gmail SMTP. Compiled graph without checkpointer (the server provides it).
3. **LangGraph Server** — Official `langchain/langgraph-server` image (built via `langgraph build`). Provides Postgres-backed thread persistence and Redis-backed SSE streaming.
4. **Chat UI** (`agent-ui-pro/`) — Next.js 14 + shadcn/ui using `@langchain/langgraph-sdk` with mic + file-upload audio.
5. **nginx** (`nginx/`) — Single public entry point: routes `/` → UI, `/threads|/runs|...` → agent; enforces `x-api-key` auth, rate limiting, SSE streaming.

Everything starts with `docker compose up --build -d`. **Only nginx publishes a host port (8080).** The UI is served by nginx at `http://localhost:8080`; the API and agent are private (internal network only).

## Commands

### Start / Stop

```bash
# First time: build the agent image
cd agent && pip install -U langgraph-cli && langgraph build -t agendai-agent:latest --no-pull && cd ..

docker compose up --build -d    # start all services (postgres, redis, api, langgraph-server, nginx, ui)
docker compose ps               # check status
docker compose logs api         # API logs
docker compose logs langgraph-server  # agent logs
docker compose down -v          # stop and wipe volumes (resets DB)
```

### Tests (run locally, not inside Docker)

```bash
# API — requires a local Postgres (docker compose postgres service or local install)
export DATABASE_URL=postgres://agendai:agendai@localhost:5433/agendai_test
cd api && npm install && npm test          # 48 Jest tests against real Postgres

# Agent
cd agent && uv run pytest --tb=short      # 91 pytest tests
```

### Local dev (API only, without Docker)

```bash
cd api
cp ../.env.example ../.env      # fill OPENAI_API_KEY, DATABASE_URL etc.
npm run dev                     # nodemon, hot-reload
```

### Reset database

```bash
docker compose down -v && docker compose up --build -d
```

## Architecture

### API Layer (`api/src/`)

Routes receive a shared `pool` (pg.Pool) injected at startup and wire up a layered stack:

```
routes/ → controllers/ → services/ → repositories/ → pg.Pool → Postgres
```

- **`db/connection.js`** — `pg.Pool` singleton via `DATABASE_URL`; conditional SSL (off for localhost/CI, on for Neon); `async initSchema(pool)` runs `schema.sql` on startup (idempotent).
- **`db/seed.js`** — async; seeds 3 doctors, 5 patients, 10 slots, 2 appointments once (count-guard).
- **`cache/index.js`** — Redis (`ioredis`) TTL 60 s. Availability queries cached; writes call `delByPrefix('horarios')` after commit. Graceful no-op fallback when `REDIS_URI` absent.
- **`middlewares/requestId.js`** — accepts inbound `X-Request-ID` or generates UUID; exposes on `req.requestId`.
- **`app.js`** — `createApp(pool)` factory. Rate limiting (100 req/15 min), 30 s timeout, `requestId` → `requestLogger` (structured JSON + pino).
- **`server.js`** — async startup: `initSchema` → `seed` → `listen`; `process.exit(1)` on failure.

### LangGraph Agent

The agent graph is compiled in `agent/agent/graph.py` **without a checkpointer** — the LangGraph Server injects its own Postgres-backed checkpointer at runtime. Uses `create_agent` (ADR-026) wrapping the chat+tools loop as a subgraph. Nodes in `agent/agent/nodes/`:

- `input_detector.py` — routes text vs. audio; audio enters as `HumanMessage(input_audio)` content part
- `llm_core.py` — `base_llm` (gpt-4o-mini, text) + `audio_llm` (gpt-audio, text+audio modalities)
- `tools.py` — 6 `@tool` async functions calling the REST API via `api_client.py`; parallel tool calls enabled
- `tool_result_processor.py` — detects create/cancel and prepares email payload
- `email_sender.py` — Resend HTTP API with `tenacity` retry (3x, exponential backoff)
- `tts.py` — OpenAI TTS (voice `alloy`)

**Middleware stack** (`agent/agent/middleware.py`, applied via `create_agent`):
```
injection_guard → pii_email/cpf/phone → summarization → llm_circuit_breaker → llm_retry → tool_retry → api_circuit_breaker
```

The server listens on **port 8123** (internal only). Config via `agent/langgraph.json` (graph: `agendai_agent`). `_MAX_GRAPH_STEPS=60` (9 middleware items × ~6 steps/LLM call).

### Database

**Postgres** (Neon in production; `postgres:16` container in dev). Two logical databases:

| Database | Used by | Env var |
|---|---|---|
| `agendai` | REST API (médicos, pacientes, horários, agendamentos, pagamentos) | `DATABASE_URL` |
| `agendai_lg` | LangGraph Server (checkpoints, threads, runs) | `DATABASE_URI` |

Five API tables: `medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos`.

### Testing Pattern

Tests connect to a real Postgres via `DATABASE_URL`, drop + recreate schema + seed in `beforeEach`, and use `supertest` against `createApp(pool)`. No mocking of the database layer. Run with `--runInBand` for serialization.

## Key Env Vars

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | GPT-4o-mini, Whisper, TTS |
| `LANGSMITH_API_KEY` | ✅ | LangGraph Server license + tracing key (Developer plan) |
| `LANGSMITH_TRACING` | — | `true` to enable LangSmith traces |
| `LANGSMITH_PROJECT` | — | LangSmith project name (default: `AgendAI`) |
| `DATABASE_URL` | ✅ | Postgres for the API (`agendai` database) |
| `DATABASE_URI` | ✅ | Postgres for the LangGraph Server (`agendai_lg` database) |
| `REDIS_URI` | ✅ | Redis for SSE streaming (LangGraph Server) |
| `LANGGRAPH_AUTH_TOKEN` | ✅ | Shared token: nginx `x-api-key` ↔ UI `NEXT_PUBLIC_LANGGRAPH_API_KEY` |
| `API_BASE_URL` | ✅ | Internal URL of the API (agent → api, default `http://api:3000`) |
| `PORT` | `3000` | API listen port |
| `RESEND_API_KEY` | — | Resend HTTP API for appointment emails (replaces Gmail SMTP, blocked on Render free tier) |
| `EMAIL_FROM` | — | Email sender address (default: `AgendAI <onboarding@resend.dev>`) |

> `LANGSMITH_API_KEY` serve para os dois papéis: licença do servidor e tracing. Um único campo.

## CI/CD

Push para `main` dispara:
1. `.github/workflows/ci.yml` — testa API (Postgres real) + agente (pytest). Falha bloqueia deploy.
2. `.github/workflows/deploy.yml` — builda imagens → push GHCR → aciona 4 deploy hooks Render (api → langgraph → nginx → ui).

GitHub Secrets necessários: `LANGSMITH_API_KEY`, `LANGGRAPH_AUTH_TOKEN`, `RENDER_DEPLOY_HOOK_API`, `RENDER_DEPLOY_HOOK_LANGGRAPH`, `RENDER_DEPLOY_HOOK_NGINX`, `RENDER_DEPLOY_HOOK_UI`.
