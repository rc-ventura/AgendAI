# ADR-003: Conversação stateless por sessão

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/state.py`, `agent/agent/graph.py`

---

## Contexto

O agente de agendamento médico processa conversas com pacientes. Cada interação precisa de contexto (histórico de mensagens, resultados de tool calls), mas o sistema é um MVP sem requisitos de persistência de longo prazo.

## Decisão

Manter **conversação stateless por thread** — o estado da conversa (`AgendAIState`) vive apenas durante a execução do grafo. O histórico é gerenciado pelo checkpointer do LangGraph (in-memory no MVP, ver ADR-014), vinculado a um `thread_id`. Nenhum estado de conversa é persistido no banco SQLite da API.

## Alternativas consideradas

### Alternativa A: Persistir conversas no SQLite da API
**Por que não**: Adicionaria tabela `conversas` e lógica de save/load no meio do grafo. Complexidade desnecessária quando o LangGraph já oferece checkpointer nativo.

### Alternativa B: Session storage no frontend (localStorage)
**Por que não**: Histórico ficaria apenas no browser do paciente — sem correlação com o servidor, sem possibilidade de auditoria ou LangSmith tracing.

### Alternativa C: Redis como session store
**Por que não**: Adiciona serviço extra ao compose. Checkpointer in-memory do LangGraph resolve para MVP.

## Consequências

### Aceitas
- **Simplicidade**: estado da conversa é o `TypedDict` Python — sem serialização, sem schema de banco.
- **Isolamento por thread**: `thread_id` garante que conversas de pacientes diferentes não se misturam.
- **LangSmith tracing**: cada execução do grafo é uma trace independente, correlacionada por `thread_id`.

### Trade-offs
- **Histórico perdido em restart**: checkpointer in-memory (ADR-014) perde todas as threads no `docker compose down`.
- **Sem retomada cross-device**: paciente que começa no desktop não continua no celular.
- **Crescimento de memória**: threads ativas acumulam mensagens na RAM do container.

### Condições que invalidam
1. Necessidade de retomar conversa após restart → persistir checkpointer (ADR-014, fase 1).
2. Cross-device continuity → session store externa (Redis/PostgreSQL).
3. Auditoria de conversas → persistir histórico completo em banco.

## Referências

- `agent/agent/state.py` — `AgendAIState` TypedDict
- `agent/agent/graph.py` — `StateGraph` com `add_messages`
- ADR-014: checkpointer in-memory
