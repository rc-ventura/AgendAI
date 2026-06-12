# ADR-031 — Structured Logging & Correlation ID (B9 / US5)

**Status:** Accepted  
**Data:** 2026-06-12  
**Spec relacionada:** [Spec 005 — Agent Hardening (B9/US5)](../../specs/005-agent-hardening/spec.md)  
**Depende de:** [ADR-026](./ADR-026-create-agent-middleware-vs-manual.md) (create_agent), [ADR-029](./ADR-029-guardrails.md) (PII — logs MUST NOT contain raw PII)

---

## Contexto

FR-018..020 exigem que cada requisição carregue um `request_id` rastreável do nginx até o
LangSmith, com logs estruturados em JSON e sem PII. O contrato (SC-012) define três outcomes
testáveis: mesma ID em todos os serviços, trace pesquisável em < 5 min, ID presente em linhas
de erro.

---

## Decisão

**Gerar `X-Request-ID` no nginx e propagar como header; API loga JSON com pino; agente conecta
o ID à trace LangSmith via run metadata no BFF. LangSmith é o layer de observabilidade do
agente — sem structlog ou nova dep Python.**

---

## Implementação por camada

### nginx (`nginx/nginx.conf.template`)

```nginx
proxy_set_header X-Request-ID $request_id;
```

`$request_id` é uma variável built-in do nginx ≥ 1.11.0 — string hex de 32 caracteres,
única por conexão. Propagada para todos os upstreams (API via porta interna, LangGraph Server).

### API — `requestId.js` + `requestLogger.js` + `errorHandler.js`

```
requestId → requestLogger → routes → errorHandler
```

- **`requestId.js`**: aceita `X-Request-ID` inbound ou gera UUID; expõe em `req.requestId`;
  define header de resposta. Separado do `requestLogger` para reutilização e testabilidade.
- **`requestLogger.js`**: loga JSON via pino com `request_id`, `service: "api"`, `event`,
  `method`, `path`, `status_code`, `duration_ms`.
- **`errorHandler.js`**: loga `level: error` com `request_id` em erros 5xx.

Campos do log JSON (pino):

```json
{"level":30,"time":1749730800000,"request_id":"a0f5...","service":"api","event":"http.request","method":"GET","path":"/horarios","status_code":200,"duration_ms":12}
```

### Agente — LangSmith como observability layer

O agente não recebe nova biblioteca. LangSmith (`LANGSMITH_TRACING=true`) já captura
automaticamente, por run:
- Cada nó do grafo LangGraph com inputs/outputs
- Cada chamada LLM (tokens, custo, latência)
- Cada tool call com request/response
- Erros com stack trace e contexto

**Conexão nginx ID → trace LangSmith** (BFF — `route.ts`):
```typescript
metadata: { ...body.metadata, request_id: req.headers.get("x-request-id") }
```
O `request_id` do nginx aparece nos metadados do run no LangSmith — a trace é pesquisável
por esse ID em < 5 min (SC-012).

### Agente — `logging_config.py` (infra logs)

JSON formatter mínimo sobre Python `logging` padrão. Cobre erros de startup e falhas de
infraestrutura fora do grafo (Redis, variáveis de ambiente). Zero nova dependência.

```python
{"ts": "...", "level": "ERROR", "service": "agent", "event": "Redis connection refused"}
```

---

## Alternativas consideradas

### A) structlog completo com bind de `request_id` por nó

Cada nó do grafo bindaria `request_id` via `structlog.contextvars`. Rejeitado: LangSmith
já captura tudo com mais riqueza (inputs, outputs, tokens, latência por step). `structlog`
seria redundante para observabilidade de negócio e adicionaria uma dependência nova.

### B) Usar LangGraph `run_id` como correlation ID cross-service

O `run_id` de cada execução LangGraph é o ID nativo da trace LangSmith. Poderia ser
propagado de volta ao browser como `X-Request-ID`. Rejeitado: o `run_id` só existe depois
que o run é criado — nginx precisa gerar o ID antes de qualquer routing.

### C) OpenTelemetry / Jaeger

Overkill para o estágio atual. LangSmith cobre o agente; pino cobre a API.

---

## Consequências

### Positivas

- SC-012: um `request_id` rastreia nginx → API logs → LangSmith trace
- API logs são JSON pesquisáveis (grep/jq em `docker logs api`)
- Erros 5xx loggam `request_id` para correlação imediata
- Zero nova dependência Python — `logging` padrão
- 48 Jest verdes (41 anteriores + 7 novos de B9)

### Negativas / riscos

- Logs de container do agente não têm `request_id` por linha de execução — apenas em
  erros de startup. LangSmith resolve para rastreabilidade de negócio.
- nginx `$request_id` é hex (não UUID) — diferente do UUID gerado pela API quando o
  header não chega. Formato inconsistente mas funcionalmente equivalente.

---

## Relação com outras decisões

- **ADR-029**: logs MUST NOT conter PII — `requestLogger.js` não loga body/headers de
  request; `errorHandler.js` não loga `err.stack` (que poderia vazar dados internos).
- **ADR-030**: `context_summary` no estado pode ser incluído em logs estruturados como
  campo de observabilidade do contexto ativo.
