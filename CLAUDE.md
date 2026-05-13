# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/001-n8n-medical-scheduling/plan.md
<!-- SPECKIT END -->

## Project Overview

AgendAI is a medical scheduling automation system consisting of two independent components:

1. **REST API** (`api/`) — Node.js 20 + Express 4 + SQLite (`better-sqlite3`) that manages doctors, patients, time slots, appointments, and (mock) payments.
2. **N8N Workflows** (`n8n/`) — 4 exported JSON flows that handle the chat interface: routing (flow-a), GPT-4o-mini with function calling (flow-b), audio via Whisper/TTS (flow-c), and Gmail transactional email (flow-d).

Everything starts with a single `docker compose up --build -d`. The API runs on port 3000; N8N on port 5678.

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

### N8N Flows

Import order matters (sub-workflows must exist before callers reference their IDs):

1. `flow-d-email.json` — Gmail sub-workflow
2. `flow-b-ai-core.json` — LLM core (references flow-d ID)
3. `flow-a-entrada.json` — webhook entry (references flow-b and flow-c IDs)
4. `flow-c-audio.json` — audio pipeline (Whisper → flow-b → TTS)

After import, update `API_BASE_URL` in HTTP Request nodes to `http://api:3000` and wire OpenAI/Gmail credentials.

### Database

SQLite file at `data/clinica.db` (Docker volume, gitignored). Five tables: `medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos`. Tests use `:memory:` DB injected via `createApp(db)`.

### Testing Pattern

Tests create an in-memory DB, run schema + seed, pass the `db` to `createApp(db)`, and use `supertest` against the resulting Express app. No mocking of the database layer.

## Key Env Vars

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for N8N GPT-4o-mini / Whisper / TTS |
| `PORT` | `3000` | API listen port |
| `DB_PATH` | `/app/data/clinica.db` | SQLite file path |
| `N8N_BASIC_AUTH_USER` | `admin` | N8N UI login |
| `N8N_BASIC_AUTH_PASSWORD` | `admin` | N8N UI login |
