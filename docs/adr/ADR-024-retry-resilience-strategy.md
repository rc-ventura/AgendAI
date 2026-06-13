# ADR-024 — Estratégia de Retry e Resiliência (Agent + API)

**Status:** Implementado (B6 — 2026-06-10 · API-side B6 — 2026-06-11) — aguarda commit manual

**Data:** 2026-06-03 | **Última atualização:** 2026-06-10

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

---

## Notas de Implementação (B6 — 2026-06-10)

### Desvio: pybreaker → CircuitBreaker customizado

O ADR original especificava `pybreaker` como circuit breaker. Na implementação, `pybreaker 1.4.1`
usa `@gen.coroutine` do Tornado para suporte async — incompatível com asyncio puro. A lib foi
removida e substituída por uma classe `CircuitBreaker` de ~30 linhas em `agent/agent/resilience.py`.

Ver learning lesson completa: `docs/learning-lessons/circuit_breaker_custom_vs_libs.md`

Esta abordagem é consistente com o que a comunidade de agentes de IA faz em produção: toda
referência encontrada usa implementações customizadas, não libs genéricas.

### Desvio: transcriber.py / tts.py removidos (B5)

O ADR especificava retry em `transcriber.py` e `tts.py`. Ambos foram eliminados no B5 (ADR-028)
com a migração para o modelo `gpt-audio` que processa áudio nativo. Retry em STT/TTS não se aplica.

### Arquivo de resiliência extraído

Todo código de retry e circuit breaker reside em `agent/agent/resilience.py` — **não** em
`llm_core.py`. Exporta `CircuitBreaker`, `CircuitOpenError`, `llm_breaker` (singleton),
`invoke_with_resilience`, `PT_BR_UNAVAILABLE`, `RETRYABLE_EXCEPTIONS`. Reutilizável pelo
`CircuitBreakerMiddleware` planejado no B7 (ADR-026).

### Lambda vs. async def no tenacity

O decorator `@retry` do tenacity detecta `asyncio.iscoroutinefunction()` para decidir entre
`Retrying` (sync) e `AsyncRetrying`. Um lambda que retorna coroutine é **sync** para o tenacity
— ele nunca atrasa as tentativas, pois não vê a exception (a coroutine não foi awaited).
**Solução:** sempre usar `async def` como função base antes de decorar com `@retry`.

### Observabilidade do Circuit Breaker

O `CircuitBreaker` emite logs Python estruturados em três eventos:

| Evento | Nível | Mensagem |
|---|---|---|
| Circuito abre | WARNING | `circuit_breaker=open fails=3 reset_in=30s` |
| Call bloqueada (circuito aberto) | WARNING | `circuit_breaker=blocked remaining=Xs` |
| Circuito fecha (sucesso após OPEN) | INFO | `circuit_breaker=closed` |

Esses logs aparecem no `docker compose logs langgraph-server` e, via LangSmith callback,
nas traces do agente quando `LANGSMITH_TRACING=true`.

### Gap vs. modelo completo (Hannecke)

A implementação atual cobre apenas **hard failures** (1 de 5 categorias). O modelo completo
adiciona estados DEGRADED e HALF-OPEN, health score com decay, e detecção de falhas semânticas.
Ver `docs/learning-lessons/circuit_breaker_custom_vs_libs.md` para upgrade path detalhado.

### CircuitBreaker é singleton de processo — implicações de escala

`llm_breaker` e `api_breaker` em `agent/agent/resilience.py:69-70` são instâncias **a nível de
módulo**, criadas uma vez no import. O estado (`_fails`, `_opened_at` em
`agent/agent/resilience.py:33-34`) vive **na memória de um único processo Python**. Todos os runs
do grafo nesse processo compartilham o mesmo breaker.

**Por que isso é o comportamento CORRETO hoje:** se a OpenAI está fora, está fora para todos. O
breaker existe justamente para detectar uma falha de infraestrutura global e parar de martelar o
serviço caído — compartilhar o estado entre requests é a *feature* (visibilidade cross-request),
não um defeito. Quando o circuito abre (`agent/agent/resilience.py:61-62`), todos os pacientes
recebem `PT_BR_UNAVAILABLE` por 30s; é o fail-fast global desejado.

**Deploy atual = réplica única.** O serviço `langgraph-server` em `docker-compose.yml` é definido
uma vez, sem `deploy.replicas` nem `--scale` — há **1 processo** do agente. Logo existe **1**
`llm_breaker`, de fato global. Não há dívida técnica a corrigir neste estágio (clínica única,
baixa concorrência).

**Onde a escala quebra a premissa — duas dimensões distintas:**

| Dimensão | O que acontece | Quando vira problema | Mitigação |
|---|---|---|---|
| **N réplicas** (escala horizontal) | Cada processo tem seu próprio breaker em memória → N×3 falhas antes de todos abrirem; uma réplica não avisa as outras. O "fail-fast global" deixa de ser global. | Render/orquestrador rodando >1 instância do `langgraph-server` | Mover o estado do breaker (`_fails`, `_opened_at`) para o **Redis** já presente no stack (`docker-compose.yml`, `REDIS_URI`) — breaker compartilhado entre processos |
| **Multi-tenant** (Spec 006+) | Um único breaker global: o tenant A que dispara o circuito derruba o tenant B (blast radius grande demais) | Quando houver `tenant_id`/`user_id` autenticado (Spec 006) | Breaker chaveado por tenant — `dict[str, CircuitBreaker]` por `tenant_id`, em vez de singleton |

**Distinção importante:** as duas mitigações são ortogonais e independentes:
- *Redis-backed* resolve a fragmentação entre **processos** (escala horizontal), mantendo o breaker
  global por tenant.
- *Por-tenant* resolve o blast radius entre **clientes** (multi-tenancy), e pode coexistir com o
  estado em memória (1 réplica) ou em Redis (N réplicas).

Para uma falha de infraestrutura genuinamente global (OpenAI inteira fora, rate limit da conta), o
singleton de processo continua correto em qualquer escala — o por-tenant só importa quando o limite
de falha é por fatia de tráfego (ex.: rate limit por cliente).

**Nota sobre `close()` e thread-safety:** `CircuitBreaker.close()` (`agent/agent/resilience.py:36-39`)
existe para isolamento entre testes e **não é thread-safe**. Aceitável: testes rodam serialmente e a
produção usa asyncio single-threaded. Um breaker Redis-backed (acima) precisaria de operações
atômicas (ex.: `INCR`) para o incremento de falhas sob concorrência real.

---

## Notas de Implementação — API-side (2026-06-11)

### `db/init.js` — startup retry

`initializeWithRetry(pool, initSchema, seed)` usa `p-retry` (4 retries, exp 1→5s, factor 2).
Abort imediato em erros de autenticação (`EAUTH` / "password"). Chamado em `server.js` antes
de `app.listen`.

### `db/withRetry.js` — query retry

`withDbRetry(fn)` usa `p-retry` (2 retries, exp 200→2000ms). Retenta em
`ECONNRESET`, `ECONNREFUSED`, `ETIMEDOUT`, `57P01`, `08006`, `08001` e mensagens
"connection terminated/refused". `AbortError` em todos os outros erros — constraint violations
(23xxx), auth, e erros de negócio não são retentados.

Todos os métodos de `repositories/*.js` encapsulam `pool.query` em `withDbRetry`.

### Desvio: async-retry → p-retry

O plano original especificava `async-retry` para startup. `p-retry` já estava no `package.json`
(adicionado na sessão B6 anterior) e oferece a mesma API com `AbortError` integrado. Sem nova dep.

### Contrato de resiliência — outcomes validados

| # | Outcome | Teste | Status |
|---|---------|-------|--------|
| 1 | Transient LLM error retried transparently | `test_llm_transient_error_is_retried_transparently` | ✅ |
| 2 | 3 LLM failures → breaker opens → pt-BR msg | `test_llm_breaker_opens_after_3_failures_returns_ptbr_message` | ✅ |
| 3 | DB cold-start retry → request succeeds | `resilience.test.js: retries a transient ECONNRESET` | ✅ |
| 4 | 409 not retried | `test_api_client_does_not_retry_409` + `resilience.test.js: 409` | ✅ |
| 5 | Email retry → exactly one email | `test_email_sender_no_duplicate_on_smtp_retry` | ✅ |
| 6 | 66 pytest + 41 Jest green | CI gate | ✅ |
