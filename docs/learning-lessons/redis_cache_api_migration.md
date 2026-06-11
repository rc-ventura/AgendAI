# Redis Cache: Migração de node-cache para ioredis na API

**Contexto:** B4 (Spec 005) — cache da API migrado de `node-cache` (in-memory, per-container)
para Redis compartilhado (`ioredis`). Decisão tomada em 2026-06-11 como B4 reproposto.

**Data:** 2026-06-11

---

## Por que o node-cache é problemático em produção

`node-cache` armazena dados **na memória do processo Node.js**. Em containers:

```
Réplica 1: GET /horarios → cache MISS → DB → armazena em memória (horario X disponível)
Réplica 2: POST /agendamentos → COMMIT → delByPrefix (apaga da memória da réplica 2)
Réplica 1: GET /horarios → cache HIT → retorna horario X disponível (STALE!)
```

Na escala atual (1 réplica), isso não ocorre. Na nuvem com auto-scale, é um bug garantido.
O Redis compartilhado elimina o problema: invalidação em qualquer réplica afeta todas.

---

## Padrão de migração: operações async com graceful fallback

A mudança crítica: `node-cache` é síncrono, Redis é assíncrono. Todas as call sites precisam de `await`:

```js
// Antes (node-cache — síncrono)
const cached = cache.get(cacheKey);
cache.set(cacheKey, result);
cache.delByPrefix('horarios');

// Depois (ioredis — async)
const cached = await cache.get(cacheKey);
await cache.set(cacheKey, result);
await cache.delByPrefix('horarios');
```

**Graceful fallback** quando `REDIS_URI` ausente:

```js
let _client; // undefined = não inicializado; null = sem Redis

function _getClient() {
  if (_client !== undefined) return _client;
  const uri = process.env.REDIS_URI;
  if (!uri) { _client = null; return null; }
  const Redis = require('ioredis');
  _client = new Redis(uri, { maxRetriesPerRequest: 2 });
  _client.on('error', err => console.warn('[cache] Redis error:', err.message));
  return _client;
}

async function get(key) {
  const c = _getClient();
  if (!c) return undefined; // no-op — DB sempre consultado
  try { return JSON.parse(await c.get(PREFIX + key)) ?? undefined; }
  catch { return undefined; }
}
```

**Resultado**: em testes (sem `REDIS_URI`), cache é no-op — todos os 41 Jest passam sem Redis.

---

## delByPrefix com SCAN (não KEYS)

`KEYS pattern` bloqueia o Redis em produção com muitas chaves. Usar `SCAN`:

```js
async function delByPrefix(prefix) {
  const c = _getClient();
  if (!c) return;
  const pattern = PREFIX + prefix + '*';
  let cursor = '0';
  const keys = [];
  do {
    const [next, batch] = await c.scan(cursor, 'MATCH', pattern, 'COUNT', 100);
    cursor = next;
    keys.push(...batch);
  } while (cursor !== '0');
  if (keys.length) await c.del(...keys);
}
```

`SCAN` é iterativo e não bloqueia. `COUNT 100` é uma sugestão — Redis pode retornar mais ou menos.
O loop `cursor !== '0'` garante que todos os resultados são coletados.

---

## Prefixo de chave e separação de concerns

Com Redis compartilhado entre múltiplos consumers (API + LangGraph Server), prefixos evitam colisões:

```
agendai:cache:*        → API Node.js (disponibilidade de horários)
langgraph:cache:*      → LangGraph node cache (futuro)
langgraph:*            → LangGraph Server (checkpoints, SSE streaming)
```

---

## LangGraph node cache: por que não usamos CachePolicy

A intenção original de B4 era cachear `buscar_pagamentos` via `CachePolicy` no nó `execute_tools`.
O problema: `execute_tools` executa TODOS os tools numa única invocação — estáveis e dinâmicos.
`CachePolicy` cacheia a saída do nó inteiro baseado na entrada.

Opções avaliadas:

| Opção | Complexidade | Risco Constitutional IV |
|-------|-------------|------------------------|
| CachePolicy no execute_tools (todos os tools) | Baixa | Alto (cacheia buscar_horarios) |
| Split em execute_stable_tools + execute_tools | Média | Nenhum |
| key_func que retorna chave única para dinâmicos | Média | Baixo (mas desperdiça Redis) |
| Só infraestrutura (compile(cache=...), sem CachePolicy) | Baixa | Nenhum ← escolhido |

`compile(cache=RedisCache(...))` prepara a infraestrutura. `CachePolicy` pode ser adicionado
trivialmente em nós futuros dedicados a dados estáticos (lista de médicos, configurações).

---

## Relação com ADR-025 e próximos passos

- **ADR-025 B4** — documenta a decisão e a implementação
- **B6 API-side (T029/T030)** — próximo: `connection.js` startup retry + `repositories` p-retry
- **Futuro**: se um nó dedicado `buscar_medicos` (estático) for criado, `CachePolicy(ttl=3600)` pode ser adicionado sem risco

**Validação em Docker**: `redis-cli KEYS "agendai:cache:*"` → `agendai:cache:horarios` após primeira request.
