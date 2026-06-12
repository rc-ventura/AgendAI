# Learning Lesson — Observability & Correlation ID (B9)

**Batch:** B9 · **Data:** 2026-06-12

---

## L1 — LangSmith já é o APM do agente: não duplicar com structlog

`LANGSMITH_TRACING=true` captura automaticamente, sem código:

| O que | Como aparece no LangSmith |
|-------|--------------------------|
| Cada nó LangGraph | Chain run com input/output do estado |
| Cada chamada LLM | LLM run com prompt, resposta, tokens, custo |
| Cada tool call | Tool run com args e resultado |
| Retries (tenacity) | `on_retry` event com contagem |
| Erros | Stack trace + estado no momento da falha |

Adicionar `structlog` com hooks por nó duplicaria essa informação com menos riqueza.
A decisão correta: LangSmith para observabilidade de negócio, Python `logging` padrão
para infra (erros de startup, Redis down).

---

## L2 — Conectar nginx ID à trace LangSmith via run metadata (BFF)

O caminho de correlação é:

```
nginx gera $request_id (hex 32 chars)
    ↓ header X-Request-ID
BFF (Next.js Route Handler)
    ↓ injeta metadata.request_id no body do POST /runs
LangGraph Server
    ↓ persiste metadata no checkpoint
LangSmith
    ↓ exibe request_id nos metadados do run → pesquisável
```

**Uma linha no BFF** (`route.ts`) conecta nginx ao LangSmith:
```typescript
metadata: { ...body.metadata, request_id: req.headers.get("x-request-id") }
```

O BFF já manipulava o body para injetar `durability: "exit"` (B3). Piggyback no mesmo hook.

---

## L3 — Separar `requestId.js` de `requestLogger.js` na API

Responsabilidades distintas:

| Middleware | Responsabilidade |
|-----------|-----------------|
| `requestId.js` | Ler/gerar ID, expor em `req.requestId`, setar header de resposta |
| `requestLogger.js` | Logar a requisição em JSON com o ID já disponível |

**Por que separar**: `requestId.js` pode ser unit-testado com mocks simples (req, res, next)
sem precisar do Express completo. `requestLogger.js` depende do ciclo de vida da resposta
(`res.on('finish')`). Responsabilidades distintas → testabilidade independente.

**Ordering**: `requestId` ANTES de `requestLogger`. Se invertidos, `req.requestId` seria
`undefined` no log.

---

## L4 — nginx `$request_id` vs UUID gerado pela API

| Fonte | Formato | Quando |
|-------|---------|--------|
| nginx `$request_id` | hex 32 chars (ex: `a3f7b2...`) | Requisição passou pelo nginx |
| `randomUUID()` (requestId.js) | UUID v4 (ex: `550e8400-e29b-...`) | Requisição direta à API (dev/teste) |

São funcionalmente equivalentes mas têm formatos diferentes. Em produção, **todas** as
requisições passam pelo nginx, então o formato será sempre hex. O fallback UUID é só para
desenvolvimento local sem nginx.

---

## L5 — `errorHandler.js` loga apenas 5xx, não 4xx

O `errorHandler.js` loga com `logger.error` apenas quando `status >= 500`. Erros 4xx
(validação, not found, unauthorized) são esperados e não precisam de alerta — só o
`requestLogger.js` os registra no log normal da requisição.

**Por que importa**: se o `errorHandler` logasse todo 4xx como error, os logs de produção
seriam poluídos com erros de validação normais, mascarando erros reais.

---

## L6 — UsageMetadata e ResponseMetadata: classes typed built-in para observabilidade

### `UsageMetadata` — tokens padronizados

```python
from langchain_core.messages import AIMessage, UsageMetadata

msg: AIMessage = ...
usage: UsageMetadata = msg.usage_metadata
# → {"input_tokens": 234, "output_tokens": 89, "total_tokens": 323}
```

É uma classe tipada (não só dict) — útil para type hints em testes e mypy. Toda
`AIMessage` do `ChatOpenAI` já a popula automaticamente. Para SC-008 (custo por conversa
flat), basta somar `usage_metadata["total_tokens"]` das `AIMessage`s no estado final.
LangSmith também exibe isso automaticamente por run — **nenhuma lib de cost-tracking
adicional é necessária**.

### `ResponseMetadata` — metadados brutos do provider

```python
msg.response_metadata
# → {
#     "finish_reason": "stop",        ← "stop" | "length" | "tool_calls" | "content_filter"
#     "model_name": "gpt-4o-mini",
#     "system_fingerprint": "fp_...",
# }
```

Contém informações específicas da API do provider que não se encaixam no modelo padrão
do LangChain. O campo mais útil para observabilidade é **`finish_reason`**:

| Valor | Significado |
|-------|-------------|
| `"stop"` | Resposta completada normalmente |
| `"length"` | Resposta truncada — atingiu `max_tokens` |
| `"tool_calls"` | Parou para chamar ferramentas |
| `"content_filter"` | Bloqueado pelo filtro de conteúdo do provider |

**Uso prático**: se o agente retorna respostas estranhas/incompletas, inspecionar
`finish_reason` é o primeiro passo — `"length"` indica que `max_tokens` está muito baixo.
Não há nada a implementar; o campo já existe em todo `AIMessage`.

### Distinção entre as duas

| Classe | Padronização | Conteúdo |
|--------|-------------|---------|
| `UsageMetadata` | LangChain (cross-provider) | Tokens in/out/total |
| `response_metadata` | Provider-específico | finish_reason, fingerprint, logprobs |

### Sobre E2E tracing ID

`UsageMetadata` e `response_metadata` monitoram **consumo e contexto da mensagem** —
não criam IDs de rastreamento. O ID de correlação E2E é responsabilidade do `RunTree`
(langsmith SDK) e do `RunnableConfig.metadata`, que é exatamente o que o B9 usa:
o BFF injeta `request_id` (do nginx) em `metadata` → LangSmith propaga automaticamente
pela árvore de execução inteira.
