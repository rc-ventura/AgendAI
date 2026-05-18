# Research: Professional Chat UI

**Feature**: 003-professional-chat-ui
**Date**: 2026-05-16

## Decision 1: Base UI — agent-chat-ui vs. building from scratch

**Decision**: Clone `github.com/langchain-ai/agent-chat-ui` as `agent-ui-pro/`.

**Rationale**: agent-chat-ui is a production-quality Next.js 14 + shadcn/ui chat shell
that already handles LangGraph streaming (SSE via `@langchain/langgraph-sdk`), thread
management, markdown rendering, and a polished visual design. The existing agent-ui
validates that the SDK integration patterns work end-to-end. Cloning gives full control
for audio injection without upstream runtime dependency.

**Alternatives considered**:
- CDN embed / iFrame: No ability to inject audio controls into the input bar; iframe
  cross-origin restrictions block postMessage audio blobs.
- npm package: agent-chat-ui is not published to npm; would require patching.

---

## Decision 2: Audio integration strategy

**Decision**: Port `AudioUploadButton.tsx` and the `sendAudio` function verbatim from
the existing agent-ui into agent-ui-pro, then wire them into agent-chat-ui's input bar.

**Rationale**: These files are already validated against the live agent (Whisper pipeline,
`input_type: "audio"`, `audio_data: Array.from(Uint8Array)`). Zero re-invention needed.
The agent-chat-ui input component is a single composable component; adding two icon
buttons (mic + attach) is a minimal surgery.

**Alternatives considered**:
- Re-implement audio from scratch in agent-chat-ui: Adds risk with no benefit; the
  existing implementation has known-good MediaRecorder + file input patterns.
- Use a third-party audio recorder library: Overkill and adds a dependency for a
  ~70-line component that is already proven.

---

## Decision 3: Streaming protocol compatibility

**Decision**: Keep `streamMode: "messages"` for text (parsing `messages/partial` events)
and `streamMode: "values"` for audio, exactly as in the existing agent-ui `langgraph.ts`.

**Rationale**: agent-chat-ui uses the same `@langchain/langgraph-sdk` Client and the same
streaming patterns internally. The LangGraph server (langgraph dev, port 8123 / nginx 8080)
is unchanged, so the protocol is already validated.

**Alternatives considered**:
- Migrate to a single `streamMode`: Not necessary; both modes work and changing them
  risks breaking audio response parsing which relies on `chunk.data.messages`.

---

## Decision 4: Localization

**Decision**: Hard-code Brazilian Portuguese (pt-BR) strings directly in components
(no i18n library).

**Rationale**: Single-language product; adding an i18n framework (next-intl, react-i18next)
is premature abstraction per Constitution Principle V. String literals in components are
sufficient and keep the codebase simple.

**Alternatives considered**:
- next-intl / react-i18next: Over-engineered for a single-locale app at this stage.

---

## Decision 5: Port and Docker service

**Decision**: New service `agent-ui-pro` on port 3002; existing `agent-ui` on port 3001
remains untouched. A single new service block is added to `docker-compose.yml`.

**Rationale**: Satisfies US3 (parallel operation) with minimal infrastructure change.
Port 3002 is unused. No nginx changes required — the new UI connects directly to
`http://localhost:8080` (the existing nginx proxy), same as the current UI.

**Alternatives considered**:
- Replace agent-ui in-place: Violates SC-003 / US3; no fallback during validation.
- Add nginx route: Unnecessary complexity; separate port is simpler.

---

## Existing agent-ui — authoritative interaction inventory

This section records every validated interaction from the current agent-ui that
MUST be preserved in agent-ui-pro (source of truth per user instruction).

| # | Interaction | Implementation |
|---|-------------|----------------|
| 1 | Create LangGraph thread on load | `client.threads.create()` |
| 2 | Stream text response | `client.runs.stream(threadId, graphId, { input: { messages, input_type:"text" }, streamMode:"messages" })` → parse `messages/partial` events |
| 3 | Send audio (mic) | MediaRecorder → `Blob({type:"audio/webm"})` → `sendAudio` |
| 4 | Send audio (file) | `<input accept="audio/*">` → `sendAudio` |
| 5 | sendAudio protocol | `client.runs.stream(threadId, graphId, { input: { ..., input_type:"audio", audio_data:Array.from(Uint8Array) }, streamMode:"values" })` → parse `chunk.data.messages` |
| 6 | Reset conversation | `resetThread()` + `client.threads.create()` |
| 7 | Welcome message | "Olá! Sou o assistente AgendAI…" on thread init |
| 8 | Typing indicator | "Digitando…" bubble while `loading === true` |
| 9 | Error fallback | Portuguese error string in assistant bubble on catch |
| 10 | Enter to send | `onKeyDown` Enter (without Shift) → `handleSend()` |
| 11 | Auto-scroll | `bottomRef.current?.scrollIntoView({ behavior:"smooth" })` |
| 12 | Audio message label | User bubble: "Mensagem de áudio enviada" + 🎙 indicator |
| 13 | Env config | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_GRAPH_ID`, `NEXT_PUBLIC_LANGGRAPH_API_KEY` |

---

## agent-chat-ui capabilities (upstream baseline)

agent-chat-ui provides out-of-the-box:
- shadcn/ui component library (Radix primitives + Tailwind CSS)
- Thread creation and management UI
- Streaming message rendering with markdown support
- Tool call visualization (collapsible panels)
- Message history within session
- Configurable agent endpoint + API key via UI or env

**Gap vs. agent-ui**: No audio support (no mic, no file upload). This is the only
functional gap to fill.
