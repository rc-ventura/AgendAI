# Contract: LangGraph Agent Protocol

**Feature**: 003-professional-chat-ui
**Date**: 2026-05-16
**Status**: Validated (inherited from existing agent-ui)

> This contract describes the wire protocol between agent-ui-pro and the LangGraph
> agent server. It is **read-only for this feature** — no agent changes are required.

---

## Connection

| Property | Value |
|----------|-------|
| Base URL | `NEXT_PUBLIC_API_URL` (default: `http://localhost:8080`) |
| Auth header | `x-api-key: <NEXT_PUBLIC_LANGGRAPH_API_KEY>` |
| SDK | `@langchain/langgraph-sdk` Client |

---

## Thread Management

### Create thread
```
POST /threads
Response: { thread_id: string }
```

### Reset
Client-side only: discard `threadId` and call create again.

---

## Text Message Stream

```
POST /threads/{threadId}/runs/stream
Content-Type: application/json

{
  "assistant_id": "agendai_agent",
  "input": {
    "messages": [{ "role": "user", "content": "<text>" }],
    "input_type": "text"
  },
  "stream_mode": "messages"
}
```

**Response**: Server-Sent Events stream.

Relevant event: `event: messages/partial`
```json
{
  "data": [
    {
      "id": "<msg-id>",
      "type": "ai",
      "content": "<accumulated text so far>"
    }
  ]
}
```

**Client behaviour**: Track `seen: Map<msgId, string>`; yield `fullText.slice(prev.length)`
as delta for each chunk. Ignore non-AI message types.

---

## Audio Message Stream

```
POST /threads/{threadId}/runs/stream
Content-Type: application/json

{
  "assistant_id": "agendai_agent",
  "input": {
    "messages": [{ "role": "user", "content": "[Mensagem de áudio]" }],
    "input_type": "audio",
    "audio_data": [/* Array<number> — Uint8Array of the audio blob */]
  },
  "stream_mode": "values"
}
```

**Response**: SSE stream.

Relevant event: `event: values`
```json
{
  "data": {
    "messages": [
      { "role": "assistant", "content": "<final reply text>" }
    ]
  }
}
```

**Client behaviour**: Iterate stream; on each `values` event, read
`chunk.data.messages[last]` where `role === "assistant"` or `type === "ai"`.
Return the last non-empty content found. Fallback: `"[Áudio processado]"`.

---

## Audio Encoding

| Property | Value |
|----------|-------|
| Mic recording MIME | `audio/webm` (MediaRecorder default) |
| File upload MIME | any `audio/*` (server handles format detection) |
| Wire encoding | `Array.from(new Uint8Array(await blob.arrayBuffer()))` |
| Field name | `audio_data` inside `input` object |

---

## Error Handling

| Condition | Client response |
|-----------|-----------------|
| Network / HTTP error | Replace assistant placeholder with "Erro ao processar mensagem. Tente novamente." |
| Audio error | Replace placeholder with "Erro ao processar áudio. Tente novamente." |
| Mic permission denied | `alert("Microfone não disponível")` → file upload remains available |
| Agent unreachable on load | Thread creation will fail; show connection error state |
