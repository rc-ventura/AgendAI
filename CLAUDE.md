# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/003-professional-chat-ui/plan.md
<!-- SPECKIT END -->

## Project Overview

AgendAI is a medical scheduling automation system consisting of four independent components:

1. **REST API** (`api/`) — Node.js 20 + Express 4 + SQLite (`better-sqlite3`) that manages doctors, patients, time slots, appointments, and (mock) payments.
2. **LangGraph Agent** (`agent/`) — Python 3.11 + LangGraph v1.0+ StateGraph that handles the chat interface: input routing, GPT-4o-mini with tool calling, Whisper/TTS audio pipeline, and Gmail SMTP transactional email.
3. **Chat UI** (`agent-ui-pro/`) — Next.js 14 + shadcn/ui professional frontend using `@langchain/langgraph-sdk` with audio support (mic + file upload). Runs on port 3002.

Everything starts with a single `docker compose up --build -d`. The API runs on port 3000; the LangGraph agent on port 8123 (via nginx proxy on 8080); the chat UI on port 3002.

## Commands

### Start / Stop

```bash
docker compose up --build -d    # build and start all services
docker compose ps               # check status
docker compose logs api         # API logs
docker compose down -v          # stop and wipe volumes (resets DB)
```

### Tests (run locally, not inside Docker)

```bash
cd api
npm install
npm test                        # all tests (--runInBand --forceExit)
npx jest tests/agendamentos.test.js   # single test file
```

### Local dev server (without Docker)

```bash
cd api
cp ../.env.example ../.env      # set OPENAI_API_KEY, DB_PATH
npm run dev                     # nodemon, hot-reload
```

### Reset database

```bash
docker compose down -v && docker compose up --build -d
```

## Architecture

### API Layer (`api/src/`)

Routes receive a shared `db` instance (injected at startup from `server.js`) and wire up a layered stack:

```
routes/ → controllers/ → services/ → repositories/ → better-sqlite3
```

- **`db/connection.js`** — creates the `better-sqlite3` singleton with WAL mode + FK enforcement; runs `schema.sql` on every startup (idempotent `CREATE TABLE IF NOT EXISTS`).
- **`db/seed.js`** — populates 3 doctors, 5 patients, 10 time slots, 2 appointments on first run (checks row count before inserting).
- **`cache/index.js`** — `node-cache` singleton, TTL 60 s. Availability queries are cached; any write (create/cancel appointment) calls `del('horarios:disponiveis')` to invalidate.
- **`middlewares/errorHandler.js`** — centralized error handler; maps known error types to HTTP status codes.
- **`app.js`** — `createApp(db)` factory (enables in-memory DB injection for tests). Applies rate limiting (100 req/15 min), 30 s request timeout, and request logger before routing.

### LangGraph Agent

The agent is a `StateGraph` compiled in `agent/agent/graph.py`. Nodes live in `agent/agent/nodes/`:

- `input_detector.py` — routes text vs. audio
- `transcriber.py` — Whisper STT for audio input
- `llm_core.py` — GPT-4o-mini with the system prompt and tool bindings
- `tools.py` — 6 `@tool`-decorated async functions that call the REST API via `api_client.py`
- `tool_result_processor.py` — inspects the latest tool round to detect successful create/cancel appointment calls and prepares the email payload
- `email_sender.py` — Gmail SMTP with `tenacity` retry
- `tts.py` — OpenAI TTS (voice `alloy`) for audio output

The compiled `graph` is exposed via LangGraph Platform (`langgraph dev`) on port 8123. Configure `OPENAI_API_KEY`, `API_BASE_URL`, optional `LANGCHAIN_*` (LangSmith), and optional `GMAIL_USER` / `GMAIL_APP_PASSWORD` via `.env`.

### Database

SQLite file at `data/clinica.db` (Docker volume, gitignored). Five tables: `medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos`. Tests use `:memory:` DB injected via `createApp(db)`.

### Testing Pattern

Tests create an in-memory DB, run schema + seed, pass the `db` to `createApp(db)`, and use `supertest` against the resulting Express app. No mocking of the database layer.

## Key Env Vars

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required by the LangGraph agent for GPT-4o-mini / Whisper / TTS |
| `PORT` | `3000` | API listen port |
| `DB_PATH` | `/app/data/clinica.db` | SQLite file path |
| `API_BASE_URL` | `http://api:3000` | URL used by the agent to call the REST API |
| `LANGGRAPH_AUTH_TOKEN` | — | Token enforced by the nginx proxy in front of the agent (port 8080) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | — | Optional Gmail SMTP credentials for notifications |
