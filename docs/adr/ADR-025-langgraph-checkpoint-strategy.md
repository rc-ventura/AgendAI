# ADR-025: Estratégia de Checkpoint do LangGraph em Produção

**Status**: Implementado (B3 — 2026-06-10 · B4 — 2026-06-11)  
**Data**: 2026-06-06  
**Spec relacionada**: [005-agent-hardening](../../specs/005-agent-hardening/)  
**Depende de**: [ADR-014](./ADR-014-checkpointer-inmem.md) (supersedido em produção), [ADR-013](./ADR-013-langgraph-dev-server.md)

---

## Contexto

Em produção (spec 004), o LangGraph Server gerenciado (`langgraph/langgraph-server`) injeta automaticamente um checkpointer Postgres usando `DATABASE_URI` (Neon free tier). Cada nó do grafo escreve o estado completo no Postgres antes de o próximo nó começar — comportamento síncrono e bloqueante.

Observação em produção com Neon free tier:

```
8 nós por conversa × 50–200ms por checkpoint = 400ms–1.6s adicionados por conversa
```

Esse overhead é perceptível ao usuário como micro-pausas no stream de resposta — o "engasgo" entre fases da conversa (ex: entre o LLM terminar de gerar e a resposta final aparecer).

A pesquisa foi motivada pela pergunta: **Redis poderia atuar como broker entre os nós para eliminar esse bloqueio?**

---

## Os três padrões identificados na pesquisa

### Padrão A — Redis como substituto do Postgres (`langgraph-redis`)

```
Node executa → ESCREVE estado no Redis (<1ms) → próximo Node começa
               (Redis substitui Postgres completamente)
```

- **Biblioteca**: `langgraph-redis` (redis-developer/langgraph-redis, 223 stars, v0.4.1)
- **Ganho**: checkpoint <1ms vs 50–200ms do Neon free → economiza ~1.2s por conversa
- **Risco**: Redis é volátil — restart do Redis apaga histórico de conversas. Dados de agendamento (API Postgres) sobrevivem; só o histórico do chat é perdido.
- **Restrição**: **exige sair do managed LangGraph Server** — a imagem gerenciada hardcoda Postgres como checkpointer via `DATABASE_URI`. Seria necessário implementar servidor próprio com FastAPI.

### Padrão B — Redis como job queue para runs (Aegra)

```
Browser → Redis queue (recebe o run como tarefa) → Worker executa o grafo
                                                         ↓
                                          checkpoints ainda vão pro Postgres
```

- **Projeto**: Aegra (ibbybuilds/aegra, 961 stars, Apache 2.0) — alternativa open-source ao LangGraph Platform
- **Ganho**: melhor gerenciamento de concorrência (30 runs simultâneos, crash recovery)
- **Risco**: Redis entre nós individuais — os checkpoints dentro da execução do grafo continuam indo ao Postgres. **Não resolve a latência de checkpoint entre nós.**
- **Melhor para**: escalar para muitos usuários simultâneos, não para reduzir latência por conversa.

### Padrão C — Redis como broker entre nós (proposta original, sem implementação de referência)

```
Node 1 executa
    ↓
publica estado no Redis (<1ms) → Node 2 começa imediatamente
                    ↓
              background: Postgres persiste de forma assíncrona
                          (não bloqueia Node 2)
```

- **Padrão arquitetural**: write-behind cache aplicado ao grafo de nós
- **Ganho**: elimina completamente o bloqueio de checkpoint — nós encadeiam em sub-milissegundo
- **Risco**: se Redis cair antes do sync com Postgres, o estado "em voo" é perdido (conversa corrompida). Mitigável com Redis persistence (AOF/RDB) + ack.
- **Status**: **não existe implementação de referência pública para LangGraph**. Seria checkpointer customizado implementado do zero.
- **Restrição**: também exige sair do managed server.

---

## Padrão D — Redis como cache de saída de nós (oficial LangGraph, PR #5834)

**Descoberta nos fóruns do LangGraph (GitHub PR #5834, merged agosto 2025):**

O próprio time da LangChain implementou e mergeou Redis entre nós — mas não como broker de estado, e sim como **cache de output**:

```
Node buscar_horarios executa pela 1ª vez
    → resultado salvo no Redis (TTL configurável)

Usuário pergunta novamente sobre horários na mesma sessão
    → Node NÃO executa → Redis retorna resultado cacheado diretamente
```

- **Classe**: `RedisCache` (mesma interface de `InMemoryCache` e `SqliteCache`)
- **Disponibilidade**: LangGraph 1.0+ (já disponível no nosso setup)
- **Restrição crítica**: funciona na **compilação do grafo** (`graph.compile(cache=RedisCache(...))`), não no managed server que injeta o grafo — requer verificar se o LangGraph Server expõe essa configuração
- **Limitação com interrupt**: Redis checkpointer (não o cache) tem bug confirmado com padrões `interrupt()` (HITL) — issue #6393 fechado como "not maintained by langchain"
- **Ganho para AgendAI**: tool calls repetidas na mesma sessão (buscar horários, buscar agendamentos) não re-executam — economia de 0.5–2s por chamada duplicada

---

## Frequência de checkpoint: padrão de produção

**Pergunta central**: é padrão em produção escrever no Postgres após cada nó da conversa, ou existe uma forma otimizada?

### Evidências quantitativas (GitHub issue #806 — AWS AgentCore)

> ⚠️ **Nota**: esses números vêm da implementação do AWS Bedrock AgentCore (`langgraph-checkpoint-aws`), não do LangGraph Server padrão com Postgres. O overhead em Postgres é diferente (50–200ms/checkpoint vs API HTTP do AgentCore), mas o **padrão de frequência** (62 writes por 6 nós) é idêntico ao comportamento padrão do LangGraph em qualquer backend.

Para um workflow de **6 nós** com tool calling, a comparação direta:

| Modo | Writes ao backend | Overhead medido (AgentCore) |
|---|---|---|
| **Checkpoint por nó** (padrão atual) | 62 writes | ~8.7s |
| **Checkpoint apenas no final** | 2 writes | ~300ms |

PR #970 (fechado como resolvido) implementou `checkpoint_mode="end_of_workflow"` para o AgentCore. O LangGraph padrão expõe modos equivalentes documentados abaixo.

### Pesquisa acadêmica: 75% dos checkpoints são desperdício

O estudo *Crab* (2026) sobre agentes conversacionais mediu que:

> **"over 75% of agent turns produce no recovery-relevant state, so blanket checkpointing is mostly waste"**

O estudo propõe *semantics-aware checkpointing* que checkpointa apenas quando o estado muda de forma relevante para recovery — **reduz tráfego em até 87%**.

### Os três modos de durabilidade documentados

Documentação e comunidade LangGraph descrevem explicitamente três modos:

| Modo | Quando checkpointa | Performance | Recovery |
|---|---|---|---|
| `'sync'` (padrão) | Antes de cada nó (bloqueante) | Overhead máximo | Total — recover mid-workflow |
| `'async'` | Entre nós (não bloqueante) | Risco pequeno de perda | Quase total |
| `'exit'` | Apenas ao completar | **Performance máxima** | Nenhum mid-workflow |

### Quando o modo `'exit'` é suficiente

Para um **chat conversacional** (como AgendAI), o caso de uso é:
- Usuário envia mensagem → workflow executa → resposta aparece na tela
- Se o workflow falhar no meio, o usuário simplesmente retenta a mensagem
- Não há "side effects irrecuperáveis" que exijam recovery de estado mid-workflow (API calls são idempotentes — buscar horários não tem efeitos colaterais)

O único nó que tem side effect real é `email_sender.py` — e ele já tem retry com `tenacity` (3x backoff).

**Conclusão**: para AgendAI, `checkpoint_mode='exit'` é arquiteturalmente correto. O risco de perder estado mid-workflow é mitigado pelo retry no único nó com side effect.

### Restrição atual

O managed LangGraph Server (`langgraph/langgraph-server`) **não expõe** `checkpoint_mode` como configuração externa. O modo é definido na compilação do grafo em `graph.py`. Verificar se `graph.compile(checkpointer=checkpointer, checkpoint_mode="exit")` é aceito pelo managed server — ou se é ignorado (o server recompila internamente).

## O que a comunidade usa em produção

Pesquisa em fóruns, GitHub e blogs técnicos (junho 2026):

> *"FastAPI seems easier but you lose tons of stuff — you'd need to rebuild state management, conversation threading, checkpointing, streaming responses, and error handling from scratch."* — comunidade Latenode

O consenso é manter o managed LangGraph Server para projetos em estágio MVP/early production. A latência de checkpoint é resolvida com **melhor infraestrutura Postgres**, não com mudança de arquitetura:

- **Connection pooling** com `ConnectionPool(max_size=10)` — padrão documentado pela LangChain
- **Postgres pago** (Neon paid, Aerospike) com P99 garantido <20ms
- **Neon paid ($19/mês)**: 8 checkpoints × 20ms = 160ms total vs ~1.2s atual

O padrão de Redis como broker entre nós é **arquiteturalmente válido mas não validado em produção para LangGraph** por nenhum projeto público de referência.

---

## Decisão atual

Manter o managed LangGraph Server com Postgres (Neon). A ação imediata recomendada é **upgrade do Neon para o plano pago** — zero mudança de código, ganho de ~1s por conversa.

A migração para Redis como checkpointer (Padrão A) ou broker (Padrão C) é uma decisão futura condicionada a:

1. Latência de checkpoint se tornar o gargalo dominante após outras otimizações (parallel tool calls, redução de rounds de LLM)
2. Necessidade de escala horizontal com múltiplos workers (Padrão B via Aegra)
3. Aceitação explícita do trade-off de volatilidade do histórico de conversas

---

## Análise de impacto por opção

| Opção | Ganho de latência | Complexidade | Custo | Recomendação |
|---|---|---|---|---|
| **Parallel tool calls** (`llm_core.py`) | ~1–3s/conversa | Baixa — 2 linhas | Zero | ✅ Agora |
| **Reduzir rounds LLM** (prompt engineering) | ~5–7s/conversa | Média — iterar prompt | Zero | ✅ Próximo |
| **checkpoint_mode='exit'** | ~8.4s/conversa (62→2 writes) | Baixa — verificar suporte no managed server | Zero | 🔍 Investigar |
| **Neon paid** | ~1s/conversa | Zero — sem mudança de código | $19/mês | ✅ Se mantiver per-nó |
| **Padrão A** (Redis checkpointer) | ~1.2s/conversa | Alta — sair do managed server | Redis infra | 🔜 Spec 005+ |
| **Padrão C** (Redis broker) | ~1.2s/conversa + mais consistente | Muito alta — implementação do zero | Redis infra | 🔜 Futuro |
| **Padrão B** (Aegra) | Nenhum por conversa | Alta — migrar runtime | Infra própria | 🔜 Se escalar |
| **Padrão D** (Redis node cache) | 0.5–2s em calls duplicadas | Baixa — compilação do grafo | Redis já existe | 🔍 Investigar |

O maior ganho de latência acessível **sem mudança de infraestrutura** é reduzir os rounds de LLM via prompt engineering e parallel tool calls — combinados economizam 5–10s por conversa, mais que qualquer otimização de checkpoint.

---

## Consequências

### Aceitas agora
- Neon free tier continua adicionando ~1s por conversa em checkpoints até upgrade.
- Managed LangGraph Server limita controle sobre a estratégia de checkpoint.
- Análise documentada como base para decisões da spec 005.

### Condições que ativam revisão desta decisão
1. Upgrade do Neon e otimizações de LLM rounds implementadas — checkpoint volta a ser gargalo dominante.
2. Projeto escalando para múltiplos usuários simultâneos — Padrão B (Aegra) se torna relevante.
3. Requisito de latência < 10s por conversa com persistência — Padrão A ou C necessários.

---

## Implementação B3 — `durability: "exit"` via BFF Next.js (2026-06-10)

**Status do ADR**: Accepted (B3 implementado)

### Conclusão da sonda (T005/R2)

O managed LangGraph Server expõe `durability` como **parâmetro por-run na API**, não como config de compile-time. A referência no código do servidor é `langgraph_api/models/run.py:125 RunCreateDict.durability`. Modos:

- `"async"` (default): checkpoint assíncrono após cada nó
- `"sync"`: checkpoint síncrono antes do próximo nó
- `"exit"`: checkpoint **somente ao final do run** (turn boundary)

### Princípio arquitetural aplicado

> "A durabilidade deve ser configurada na chamada de execução do grafo (back-end), não na interface do cliente (UI). O cliente apenas dispara eventos — não controla a estratégia de persistência."

### Mudança aplicada — BFF Route Handler (Node.js, server-side)

```typescript
// agent-ui-pro/src/app/api/[..._path]/route.ts
// Proxy BFF usando o padrão oficial langgraph-nextjs-api-passthrough.
// durability: "exit" injetado aqui — em Node.js — para todos os runs.
initApiPassthrough({
  apiUrl: process.env.LANGGRAPH_API_URL,        // server-side, nunca NEXT_PUBLIC_
  headers: () => ({ "X-Api-Key": process.env.LANGGRAPH_AUTH_TOKEN }),
  bodyParameters: (req, body) => {
    if (req.method === "POST" && req.url.includes("/runs")) {
      return { ...body, durability: "exit" };   // ← QW-3 B3
    }
    return body;
  },
  baseRoute: "api",
  runtime: "nodejs",
});
```

O browser chama `/api/threads/:id/runs/stream` (relativo ao origin nginx). O Route Handler:
1. Recebe o request
2. Injeta `durability: "exit"` no body
3. Encaminha para `http://langgraph-server:8123` com `X-Api-Key` server-side
4. Proxy SSE stream de volta ao browser

`LANGGRAPH_AUTH_TOKEN` nunca é exposto no browser (não tem prefixo `NEXT_PUBLIC_`).

### Impacto esperado

Com 6 nós no grafo atual (`detect_input → transcribe? → chat_with_llm ↔ execute_tools → process_tool_results → send_email → synthesize_tts?`), o modo default `"async"` produz ~6 writes/turno. Com `"exit"`, reduz para **1 write/turno** — redução teórica de ~83% (dentro do target SC-006: ≥80%).

Ressalva: se o processo do servidor morrer mid-run com `durability="exit"`, o estado parcial não é recuperável. Para o AgendAI (idempotente — agendamentos via API REST), isso é aceitável: o usuário resubmete a mensagem.

### Verificação

- `test_bff_route_handler_sets_durability_exit` em `agent/tests/test_graph.py` (T015) — 65 pytest verdes
- Contagem de writes/turno TBD (requer sistema em execução)

---

## B4 — Redis cache para API (2026-06-11)

### Decisão revisada

O plano original de B4 era usar `graph.compile(cache=RedisCache(...))` com `CachePolicy` per-node
para cachear `buscar_pagamentos` (write-stable) no LangGraph. Após análise, a decisão foi **pivotar
para migrar o cache da API** de `node-cache` (in-memory) para **Redis compartilhado**.

### Motivação

| Problema | node-cache (antes) | Redis (depois) |
|--|--|--|
| Multi-réplica (cloud) | Cada container tem seu próprio cache | Cache compartilhado entre todas as réplicas |
| Constitution III (stateless) | Estado no container — violação | Estado externo — conforme |
| Observabilidade | Invisível — não aparece em nenhuma ferramenta | Visível via `redis-cli KEYS` |
| Invalidação | Correta mas isolada por container | Correta e global |

### Implementação

- `api/src/cache/index.js` — reescrito com `ioredis` v5; operações async com graceful fallback
  quando `REDIS_URI` ausente (tests rodam sem Redis; cache é no-op)
- `api/src/services/horariosService.js` — `await cache.get/set`
- `api/src/services/agendamentosService.js` — `await cache.delByPrefix` (2 call sites)
- `docker-compose.yml` — `REDIS_URI=redis://redis:6379` na API service + `depends_on: redis`
- `agent/pyproject.toml` — `redis[asyncio]>=5.0` adicionado
- `agent/agent/graph.py` — `compile(cache=_build_cache())` como infraestrutura;
  `_build_cache()` retorna `RedisCache(redis_client)` se `REDIS_URI` presente, `None` caso contrário

### Scoping de cache (Constitution IV — nunca servir stale)

`delByPrefix('horarios')` é chamado após `criarAgendamento` e `cancelarAgendamento` — pós-commit,
antes do return. Disponibilidade nunca é servida stale.

### LangGraph node cache — por que não aplicar CachePolicy

`execute_tools` executa TODOS os tools (estáveis e dinâmicos) num único nó. `CachePolicy` cachearia
o nó inteiro — incluindo `buscar_horarios` (dinâmico). Alternativas:
1. Split do nó (`execute_stable_tools` / `execute_tools`) — adiciona complexidade sem ganho real
   (buscar_pagamentos raramente chamado 2× na mesma sessão)
2. `key_func` que retorna chave única para chamadas dinâmicas — desperdiça Redis com entries nunca acessados

Decisão: `compile(cache=RedisCache(...))` wira a infraestrutura; nenhum nó usa `CachePolicy` neste
batch. Futura adição de nó dedicado (buscar_medicos, dados estáticos) pode usar CachePolicy trivialmente.

### Validação

- `redis-cli KEYS "agendai:cache:*"` → `agendai:cache:horarios` após primeira request ✅
- `delByPrefix` via SCAN confirmado: prefixo `horarios:` e `horarios` removidos ✅
- 41 Jest + 66 pytest verdes ✅
- `_build_cache()` retorna `None` sem `REDIS_URI` (graceful) ✅

---

## Referências

- [ADR-014](./ADR-014-checkpointer-inmem.md) — checkpointer in-memory para MVP (supersedido em produção)
- [ADR-013](./ADR-013-langgraph-dev-server.md) — decisão do servidor LangGraph
- [langgraph-redis — redis-developer/langgraph-redis](https://github.com/redis-developer/langgraph-redis)
- [Aegra — ibbybuilds/aegra](https://github.com/ibbybuilds/aegra)
- [LangGraph in Production: Latency, Replay, and Scale — Aerospike](https://aerospike.com/blog/langgraph-production-latency-replay-scale/)
- [Understanding LangGraph Server Deployment Costs — Latenode Community](https://community.latenode.com/t/understanding-langgraph-server-deployment-costs-and-self-hosting-options/33992)
- [Mastering LangGraph Checkpointing: Best Practices 2025 — Sparkco](https://sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025)
- [AgentCoreMemorySaver checkpoint_mode — langchain-aws issue #806](https://github.com/langchain-ai/langchain-aws/issues/806) — benchmark AWS-specific: 62→2 writes para 6 nós (8.7s→300ms); padrão de frequência idêntico ao LangGraph padrão
- [Durable Execution: Agents That Survive Failure — vadim.blog](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off) — modos 'sync'/'async'/'exit' documentados; cita estudo Crab 2026 (75% dos checkpoints sem valor de recovery, redução 87% com checkpointing semântico)
