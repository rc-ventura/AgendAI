# ADR-014: Checkpointer in-memory do LangGraph para MVP (sem persistência entre restarts)

**Status**: Accepted  
**Data**: 2026-05-17  
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)  
**Código**: `agent/pyproject.toml` (`langgraph-cli[inmem]`)  
**Depende de**: [ADR-013](./ADR-013-langgraph-dev-server.md)

---

## Contexto

O `langgraph dev` (ADR-013) gerencia o checkpointer internamente. O extra `[inmem]` instalado em `pyproject.toml` fornece a implementação in-memory desse checkpointer — os threads (histórico de conversa) vivem na RAM do container e são perdidos em qualquer restart.

Isso produz um **mismatch** observável na UI:

```
1. Usuário conversa → threadId salvo no URL query param (?threadId=019e35d2-...)
2. docker compose down && docker compose up → container agent recriado
3. Browser reabre com o threadId antigo na URL
4. SDK dispara POST /threads/{id}/history → LangGraph retorna 404
5. Erro aparece no console: "Thread with ID ... not found"
```

O `agent-ui-pro` trata esse erro em `Stream.tsx` (`onError`) e em `Thread/index.tsx` (watch de `stream.error`): ao detectar o 404, limpa o `threadId` da URL e abre uma nova conversa silenciosamente. O usuário não vê mensagem de erro — apenas a tela de nova conversa.

A pergunta é: vale adicionar persistência real agora?

## Decisão

Manter `langgraph-cli[inmem]` e checkpointer in-memory para o MVP. O mismatch UI/servidor é tratado defensivamente na camada do cliente. Não adicionar infraestrutura de banco de dados neste momento.

## Alternativas consideradas

### Alternativa A: PostgreSQL como backend do checkpointer

Trocar `langgraph-cli[inmem]` por `langgraph-cli` (sem extra) + adicionar serviço `postgres` ao `docker-compose.yml`. O `langgraph dev` aceita `DATABASE_URL` e usa PostgreSQL automaticamente.

```yaml
# docker-compose.yml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: langgraph
    POSTGRES_USER: langgraph
    POSTGRES_PASSWORD: langgraph
  volumes:
    - pgdata:/var/lib/postgresql/data

agent:
  environment:
    - DATABASE_URL=postgresql://langgraph:langgraph@postgres:5432/langgraph
```

```toml
# pyproject.toml
"langgraph-cli>=0.1.55",  # sem [inmem]
"langgraph-checkpoint-postgres>=2.0",
```

**Por que não escolhido agora**:
- Adiciona um serviço novo (`postgres`) ao compose — aumenta complexidade de setup.
- Exige que o Postgres esteja healthy antes do agente iniciar (`depends_on` + healthcheck).
- Para um desafio técnico / MVP, a persistência entre restarts não é requisito funcional.
- O trade-off pode ser **explicado** como decisão consciente, o que demonstra maturidade arquitetural.

**Quando escolher**: projeto promovido a produção, ou quando paciente precisar retomar conversa após restart do servidor.

### Alternativa B: SqliteSaver customizado no graph.py

Compilar o grafo com checkpointer SQLite explícito e montar volume:

```python
# agent/agent/graph.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async with AsyncSqliteSaver.from_conn_string("/app/data/langgraph/checkpoints.db") as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
```

```yaml
# docker-compose.yml
agent:
  volumes:
    - ./data/langgraph:/app/data/langgraph
```

**Por que não escolhido**:
- O `langgraph dev` injeta seu próprio checkpointer na compilação do grafo — o checkpointer declarado no código pode ser ignorado ou conflitar com o gerenciamento de threads da plataforma.
- Comportamento não documentado: a interação entre checkpointer customizado e o runtime do `langgraph dev` é imprevisível em versões futuras do CLI.
- Exigiria testes de integração para validar que a persistência realmente funciona com o SDK.

### Alternativa C: FastAPI/uvicorn customizado

Implementar servidor próprio com FastAPI, gerenciando threads e checkpointer manualmente.

**Por que não escolhido**: reimplementaria por conta própria toda a API REST/SSE do `langgraph-cli` (`/threads`, `/runs`, `/stream`, `/assistants`, etc.), perdendo compatibilidade com LangGraph Studio e o `@langchain/langgraph-sdk`. Ver ADR-013 para análise detalhada.

## Consequências

### Aceitas

- **Setup mínimo**: `docker compose up --build -d` não exige Postgres ou Redis.
- **Histórico por sessão**: dentro de uma sessão Docker ativa, o histórico funciona normalmente — threads são criados, listados no sidebar, e retomados via `threadId` na URL.
- **Tratamento defensivo na UI**: o `agent-ui-pro` detecta o 404 de thread não encontrado e reseta a conversa silenciosamente, sem expor erro ao usuário.
- **Demonstração clara do trade-off**: o comportamento e sua causa são documentados e explicáveis, o que é suficiente para o contexto de desafio técnico.

### Trade-offs assumidos

- **Perda de histórico em restarts**: qualquer `docker compose down` apaga todos os threads. Sem `-v`, pois o LangGraph não usa volumes nomeados — os dados ficam no filesystem interno do container.
- **Ruído no console**: o SDK dispara `POST /threads/{id}/history` antes do handler React estar pronto, gerando um `Uncaught (in promise) HTTP 404` no DevTools. Não afeta o usuário final.
- **Sidebar vazia após restart**: o histórico lateral aparece vazio após cada restart, mesmo que o usuário tenha conversas anteriores.

### Condições que invalidam esta decisão

1. **Requisito de persistência real**: paciente ou clínica precisar recuperar histórico de consultas após downtime.
2. **Ambiente de produção**: qualquer deploy público exige backend durável (PostgreSQL).
3. **Múltiplas instâncias**: escala horizontal exige store compartilhado — in-memory é por definição single-node.

### Caminho de migração

```
MVP atual (inmem)
    ↓
Adicionar postgres ao compose + DATABASE_URL no agent
    ↓  (mudança de ~15 linhas, zero no código do grafo)
langgraph dev com PostgreSQL durável
    ↓
langgraph up (produção, se necessário escalar)
```

## Referências

- ADR-013: decisão de usar `langgraph dev` como servidor
- LangGraph checkpointers: <https://langchain-ai.github.io/langgraph/concepts/persistence/>
- `agent-ui-pro/src/providers/Stream.tsx` — `onError` handler para 404 de thread
- `agent-ui-pro/src/components/thread/index.tsx` — detecção de "Thread with ID ... not found"
