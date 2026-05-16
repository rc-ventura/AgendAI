# ADR-013: `langgraph dev` como servidor do agente (em vez de `langgraph up` / `langchain/langgraph-api`)

**Status**: Accepted
**Data**: 2026-05-16
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/Dockerfile:12`

---

## Contexto

O agente LangGraph precisa ser exposto via HTTP para que o `agent-ui` (Next.js) e clientes externos possam consumir. A LangChain fornece três caminhos principais para servir um `StateGraph`:

1. **`langgraph dev`** — servidor de desenvolvimento embutido no `langgraph-cli`. Single-process, auto-reload, checkpointer SQLite local/efêmero.
2. **`langgraph up`** — orquestra a stack completa do LangGraph Platform: imagem `langchain/langgraph-api` + Redis (fila assíncrona) + Postgres (checkpointer durável).
3. **FastAPI / uvicorn customizado** — escrever o próprio servidor importando o `graph` compilado e definindo endpoints à mão.

O projeto AgendAI é o entregável de um **desafio técnico**, com escopo de MVP / demonstração:

- Roda inteiramente em `docker compose up` localmente, em um único host.
- Não há SLA, não há tráfego real, não há requisito de escala horizontal.
- A spec assume explicitamente que **"histórico de conversa é mantido em memória por sessão (sem persistência entre reinicializações do container)"** (`specs/002-langgraph-orchestration/spec.md:184`).
- O objetivo é demonstrar o fluxo LLM + tools + áudio + observabilidade — não construir infraestrutura production-grade.

## Decisão

Usar **`langgraph dev`** como `CMD` do `agent/Dockerfile`:

```dockerfile
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]
```

O servidor é exposto **apenas internamente** na rede Docker (porta `127.0.0.1:8123` no host), com o nginx (`nginx/nginx.conf.template`) atuando como proxy reverso público na porta `8080`, fornecendo autenticação, rate limiting e CORS (ver ADR-014 quando documentado).

## Alternativas consideradas

### Alternativa A: `langgraph up` (stack Platform completa)

Imagem `langchain/langgraph-api` + Redis + Postgres orquestrados via `langgraph up`.

**Por que não escolhido**:
- Adiciona 2 containers extras (Redis + Postgres) ao `docker-compose.yml`.
- Postgres exige migrations, volumes, backups — overhead operacional alto.
- Para uma demonstração de MVP, a complexidade não traz benefício mensurável.
- O `docker compose up --build -d` deixaria de ser "um comando para subir tudo" e exigiria etapas extras de inicialização do banco.

**Vantagens** (não aproveitadas no MVP):
- Persistência durável de threads (sobrevive a deploys/restarts).
- Fila Redis para execuções long-running.
- Workers separados, escala horizontal.

### Alternativa B: FastAPI/uvicorn customizado

Escrever um `server.py` com FastAPI importando o `graph` e expondo endpoints à mão, rodando com `uvicorn --workers 4`.

```python
# agent/agent/server.py (hipotético)
from fastapi import FastAPI
from agent.graph import graph
app = FastAPI()
# ... endpoints /threads, /runs, /runs/stream ...
```

**Por que não escolhido**:
- Reimplementaria por conta própria a API REST/SSE que o `langgraph-cli` já fornece (threads, runs, streaming, assistants).
- Quebra a compatibilidade com o **LangGraph Studio** (`smith.langchain.com/studio/?baseUrl=...`), que espera a API REST padrão do `langgraph-cli`.
- Mais código para manter sem ganho funcional no MVP.

## Consequências

### Aceitas

- **Setup mínimo**: `docker compose up --build -d` sobe tudo, sem dependências externas (Postgres/Redis).
- **Compatível com LangGraph Studio** out-of-the-box — basta apontar para `http://localhost:8123` no Studio.
- **Auto-reload em desenvolvimento**: editar arquivos `.py` no host (com volume montado) recarrega o agente sem rebuild do container.
- **Logs verbosos** facilitam debug do grafo e das tool calls durante o desenvolvimento.
- **Compatibilidade SDK**: o `@langchain/langgraph-sdk` no `agent-ui/src/lib/langgraph.ts` conversa com a API padrão do `langgraph dev` sem ajustes.

### Trade-offs assumidos

- **Estado efêmero**: o checkpointer padrão do `langgraph dev` mantém threads em SQLite local dentro do container. Em um restart (`docker compose restart agent`), **todas as threads são perdidas**. Para o MVP isto é aceitável e está alinhado com a spec.
- **Single-process**: não escala horizontalmente. Sob carga, requests serão serializados no event loop. Aceitável para demo, inadequado para produção.
- **Auto-reload em produção é perigoso**: se algum processo CI/CD por engano fizer `git pull` num volume montado, o agente reinicia sozinho. Mitigado pelo fato de o `docker-compose.yml` não montar volume de código (o `COPY . .` no Dockerfile congela o código na imagem).
- **Stack traces verbosos** podem aparecer em logs e potencialmente em respostas HTTP de erro, vazando paths internos. Mitigado pelo nginx, que está na frente — mas o nginx **não** sanitiza corpo de resposta atualmente.
- **Sem graceful shutdown**: requests em voo podem ser cortados num `docker compose down`. Aceitável para demo.

### Condições que invalidam esta decisão

Esta decisão deve ser **revisitada** se:

1. **O projeto for promovido a produção real** com SLA, usuários reais ou requisitos de uptime.
2. **Histórico de conversa precisar persistir entre deploys** (ex.: paciente retomar conversa após restart do container).
3. **Volume de requests exigir escala horizontal** (múltiplos workers, balanceador de carga).
4. **Logs/erros começarem a vazar informação sensível** em ambientes públicos.
5. **Auditoria de segurança** exigir hardening do servidor HTTP (rate limiting nativo, request size limits, etc. — atualmente delegados ao nginx).

### Caminho de migração quando necessário

Em ordem crescente de complexidade:

1. **Mais simples**: trocar `CMD` por `langgraph up` (exige acrescentar Redis + Postgres ao compose).
2. **Médio**: manter `langgraph dev` mas adicionar `PostgresSaver` como checkpointer custom no `agent/agent/graph.py`:
   ```python
   from langgraph.checkpoint.postgres import PostgresSaver
   checkpointer = PostgresSaver.from_conn_string(os.environ["POSTGRES_URL"])
   graph = builder.compile(checkpointer=checkpointer)
   ```
3. **Mais flexível**: substituir por FastAPI/uvicorn customizado, com a estrutura de endpoints que o time precisar.

## Referências

- Discussão original: Devin Review flag em PR #2.
- LangGraph CLI docs: <https://langchain-ai.github.io/langgraph/cloud/reference/cli/>
- Spec do projeto sobre estado em memória: `specs/002-langgraph-orchestration/spec.md:184`
- ADR-012 (singleton do `ApiClient` sob asyncio) — depende implicitamente desta decisão, já que `langgraph dev` roda como evento loop asyncio single-thread.
