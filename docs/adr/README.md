# Architecture Decision Records (ADRs)

Este diretório consolida as **decisões arquiteturais** do projeto AgendAI. Cada ADR registra uma decisão técnica significativa: o contexto que motivou, as opções consideradas, a escolha final e suas consequências.

## Formato

Cada ADR segue o template:

```markdown
# ADR-XXX: Título da Decisão

**Status**: Proposed | Accepted | Superseded by ADR-YYY | Deprecated
**Data**: YYYY-MM-DD
**Spec relacionada**: 001-... | 002-... | —

## Contexto
O problema, as forças em jogo, o ambiente.

## Decisão
A escolha feita, em uma frase.

## Alternativas consideradas
Outras opções e por que foram descartadas.

## Consequências
Trade-offs aceitos, riscos conhecidos, condições futuras
que invalidariam a decisão.
```

## Índice

| ADR | Título | Status | Spec |
|---|---|---|---|
| [ADR-001](./ADR-001-node-express.md) | Stack da API REST: Node.js 20 + Express 4 | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-002](./ADR-002-sqlite-better-sqlite3.md) | Banco SQLite via `better-sqlite3` síncrono | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-003](./ADR-003-stateless-conversation.md) | Conversação stateless por sessão | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-004](./ADR-004-gpt-4o-mini.md) | GPT-4o-mini para LLM com function calling | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-006](./ADR-006-openai-whisper.md) | OpenAI Whisper para STT | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-007](./ADR-007-openai-tts.md) | OpenAI TTS para síntese de voz | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-011](./ADR-011-caminhos-evolutivos.md) | Caminhos evolutivos da arquitetura AgendAI (v2+) | 📋 Proposed | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-012](./ADR-012-apiclient-singleton-async.md) | `ApiClient` como singleton de módulo sob asyncio | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-013](./ADR-013-langgraph-dev-server.md) | `langgraph dev` como servidor do agente (MVP) | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-014](./ADR-014-checkpointer-inmem.md) | Checkpointer in-memory do LangGraph para MVP | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-015](./ADR-015-langgraph-vs-n8n.md) | LangGraph como orquestrador de IA em substituição ao n8n | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/), [002](../../specs/002-langgraph-orchestration/) |
| [ADR-016](./ADR-016-nginx-reverse-proxy.md) | Nginx como proxy reverso com autenticação, rate limiting e CORS | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/), [003](../../specs/003-professional-chat-ui/) |
| [ADR-017](./ADR-017-api-security-tokens.md) | Segurança da API REST e token de credencial do LangGraph | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-018](./ADR-018-polyglot-node-python.md) | Arquitetura polyglot — API REST em Node.js + Agente de IA em Python | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/), [002](../../specs/002-langgraph-orchestration/) |
| [ADR-019](./ADR-019-agent-ui.md) | Agent UI open-source da LangChain como interface de chat | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/), [003](../../specs/003-professional-chat-ui/) |
| [ADR-020](./ADR-020-docker-compose.md) | Docker Compose como plataforma de orquestração de containers | ✅ Accepted | [001](../../specs/001-n8n-medical-scheduling/), [002](../../specs/002-langgraph-orchestration/) |
| [ADR-021](./ADR-021-langsmith-observability.md) | LangSmith como plataforma de observabilidade para tracing do agente | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |


## Como adicionar um novo ADR

1. Use o próximo número livre na sequência (`ADR-013`, `ADR-014`, ...).
2. Crie o arquivo `docs/adr/ADR-XXX-titulo-kebab-case.md` seguindo o template acima.
3. Adicione uma linha na tabela de índice acima.
4. Linke o ADR a partir do código (comentário) ou da spec relacionada quando aplicável.
5. Ao **substituir** ou **descontinuar** um ADR, atualize o status e referencie o novo ADR que o substitui.
