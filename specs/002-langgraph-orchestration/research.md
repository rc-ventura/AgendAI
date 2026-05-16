# Research: LangGraph Medical Scheduling Orchestration

**Feature**: 002-langgraph-orchestration
**Phase**: 0 — Research
**Date**: 2026-05-14

---

## Decision 1: LangGraph v1.0+ API — StateGraph Pattern

**Decision**: Usar `StateGraph` com `TypedDict` como estado compartilhado entre nós, `ToolNode` para execução automática de tool calls do LLM, e `add_conditional_edges` para roteamento dinâmico.

**Rationale**:
- `StateGraph` em v1.0+ é a API estável — substituiu `MessageGraph` legado
- `Annotated[list[AnyMessage], add_messages]` acumula mensagens automaticamente sem sobrescrever
- `ToolNode` despacha tool calls do LLM para as funções Python correspondentes sem código manual de switch/case
- Edges condicionais com `tools_condition` detectam automaticamente se o LLM retornou tool_call ou resposta final

**Alternativas consideradas**:
- `MessageGraph` (legado pre-v1.0) — descartado: depreciado em v1.0
- `create_react_agent` (prebuilt) — descartado: não suporta nós customizados (áudio, email, TTS); adequado apenas para agentes simples sem lógica de roteamento própria
- Loop manual de tool calls — descartado: `ToolNode` já resolve isso com menos código

**Imports corretos (LangGraph v1.0+)**:
```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import AnyMessage
from typing import Annotated
from langgraph.graph.message import add_messages
```

**Padrão de grafo para AgendAI**:
```
START
  ↓
detect_input_type
  ↓ (audio) ──────── transcribe_audio ──┐
  ↓ (text)                              ↓
                               chat_with_llm (GPT-4o-mini + 5 tools)
                                 ↓ (tool_call)    ↓ (mensagem final)
                               execute_tools      check_email_needed
                                 ↓ (loop)           ↓ (sim) ↓ (não)
                               chat_with_llm     send_email  |
                                                    ↓        |
                                              check_audio_response
                                                ↓ (audio)  ↓ (texto)
                                            synthesize_tts  END
                                                  ↓
                                                 END
```

---

## Decision 2: LangGraph Platform — Self-Hosted com langgraph-cli

**Decision**: Usar `langgraph-cli` para servir o grafo via API REST compatível com o Agent UI. O serviço sobe com `langgraph dev` (desenvolvimento) ou como container Docker em produção/compose.

**Rationale**:
- `langgraph.json` define o grafo exposto; o CLI cria automaticamente o servidor API
- O Agent UI (langchain-ai/agent-ui) espera o protocolo da LangGraph Platform API — não é necessário implementar manualmente
- Para demo local: `langgraph dev` usa SQLite como checkpointer (sem Redis/PostgreSQL)
- Para Docker Compose: imagem `langchain/langgraph-api` com `langgraph.json` montado

**langgraph.json**:
```json
{
  "dependencies": ["."],
  "graphs": {
    "agendai_agent": "./agent/graph.py:graph"
  },
  "env": ".env"
}
```

**Porta padrão**: 8123 (LangGraph Platform API)

**Alternativas consideradas**:
- FastAPI wrapper manual — descartado: Agent UI exige o protocolo LangGraph Platform; reimplementar é redundante
- LangGraph Cloud — descartado: requer conta paga, inviável para demo offline

---

## Decision 3: Agent UI — Interface do Paciente

**Decision**: Usar o repositório open-source `langchain-ai/agent-ui` (Next.js) conectado ao servidor LangGraph Platform na porta 8123.

**Rationale**:
- Criado especificamente para interagir com grafos LangGraph
- Suporta streaming de tokens, exibição de tool calls intermediários (visível ao avaliador)
- Zero código de frontend — apenas variável de ambiente `NEXT_PUBLIC_API_URL=http://localhost:8123`
- Dockerfile incluído no repositório — plug-and-play no Docker Compose

**Configuração necessária**:
```env
NEXT_PUBLIC_API_URL=http://localhost:8123
NEXT_PUBLIC_GRAPH_ID=agendai_agent
```

**Porta**: 3001 (para não conflitar com API REST na 3000)

**Alternativas consideradas**:
- LangGraph Studio (desktop) — descartado: ferramenta de dev, não adequado para paciente
- Chainlit — descartado: requer código Python adicional; Agent UI já resolve sem código extra
- HTML simples — descartado: user escolheu Agent UI explicitamente

---

## Decision 4: LangSmith — Observabilidade

**Decision**: Ativar tracing automático via variáveis de ambiente. Toda execução do grafo é rastreada sem código adicional.

**Rationale**:
- LangGraph integra com LangSmith nativamente quando `LANGCHAIN_TRACING_V2=true`
- Cada nó do grafo aparece como span; tool calls aparecem com input/output completos
- Projeto identificado por `LANGCHAIN_PROJECT=AgendAI`
- Sem alteração de código — configuração 100% por env vars

**Variáveis de ambiente necessárias**:
```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<chave_langsmith>
LANGCHAIN_PROJECT=AgendAI
```

**Alternativas consideradas**:
- OpenTelemetry manual — descartado: LangSmith é nativo ao LangGraph, zero overhead de setup
- Logs estruturados locais apenas — descartado: requisito explícito do desafio

---

## Decision 5: Gmail — Envio de E-mail sem N8N

**Decision**: Usar `smtplib` + Gmail SMTP com App Password para envio de e-mail direto do serviço Python.

**Rationale**:
- Gmail SMTP com App Password não exige OAuth2 flow — mais simples para demo containerizado
- `smtplib` está na stdlib Python — zero dependência nova
- App Password é gerado uma vez e injetado como env var
- Retry com `tenacity` (3 tentativas, backoff exponencial) — paridade com Flow D do N8N

**Configuração**:
```env
GMAIL_USER=conta@gmail.com
GMAIL_APP_PASSWORD=<app_password_16_chars>
```

**Alternativas consideradas**:
- Google API Python Client (OAuth2) — descartado: requer OAuth2 flow interativo, complexo em container
- Manter N8N apenas para email — descartado: cria acoplamento desnecessário e mantém dependência do N8N
- SendGrid/Resend — descartado: dependência externa nova não justificada para demo

---

## Decision 6: OpenAI — STT e TTS

**Decision**: Usar `openai` Python SDK para Whisper (STT) e TTS, mesma chave da API do LLM.

**Rationale**: Um único SDK, uma única `OPENAI_API_KEY`, mesma integração do N8N original.

**STT**: `client.audio.transcriptions.create(model="whisper-1", file=audio_bytes)`
**TTS**: `client.audio.speech.create(model="tts-1", voice="alloy", input=text)`

---

## Constitution Compliance Notes

| Princípio | Status | Nota |
|-----------|--------|------|
| I. AI-Assisted | ✅ | GPT-4o-mini com function calling; LangSmith observa cada decisão |
| I. Claude API | ⚠️ Exceção justificada | Desafio técnico exige OpenAI explicitamente (GPT-4o-mini, Whisper, TTS) |
| II. User-Centric | ✅ | Agent UI acessível via browser; fluxo de chat em 1 ação |
| II. WCAG 2.1 AA | ⚠️ Assumido | Agent UI é mantido pela LangChain — acessibilidade assumida; não auditada para este demo |
| III. Test-First | ✅ | pytest obrigatório; testes de nós antes da implementação |
| IV. P95 < 2s | ⚠️ Exceção justificada | LLM calls são network-bound (3-10s); target ajustado para <10s texto / <30s áudio conforme spec |
| IV. Observabilidade | ✅ | LangSmith traça cada nó, tool call e latência automaticamente |
| V. Simplicidade | ✅ | YAGNI; cada nó tem responsabilidade única; sem abstrações antecipadas |
