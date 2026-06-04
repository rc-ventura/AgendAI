# ADR-024 — Estratégia de Retry e Resiliência (Agent + API)

**Status:** Proposto — implementação mapeada na Spec 005 (P1)

**Data:** 2026-06-03

**Relacionado a:** [Spec 005 — Agent Hardening](../../specs/005-agent-hardening/spec.md)

---

## Contexto

A análise de produção na Fase 1 (Render) revelou que o sistema falha silenciosamente em
cenários transientes previsíveis:

**Observado em produção:**
```
openai.APIConnectionError: Connection error.
During task with name 'chat_with_llm'
# tenacity retried 2x → desistiu → run marcado como error → usuário não recebe resposta
```

**Mapeamento completo de gaps (análise estática + observação de produção):**

| Componente | Chamada externa | Tem retry? | Falha observada |
|-----------|----------------|-----------|----------------|
| `llm_core.py` | OpenAI GPT-4o-mini | ❌ | `APIConnectionError` em prod |
| `transcriber.py` | OpenAI Whisper | ❌ | Não observada, mesmo padrão |
| `api_client.py` | HTTP → API (6 métodos) | ❌ | Cold start Render → 502 |
| `tts.py` | OpenAI TTS | ✅ tenacity | OK |
| `email_sender.py` | Resend HTTP API | ✅ tenacity | OK (ADR-023) |
| `db/connection.js` | Postgres (startup) | ❌ | Falha se Postgres demora |
| `repositories/*.js` | Postgres (queries) | ❌ | Erros transientes não retentados |

**Por que falhas transientes acontecem no Render free tier:**
- Serviços dormem após 15 min → cold start de 30-60s na primeira request
- A API pode estar acordando quando o agente já tentou chamar ela
- OpenAI retorna 429 (RateLimitError) e 504 (timeout) sob carga
- Postgres (Neon free tier) pode ter latência de conexão variável

---

## Decisão

Aplicar retry estratificado por tipo de chamada, usando as bibliotecas já presentes no stack.
**Não introduzir novas abstrações** — usar tenacity (Python, já em `pyproject.toml`) e
`p-retry` (Node.js, padrão do ecossistema).

### Estratégia por camada

```
┌─────────────────────────────────────────────────────────┐
│  Agent Python                                           │
│                                                         │
│  llm_core.py     → tenacity (3x) + pybreaker (CB)      │
│  transcriber.py  → tenacity (3x)                        │
│  api_client.py   → tenacity (3x, só erros de conexão)  │
│                                                         │
│  tts.py          → tenacity ✅ (já implementado)        │
│  email_sender.py → tenacity ✅ (já implementado)        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  API Node.js                                            │
│                                                         │
│  db/connection.js   → async-retry (startup, 5x, 30s)   │
│  repositories/*.js  → p-retry (queries, 3x, só 5xx)    │
└─────────────────────────────────────────────────────────┘
```

---

## Especificação de Implementação

### 1. `llm_core.py` — retry + circuit breaker

O LLM é o componente mais crítico. Além de retry para falhas transientes, adicionar circuit
breaker (`pybreaker`) para fail-fast quando a OpenAI está fora por mais de 3 falhas seguidas.
Isso é a diferença entre retry (o que tenacity faz) e fail-fast (o que circuit breaker faz).

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import APIConnectionError, APITimeoutError, RateLimitError
import pybreaker

llm_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=30)

@llm_breaker
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
)
async def _call_llm(llm, messages):
    return await llm.ainvoke(messages)
```

**Por que circuit breaker aqui e não nos outros nós:**
- O LLM é chamado 2-3 vezes por run (input detection, tool processing, final answer)
- Sem CB, uma OpenAI fora do ar faz o grafo travar em cada nó, consumindo timeout
- O CB abre após 3 falhas e retorna erro imediato nos 30s seguintes — experiência previsível

### 2. `transcriber.py` — retry simples

Whisper é chamado uma vez por run de áudio. Retry simples sem CB (falha única, não repetida).

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
)
async def _call_whisper(client, audio_data): ...
```

### 3. `api_client.py` — retry só em erros de conexão

**Importante:** Retry apenas em `ConnectError` e `TimeoutException` — **não** em 4xx (erros
de negócio como 404/409 não devem ser retentados).

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
)
async def _request(self, method, path, **kwargs): ...
```

### 4. `db/connection.js` — retry no startup

```javascript
const asyncRetry = require('async-retry');

async function connectWithRetry(connectionString) {
  return asyncRetry(
    async (bail) => {
      const pool = createPool(connectionString);
      try {
        await pool.query('SELECT 1');
        return pool;
      } catch (err) {
        if (err.message.includes('DATABASE_URL')) bail(err); // erro permanente
        throw err; // erro transiente → retry
      }
    },
    { retries: 5, minTimeout: 1000, maxTimeout: 5000, factor: 2 }
  );
}
```

### 5. `repositories/*.js` — retry em queries

```javascript
const pRetry = require('p-retry');

const TRANSIENT = /ECONNREFUSED|timeout|Connection terminated|pool is shutting down/;

async function queryWithRetry(exec, sql, params = []) {
  return pRetry(() => exec.query(sql, params), {
    retries: 3,
    onFailedAttempt: (err) => {
      if (!TRANSIENT.test(err.message)) throw err; // 4xx, constraint → não retry
    },
  });
}
```

---

## O que NÃO fazer

**Não fazer retry em:**
- `4xx` da API interna (404 paciente não encontrado, 409 horário indisponível) — são erros
  de negócio, não falhas de infraestrutura. Retry mascararia o erro para o agente.
- Erros de constraint do Postgres (`UNIQUE violation`, `NOT NULL`) — são bugs, não transientes.
- Erros de autenticação OpenAI (`AuthenticationError`) — chave errada não muda com retry.

**Não fazer circuit breaker em:**
- `api_client.py` — a API pode estar acordando (cold start), não "falhando". O retry com
  backoff é o comportamento correto. CB causaria rejeição prematura de requests legítimas.
- `transcriber.py` / `tts.py` — chamados uma vez por run, CB não agrega valor.

---

## Alternativas consideradas

### `httpx` com `transport` retry nativo
O `httpx` suporta retry via `httpx.HTTPTransport(retries=3)`. Mais simples para `api_client.py`,
mas não oferece backoff exponencial nem controle por tipo de exceção. Descartado em favor do
tenacity pela consistência com o restante do agente.

### `asyncio-tenacity` (versão async-native)
O tenacity suporta funções async diretamente com `@retry` — não é necessária uma versão
separada. Descartado pela redundância.

### Resilience4j (Java) / Polly (.NET)
Não aplicável ao stack Node.js + Python.

### axios-retry (Node.js)
Funciona apenas com axios. A API usa `pg` (driver Postgres) diretamente, não axios.
`p-retry` é mais genérico e adequado para wrapping de queries.

---

## Consequências

### Positivas
- Falhas transientes do OpenAI (RateLimitError, TimeoutError) resolvidas automaticamente
- Cold start do Render não causa erros visíveis ao usuário — agente aguarda a API acordar
- Circuit breaker em `llm_core.py` dá feedback imediato quando a OpenAI está fora
- Startup da API Node.js robusto contra Postgres lento (Neon latência variável)
- Consistência: toda chamada externa tem política de retry explícita

### Negativas / Trade-offs
- `pybreaker` é nova dependência no agente Python (`pyproject.toml`)
- `async-retry` e `p-retry` são novas dependências no `api/package.json`
- Retry aumenta a latência percebida em caso de falha real (2+4+8s antes de desistir)
- Circuit breaker aberto bloqueia todos os usuários durante os 30s de reset — trade-off
  intencional (fail-fast > travar indefinidamente)

---

## Relação com outras decisões

- **ADR-023** (Resend): `email_sender.py` já tem tenacity implementado — padrão estabelecido
  aqui é a extensão desse padrão para os demais componentes.
- **ADR-012** (API client singleton): o retry envolve os métodos do singleton existente sem
  alterar a interface pública.
- **Spec 005 P1**: esta é a decisão técnica que embasa as tasks de implementação do P1.
- **Spec 005 P3** (Guardrails): circuit breaker em `llm_core.py` é o precursor — mesmo ponto
  de extensão onde os guardrails de input serão adicionados.
