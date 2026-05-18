---
description: "Task list for Professional Chat UI with Audio Support"
---
# Tasks: Professional Chat UI with Audio Support

**Input**: Design documents from `specs/003-professional-chat-ui/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Source of truth**: `agent-ui/` — all agent interaction patterns are ported verbatim.
No agent or API changes required.

**Tests**: Not included — rapid prototype delivery; existing agent-ui tests serve as
regression baseline for interaction patterns.

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are included in every task description

---

## Phase 1: Setup

**Purpose**: Clone upstream repo, detach from upstream git, establish project skeleton.

- [X] T001 Clone `https://github.com/langchain-ai/agent-chat-ui` into `agent-ui-pro/` at repo root
- [X] T002 Remove `agent-ui-pro/.git` and re-initialise as a plain directory (no upstream tracking)
- [X] T003 Create `agent-ui-pro/.env.local.example` with: `NEXT_PUBLIC_API_URL=http://localhost:8080`, `NEXT_PUBLIC_GRAPH_ID=agendai_agent`, `NEXT_PUBLIC_LANGGRAPH_API_KEY=`
- [X] T004 Add `agent-ui-pro/` to `.gitignore` entries for `node_modules`, `.next`, `.env.local`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Docker wiring and audio SDK layer — must be complete before either UI story.

⚠️ **CRITICAL**: User stories cannot be independently validated until Docker is wired (T005–T006).

- [X] T005 Create `agent-ui-pro/Dockerfile` using the template in `specs/003-professional-chat-ui/contracts/docker-service.md` (Node 20 Alpine, multi-stage build, `next start -p 3002`, NEXT_PUBLIC_* ARGs)
- [X] T006 Add `agent-ui-pro` service block to `docker-compose.yml` per `specs/003-professional-chat-ui/contracts/docker-service.md` (port 3002, depends on nginx, same env args as agent-ui)
- [X] T007 [P] Locate the SDK lib file in `agent-ui-pro/src/` that agent-chat-ui uses for LangGraph calls (e.g., `lib/client.ts`, `lib/langgraph.ts`, or similar). Add only the missing delta from `agent-ui/src/lib/langgraph.ts`: (a) `sendAudio` function verbatim, (b) `isAudio?: boolean` field to the message type. Do NOT re-add `getOrCreateThread`, `streamChat`, or `resetThread` if agent-chat-ui already implements equivalent functions — check first to avoid duplicates
- [X] T008 [P] Verify `agent-ui-pro/package.json` already includes `@langchain/langgraph-sdk`; add it if missing (`npm install @langchain/langgraph-sdk@^0.0.30` inside `agent-ui-pro/`)
- [X] T008b [P] Inspect `agent-ui-pro/src/` for any `localStorage` or `sessionStorage` usage related to message history (grep for `localStorage`). If found, keep it — persistence across page refreshes is acceptable for the MVP (FR-008 relaxed)

**Checkpoint**: Foundation ready — both user story phases can now begin.

---

## Phase 3: User Story 1 — Professional Text Chat (Priority: P1) 🎯 MVP

**Goal**: A patient opens `http://localhost:3002` and completes a full appointment
scheduling flow via text chat — professionally branded, pt-BR, streamed responses.

**Independent Test**: Open `http://localhost:3002`, type "Quero agendar uma consulta",
confirm streamed reply appears; press Enter to send; verify AgendAI header and pt-BR text
throughout — no raw JSON visible.

### Implementation for User Story 1

- [X] T009 [P] [US1] Update `agent-ui-pro/src/app/layout.tsx`: set `<html lang="pt-BR">`, page title "AgendAI — Assistente de Agendamento Médico"
- [X] T010 [P] [US1] Update `agent-ui-pro/tailwind.config.ts`: add `primary: '#6366f1'` colour token (indigo-500, matches agent-ui header)
- [X] T011 [US1] Wire env vars into agent-chat-ui connection layer: ensure `NEXT_PUBLIC_API_URL` is used as the LangGraph client `apiUrl`, `NEXT_PUBLIC_GRAPH_ID` as the assistant/graph ID, and `NEXT_PUBLIC_LANGGRAPH_API_KEY` as the API key — replace any hardcoded defaults in agent-chat-ui's config
- [X] T012 [US1] Add welcome message as the first assistant message on thread creation: "Olá! Sou o assistente AgendAI. Posso ajudar com agendamentos médicos, consulta de horários disponíveis, cancelamentos e informações de pagamento. Como posso ajudá-lo?"
- [X] T013 [US1] Translate all patient-facing strings to pt-BR in agent-chat-ui components: input placeholder → "Digite sua mensagem… (Enter para enviar)", send button → "Enviar", new-thread button → "Nova Conversa", typing/loading indicator → "Digitando…", agent-unreachable error → "Não foi possível conectar ao assistente. Tente novamente.", generic error → "Erro ao processar mensagem. Tente novamente."
- [X] T014 [US1] Apply AgendAI branding to the chat header component: display "AgendAI" as title with subtitle "Assistente de Agendamento Médico", use `#6366f1` background, white text
- [X] T015 [US1] Validate text chat end-to-end: `npm run dev` inside `agent-ui-pro/`, open `http://localhost:3002`, run quickstart.md steps 1 and 2 (text chat + Enter to send)

**Checkpoint**: User Story 1 is fully functional and testable independently at port 3002.

---

## Phase 4: User Story 2 — Audio Input (Priority: P2)

**Goal**: A patient can record audio via microphone or upload an audio file from the
same input bar used for text, and receive a reply from the agent.

**Independent Test**: Click mic icon → record → click again → reply received; click
attach icon → select `.mp3` → reply received; deny mic permission → only file upload
available (no crash).

### Implementation for User Story 2

- [X] T016 [P] [US2] Copy `agent-ui/src/components/AudioUploadButton.tsx` verbatim into `agent-ui-pro/src/components/AudioUploadButton.tsx`
- [X] T017 [US2] Port `handleAudio` function from `agent-ui/src/components/ChatWindow.tsx` (lines 101–122) into the agent-chat-ui equivalent chat component: add user bubble "Mensagem de áudio enviada" with `isAudio: true`, show "Processando áudio…" assistant placeholder, call `sendAudio(blob, threadId)`, update placeholder with reply, handle error with "Erro ao processar áudio. Tente novamente."
- [X] T018 [US2] Add `isAudio` indicator to user message bubble rendering: when `message.isAudio === true`, prepend 🎙 emoji before the message content
- [X] T019 [US2] Wire `<AudioUploadButton onAudio={handleAudio} disabled={isLoading} />` inline in the message input bar, positioned before the textarea — mirroring `agent-ui/src/components/ChatWindow.tsx` line 222
- [X] T020 [US2] Validate audio interactions: run quickstart.md steps 3 and 4 (mic recording + file upload) with live agent

**Checkpoint**: User Stories 1 AND 2 are both independently functional at port 3002.

---

## Phase 5: User Story 3 — Parallel Operation (Priority: P3)

**Goal**: Both `agent-ui` (port 3001) and `agent-ui-pro` (port 3002) run simultaneously
via a single `docker compose up --build -d`; old UI is decommissioned only after
SC-001–SC-005 sign-off.

**Independent Test**: `docker compose up --build -d` → `docker compose ps` shows both
services healthy → complete a scheduling session on 3001 → complete same session on
3002 → stop `agent-ui` service → 3002 still works.

### Implementation for User Story 3

- [X] T021 [US3] Run `docker compose up --build -d` and confirm `agent-ui-pro` service starts successfully on port 3002 alongside existing `agent-ui` on port 3001
- [X] T022 [US3] Verify `http://localhost:3001` (existing agent-ui) still operates correctly after adding the new service
- [X] T023 [US3] Verify `http://localhost:3002` (agent-ui-pro) connects to the agent and completes a full scheduling flow
- [X] T024 [US3] Run full quickstart.md acceptance checklist (all 7 steps) against the Dockerised `agent-ui-pro`

**Checkpoint**: Both UIs operational simultaneously. SC-003 validation period can begin.

---

## Phase 6: Polish & Edge Case Hardening

**Purpose**: Edge cases from spec.md Edge Cases section; cross-cutting robustness.

- [X] T025 [P] Add connection error state: when `getOrCreateThread()` fails on load, display "Não foi possível conectar ao assistente. Verifique sua conexão e recarregue a página." instead of a blank screen — in agent-chat-ui's thread initialisation logic
- [X] T025b Add retry button to the connection error state: render a "Tentar novamente" button alongside the error message that calls `getOrCreateThread()` again and clears the error state on success — satisfying the FR-006 "retry affordance" requirement
- [X] T026 [P] Add client-side audio format validation in `agent-ui-pro/src/components/AudioUploadButton.tsx`: before calling `onAudio(file)`, check `file.type` starts with `audio/`; if not, show alert "Formato não suportado. Use MP3, WAV ou WEBM."
- [X] T027 Add audio file size guard in `agent-ui-pro/src/components/AudioUploadButton.tsx`: reject files > 25 MB with alert "Arquivo muito grande. Tamanho máximo: 25 MB."
- [X] T028 Update `CLAUDE.md` project overview: add `agent-ui-pro/` as the new professional chat UI on port 3002; note port 3001 is the legacy UI pending decommission

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (clone must exist)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (Docker wired, SDK merged) — no dependency on US2/US3
- **User Story 2 (Phase 4)**: Depends on Phase 2 only — can start in parallel with US1 after T007/T008
- **User Story 3 (Phase 5)**: Depends on Phase 3 AND Phase 4 (needs both features complete to validate)
- **Polish (Phase 6)**: Depends on Phase 3 (UI shell exists to add error states to)

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational — no dependency on US2/US3
- **US2 (P2)**: Starts after Foundational — no dependency on US1 (audio component is isolated)
- **US3 (P3)**: Starts after US1 AND US2 are both complete

### Within Each Phase

- Tasks marked [P] within the same phase can run in parallel
- T011 (env wiring) depends on T007 (SDK merge) — sequential
- T019 (wire AudioUploadButton) depends on T016 (copy file) and T017 (handleAudio) — sequential

### Parallel Opportunities

```bash
# Phase 1: T003 and T004 are sequential after T001 (no [P] marker)

# Phase 2 parallel block (after T001–T002):
T007   # Add sendAudio delta to SDK lib
T008   # Verify @langchain/langgraph-sdk in package.json
T008b  # Inspect for localStorage persistence (grep)

# Phase 3 parallel block (US1):
T009  # Update layout.tsx
T010  # Update tailwind.config.ts

# Phase 4 parallel block (US2, after Phase 2):
T016  # Copy AudioUploadButton.tsx

# Phase 6 parallel block:
T025  # Connection error state
T026  # Audio format validation
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) — ~15 min
2. Complete Phase 2 (Foundational) — ~30 min
3. Complete Phase 3 (US1: Professional Text Chat) — ~45 min
4. **STOP and VALIDATE**: run quickstart.md steps 1–2 + visual review
5. Deploy `docker compose up --build -d` → accessible at port 3002

### Incremental Delivery

1. Setup + Foundational → skeleton running
2. US1 complete → professional text chat at 3002 (MVP!)
3. US2 complete → audio input added
4. US3 complete → parallel operation validated → decommission gate opens
5. Polish → edge cases hardened

### Parallel Execution (if solo developer)

After Phase 2, US1 (T009–T015) and US2 (T016–T020) can proceed in any order
since they touch different components (branding/text vs. audio component). Merge
both before starting Phase 5 (parallel operation validation).

---

## Notes

- [P] tasks = different files, no blocking dependencies
- All agent-ui source paths referenced are relative to repo root: `agent-ui/src/...`
- All agent-ui-pro target paths are relative to repo root: `agent-ui-pro/src/...`
- Never modify `agent-ui/` — it is the source of truth and must remain functional
- Run `quickstart.md` validation steps before marking each story's checkpoint complete
- The decommission of `agent-ui` is NOT a task here — it requires team sign-off on SC-001–SC-005
