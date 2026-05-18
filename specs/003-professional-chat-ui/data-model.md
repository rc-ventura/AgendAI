# Data Model: Professional Chat UI

**Feature**: 003-professional-chat-ui
**Date**: 2026-05-16

> Note: The new UI is a pure front-end component. It owns no persistent storage.
> All entities below are in-memory, tab-scoped React state.

---

## ChatMessage

Represents a single turn in the conversation.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Unique identifier; used as React key and for streaming updates |
| `role` | `"user" \| "assistant"` | Sender of the message |
| `content` | `string` | Text content; may be appended to incrementally during streaming |
| `isAudio` | `boolean?` | True when the message originates from a mic recording or file upload |

**Lifecycle**: Created on `addMessage()`; assistant messages start with `content: ""`
and are updated in-place via `setMessages(prev => prev.map(...))` during the stream.

---

## ConversationState

The full in-memory state of the active chat window.

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `ChatMessage[]` | Ordered list of all turns, starting with the welcome message |
| `input` | `string` | Current value of the text input field |
| `loading` | `boolean` | True while any agent response is in-flight |
| `threadId` | `string \| null` | LangGraph thread ID; `null` before first `threads.create()` resolves |

**Reset behaviour**: On "Nova Conversa", `threadId` is set to `null`, `messages` is
replaced with the welcome message only, and a new thread is created.

---

## AudioInput

Represents a single audio payload submitted to the agent. Not stored as a state
entity — it is passed as a `Blob` argument to `sendAudio()` and immediately serialized.

| Field | Type | Description |
|-------|------|-------------|
| `blob` | `Blob` | Raw audio data; type is `audio/webm` (mic) or the file's MIME type (upload) |
| `audioData` | `number[]` | `Array.from(new Uint8Array(blob.arrayBuffer()))` — the wire format sent to LangGraph |

---

## Environment Configuration

Resolved at build time via Next.js `NEXT_PUBLIC_*` env vars.

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8080` | LangGraph nginx proxy URL |
| `NEXT_PUBLIC_GRAPH_ID` | `agendai_agent` | LangGraph graph/assistant ID |
| `NEXT_PUBLIC_LANGGRAPH_API_KEY` | — | Auth token forwarded as `x-api-key` header |

---

## State Transitions

```
App load
  └─▶ threadId = null
        └─▶ getOrCreateThread() resolves
              └─▶ threadId = "<uuid>"  ← ready to send

User sends text / audio
  └─▶ loading = true
        └─▶ assistant message created (content: "")
              └─▶ stream chunks update content in-place
                    └─▶ loading = false

User clicks "Nova Conversa"
  └─▶ resetThread()  →  threadId = null
        └─▶ messages = [welcome]
              └─▶ getOrCreateThread() resolves
                    └─▶ threadId = "<new-uuid>"
```
