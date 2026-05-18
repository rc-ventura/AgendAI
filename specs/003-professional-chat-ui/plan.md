# Implementation Plan: Professional Chat UI with Audio Support

**Branch**: `003-professional-chat-ui` | **Date**: 2026-05-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-professional-chat-ui/spec.md`

## Summary

Clone `github.com/langchain-ai/agent-chat-ui` as `agent-ui-pro/` — a production-quality
Next.js 14 + shadcn/ui chat shell with native LangGraph streaming support. Inject the
validated audio components (mic recording + file upload) from the existing `agent-ui`
with zero protocol changes. Apply AgendAI branding and pt-BR text. Add as a new Docker
Compose service on port 3002 while keeping the existing `agent-ui` on port 3001 alive
for parallel validation. The existing `agent-ui` is the **source of truth** for all
agent interactions; no agent or API changes are required.

## Technical Context

**Language/Version**: TypeScript 5 / Node.js 20

**Primary Dependencies**: Next.js 14, React 18, `@langchain/langgraph-sdk` ^0.0.30,
shadcn/ui (Radix + Tailwind CSS), MediaRecorder API (browser-native)

**Storage**: None — conversation state is ephemeral in-memory React state (tab-scoped)

**Testing**: Vitest + @testing-library/react (same stack as existing agent-ui)

**Target Platform**: Desktop browsers (Chrome, Firefox, Safari); mobile is stretch goal

**Project Type**: Web application (frontend-only service; no backend changes)

**Performance Goals**: Streaming response perceived latency ≤ existing agent-ui;
audio submit round-trip perceived as equivalent to text

**Constraints**: NEXT_PUBLIC_* env vars baked at build time; no server-side rendering
for agent interactions (all client-side via SDK); port 3002 reserved

**Scale/Scope**: Single concurrent user per browser tab; no multi-tenancy concerns

## Constitution Check

*GATE: Must pass before implementation. Re-check after design.*

| Principle | Applies? | Status | Notes |
|-----------|----------|--------|-------|
| I. Layered Architecture | No | ✅ N/A | Frontend only; no backend changes |
| II. Test-First with Real DB | No | ✅ N/A | No database; existing agent-ui tests serve as regression baseline |
| III. Stateless Services via DI | Partial | ✅ Pass | `createClient()` factory used; no global singleton mutation beyond `threadId` module var (matches existing pattern) |
| IV. Observability & Cache Consistency | No | ✅ N/A | No cache writes; errors surface as Portuguese UI messages |
| V. Simplicity & Minimal Abstraction | Yes | ✅ Pass | Reuse existing audio components verbatim; no new abstractions; pt-BR as hard-coded strings |

**Tech Stack Constraint**: Constitution mandates "Chat UI: Next.js 14, `@langchain/langgraph-sdk`"
— agent-ui-pro satisfies both. ✅

**Complexity Tracking**: No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/003-professional-chat-ui/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   ├── agent-protocol.md    ← LangGraph wire protocol (validated from agent-ui)
│   └── docker-service.md    ← New Docker service spec
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code Layout

```text
agent-ui-pro/                        ← cloned from langchain-ai/agent-chat-ui
├── Dockerfile                       ← new (port 3002, same pattern as agent-ui)
├── .env.local.example               ← new (documents required env vars)
├── package.json                     ← upstream + no additions required
├── src/
│   ├── app/
│   │   ├── layout.tsx               ← update: AgendAI title, pt-BR lang attr
│   │   └── page.tsx                 ← upstream (unchanged or minimal branding)
│   ├── components/
│   │   ├── AudioUploadButton.tsx    ← ported verbatim from agent-ui
│   │   └── ui/                     ← shadcn/ui components (upstream)
│   └── lib/
│       └── langgraph.ts             ← ported from agent-ui: sendAudio + streamChat
│                                       (agent-chat-ui has its own; merge audio fns)
├── public/                          ← AgendAI logo/favicon if available
└── tailwind.config.ts               ← update: AgendAI colour tokens

docker-compose.yml                   ← add agent-ui-pro service block
```

**Structure Decision**: New service directory at repo root (`agent-ui-pro/`) alongside
existing `agent-ui/`. No monorepo tooling needed — each is an independent Next.js app.

## Phase 0: Research ✅ Complete

See [research.md](./research.md).

Key decisions locked:
- Clone agent-chat-ui locally as `agent-ui-pro/`
- Port AudioUploadButton + sendAudio verbatim from agent-ui
- Hard-code pt-BR strings (no i18n library)
- Port 3002, new docker-compose service

## Phase 1: Design ✅ Complete

Artifacts generated:
- [data-model.md](./data-model.md) — in-memory state model
- [contracts/agent-protocol.md](./contracts/agent-protocol.md) — LangGraph wire protocol
- [contracts/docker-service.md](./contracts/docker-service.md) — Docker service spec
- [quickstart.md](./quickstart.md) — local dev + acceptance validation steps

## Implementation Notes for Phase 2

The following details guide task generation in `/speckit-tasks`:

### 1. Clone agent-chat-ui
```bash
git clone https://github.com/langchain-ai/agent-chat-ui agent-ui-pro
cd agent-ui-pro
rm -rf .git   # detach from upstream; this is now our code
```

### 2. Port audio files from agent-ui
Copy these two files verbatim:
- `agent-ui/src/components/AudioUploadButton.tsx` → `agent-ui-pro/src/components/AudioUploadButton.tsx`
- Audio functions from `agent-ui/src/lib/langgraph.ts` (specifically `sendAudio`, `ChatMessage.isAudio`) — merge into agent-chat-ui's existing langgraph lib, taking care not to break its streaming implementation.

### 3. Wire AudioUploadButton into input bar
Locate the agent-chat-ui message input component and add:
```tsx
<AudioUploadButton onAudio={handleAudio} disabled={isLoading} />
```
inline before the textarea, exactly as in ChatWindow.tsx line 222.

### 4. Implement handleAudio
Port `handleAudio` from `ChatWindow.tsx` lines 101–122 into the agent-chat-ui
equivalent chat hook/component.

### 5. Branding & pt-BR
- App title: "AgendAI — Assistente de Agendamento Médico"
- Welcome message: "Olá! Sou o assistente AgendAI. Posso ajudar com agendamentos médicos, consulta de horários disponíveis, cancelamentos e informações de pagamento. Como posso ajudá-lo?"
- Input placeholder: "Digite sua mensagem… (Enter para enviar)"
- Send button: "Enviar"
- Reset button: "Nova Conversa"
- Typing indicator: "Digitando…"
- Error messages: match agent-ui Portuguese strings
- Colour: primary `#6366f1` (indigo-500) as used in agent-ui header + buttons

### 6. Dockerfile & docker-compose
Follow the template in `contracts/docker-service.md`. The `npm start` command must
use port 3002 (`next start -p 3002`).

### 7. Env vars
`.env.local.example`:
```
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_GRAPH_ID=agendai_agent
NEXT_PUBLIC_LANGGRAPH_API_KEY=
```

### 8. Validation
Run the 7-step checklist in `quickstart.md` against the live agent before marking done.
