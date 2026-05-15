# Contract: LangGraph Platform API

**Tipo**: REST + SSE (Server-Sent Events)
**Servidor**: `langgraph-cli` / `langgraph-api` Docker image
**Base URL**: `http://localhost:8123`
**Grafo exposto**: `agendai_agent` (definido em `langgraph.json`)

---

## Endpoints utilizados pelo Agent UI

### POST /threads
Cria uma nova thread (sessão de conversa).

**Request**:
```json
{
  "metadata": {}
}
```
**Response `201`**:
```json
{
  "thread_id": "uuid-v4",
  "created_at": "2026-05-14T10:00:00Z",
  "metadata": {}
}
```

---

### POST /threads/{thread_id}/runs/stream
Executa o grafo em modo streaming para uma thread existente. O Agent UI usa este endpoint para exibir tokens em tempo real.

**Request**:
```json
{
  "assistant_id": "agendai_agent",
  "input": {
    "messages": [
      { "role": "human", "content": "Quais horários disponíveis?" }
    ]
  },
  "stream_mode": ["values", "messages"]
}
```

**Response**: `text/event-stream` (SSE)
```
data: {"event": "metadata", "data": {"run_id": "uuid"}}

data: {"event": "messages/partial", "data": [{"type": "AIMessageChunk", "content": "Aqui"}]}

data: {"event": "messages/partial", "data": [{"type": "AIMessageChunk", "content": " estão"}]}

data: {"event": "values", "data": {"messages": [...], "final_response": "Aqui estão os horários..."}}

data: {"event": "end"}
```

---

### POST /threads/{thread_id}/runs/stream (Áudio)
Para entrada de áudio, o conteúdo é enviado como base64 dentro do campo `messages`.

**Request**:
```json
{
  "assistant_id": "agendai_agent",
  "input": {
    "messages": [
      { "role": "human", "content": "", "additional_kwargs": {"audio_b64": "<base64>"} }
    ],
    "input_type": "audio"
  },
  "stream_mode": ["values"]
}
```

---

### GET /threads/{thread_id}/runs/{run_id}
Consulta o status de uma execução.

**Response**:
```json
{
  "run_id": "uuid",
  "thread_id": "uuid",
  "status": "success",
  "output": {
    "messages": [...],
    "final_response": "Consulta agendada com sucesso!"
  }
}
```

---

## Configuração do langgraph.json

```json
{
  "dependencies": ["."],
  "graphs": {
    "agendai_agent": "./agent/graph.py:graph"
  },
  "env": ".env"
}
```

---

## Variáveis de Ambiente do Servidor

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `OPENAI_API_KEY` | ✅ | GPT-4o-mini, Whisper, TTS |
| `LANGCHAIN_TRACING_V2` | ✅ | `true` para ativar LangSmith |
| `LANGCHAIN_API_KEY` | ✅ | Chave LangSmith |
| `LANGCHAIN_PROJECT` | ✅ | `AgendAI` |
| `API_BASE_URL` | ✅ | `http://api:3000` (nome do serviço no Compose) |
| `GMAIL_USER` | ✅ | Conta Gmail remetente |
| `GMAIL_APP_PASSWORD` | ✅ | App Password de 16 caracteres |
