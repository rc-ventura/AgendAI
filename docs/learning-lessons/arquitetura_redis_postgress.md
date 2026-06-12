# Learning Lesson — Arquitetura Redis × Postgres em LangGraph de Produção

**Origem:** pesquisa de arquitetura (infra/performance)  
**Data:** 2026-06-12  
**Relevância futura:** qualquer batch que lide com escalabilidade, latência de streaming ou persistência do LangGraph Server

---

## L1 — Checkpointing síncrono no Postgres é o principal gargalo de latência

**O que**: o LangGraph Server persiste o estado do agente no Postgres a cada nó do grafo
(checkpoint). Essa escrita ocorre **no caminho crítico** — o agente só avança para o próximo
nó após a confirmação do banco.

**Impacto medido**:

| Backend | Latência p50 | Latência p95 |
|---------|-------------|-------------|
| Redis (estado quente) | < 1 ms | < 2 ms |
| Postgres (padrão) | ~4 ms | ~15 ms (sob carga) |

Picos de p95 > 500ms no Postgres causam "lentidões misteriosas" no streaming — invisíveis nas
métricas do LLM, mas visíveis pelo usuário como delay no SSE.

**Regra**: ao investigar lentidão em streaming, checar `agent.checkpoint.write_latency_ms`
antes de olhar para o LLM. O I/O no Postgres costuma superar em muito o tempo de inferência.

---

## L2 — Três modos de checkpoint do LangGraph (trade-off durabilidade × velocidade)

```
sync  → persiste antes de avançar para o próximo nó (máxima durabilidade, bloqueia o fluxo)
async → persiste em background enquanto o próximo nó executa (equilibrado)
exit  → persiste só no fim da execução ou em erros (melhor performance, sem retomada intermediária)
```

**Quando usar cada um**:

| Modo | Quando usar |
|------|-------------|
| `sync` | Precisar de consistência plena após cada nó (HITL, transações críticas) |
| `async` | Padrão para agentes interativos — SSE fluido sem travar |
| `exit` | Sessões curtas sem necessidade de retomada parcial (ex.: agendamento em 1 turno) |

**Para AgendAI**: o modo `async` é adequado — sessões de agendamento são curtas e, se falharem
no meio, o usuário recomeça. Nenhum checkpoint intermediário é crítico.

---

## L3 — Padrão híbrido recomendado: Redis para estado quente, Postgres para histórico durável

**Arquitetura write-through assíncrono** (padrão da indústria):

```
agente executa → escreve estado no Redis (< 1ms, caminho crítico)
                               ↓ (em background, fora do SSE path)
                worker consolida turnos completos → Postgres + embeddings
```

**Benefício**: o streaming ao usuário depende apenas do Redis (rápido). O Postgres recebe
dados em lote fora do caminho crítico — lentidão do banco não afeta o usuário.

**`langgraph-checkpoint-redis`** oferece `RedisSaver` / `AsyncRedisSaver` que substituem o
`PostgresSaver` para persistência de curto prazo. Versões "shallow" guardam apenas o
checkpoint mais recente (sem histórico acumulativo), reduzindo I/O ainda mais.

**Relação com AgendAI**: a stack atual já usa Redis para SSE streaming (LangGraph Server
built-in). Para sessões longas ou alta escala, migrar o checkpointer para `AsyncRedisSaver`
+ worker de consolidação no Postgres seria o próximo passo de infra.

---

## L4 — DeltaChannel e escrita seletiva reduzem I/O sem perder informação

**DeltaChannel**: em vez de gravar todo o histórico a cada passo, salva apenas as mudanças
incrementais nos canais acumulativos (ex.: `messages`). Reduz tamanho e frequência das
escritas — especialmente relevante quando `messages` cresce com transcrições de áudio.

**Escrita seletiva (on-demand persistence)**:
- Manter todo o chat-flux no Redis
- Escrever no Postgres apenas quando algo estruturalmente importante acontece:
  - Preferência do usuário detectada ("prefere manhãs")
  - Agendamento confirmado ou cancelado
  - Evento final decisivo

```python
# Exemplo conceitual — nó de persistência seletiva
async def persist_if_important(state: AgendAIState) -> dict:
    if state.get("email_pending"):  # agendamento confirmado — vale persistir
        await store.put("appointments", state["session_id"], state["email_payload"])
    return {}  # sem modificação de estado
```

**Evitar**: gravar mensagens triviais ou intermediárias no Postgres. Isso gera sobrecarga
WAL desnecessária para dados que não precisam sobreviver a falhas.

---

## L5 — Recomendações práticas para AgendAI em escala

| Ação | Quando | Impacto |
|------|--------|---------|
| Migrar para modo `async` no LangGraph Server | Já (configuração simples) | Streaming mais fluido |
| Monitorar `checkpoint.write_latency_ms` | Junto com B9 (ADR-031) | Visibilidade do gargalo real |
| Adicionar `AsyncRedisSaver` como checkpointer | Escala > 50 sessões simultâneas | p95 latência cai de ~15ms → < 2ms |
| Worker de consolidação Redis → Postgres | Junto com RedisSaver | Histórico durável sem bloquear |
| PgBouncer para connection pool | Alta concorrência | Evita saturação de conexões do Postgres |

**Quando NÃO vale a complexidade**: para < 10 agentes simultâneos com sessões curtas (caso
atual do AgendAI), o Postgres padrão é suficiente. O padrão híbrido compensa a partir de
escala real medida em produção.

---

**Fontes:**
- SitePoint — benchmarks de latência Redis × Postgres em LangGraph
- Redis Labs — padrão write-through assíncrono para agentes
- [LangChain Docs — langgraph-checkpoint-redis](https://langchain-ai.github.io/langgraph/reference/checkpoints/#langgraph.checkpoint.redis)
- LangChain Docs — modos de checkpoint (sync / async / exit) e DeltaChannel
