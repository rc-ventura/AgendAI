# Quickstart: agent-ui-pro

**Feature**: 003-professional-chat-ui

## Prerequisites

- Docker Desktop running
- `.env` file at repo root with `LANGGRAPH_AUTH_TOKEN` set
- Existing services healthy (`docker compose ps`)

## Run both UIs in parallel

```bash
# Start everything including the new UI
docker compose up --build -d

# Verify both UIs are up
docker compose ps

# Old UI (existing):  http://localhost:3001
# New UI (professional): http://localhost:3002
```

## Local development (agent-ui-pro only)

```bash
cd agent-ui-pro

# Install dependencies (first time)
npm install

# Set env vars (copy from .env.local.example)
cp .env.local.example .env.local
# Edit .env.local:
#   NEXT_PUBLIC_API_URL=http://localhost:8080
#   NEXT_PUBLIC_GRAPH_ID=agendai_agent
#   NEXT_PUBLIC_LANGGRAPH_API_KEY=<your token>

# Start dev server
npm run dev
# → http://localhost:3002
```

## Validate interactions (acceptance checklist)

Run through these with the agent server running:

1. **Text chat**: Type "Quero agendar uma consulta" → agent replies (streamed)
2. **Enter to send**: Type message, press Enter (not Shift+Enter) → sends
3. **Mic recording**: Click 🎙 → record → click again → audio processed
4. **File upload**: Click 📎 → select `.mp3`/`.wav`/`.webm` → audio processed
5. **Reset**: Click "Nova Conversa" → fresh thread, welcome message reappears
6. **Error state**: Stop agent service → clear error message appears (no crash)
7. **Mic denied**: Deny browser mic permission → file upload still works

## Decommission checklist (when ready to retire agent-ui)

- [X] SC-001–SC-005 all pass (team sign-off)
- [X] Remove `agent-ui` service block from `docker-compose.yml`
- [X] Remove `agent-ui/` directory (or archive to a git tag)
- [X] Update CLAUDE.md port reference (3001 → 3002)
