# Learning Lesson: Arquitetura Redis + Postgres no LangGraph

**Data**: 2026-06-06  
**Contexto**: Investigação de performance em produção (Spec 004 → Spec 005)  
**Motivação**: Latência perceptível ("engasgo") no stream identificada em produção no Render.

---

## O problema original

Em produção, cada conversa adicionava overhead invisível ao usuário:

```
8 nós × 50–200ms por checkpoint no Neon free tier = 400ms–1.6s por conversa
```

A pergunta inicial: **Redis poderia ser um broker entre os nós para eliminar esse bloqueio?**

---

## Aprendizado 1 — O managed server não expõe o checkpointer

O `langgraph/langgraph-server` injeta Postgres automaticamente via `DATABASE_URI`.
Não há como trocar o checkpointer sem sair da imagem gerenciada — o que significa reescrever
o servidor com FastAPI (perdendo streaming SSE, thread management, SDK compatibility).

> **Conclusão**: qualquer otimização de checkpoint no managed server é limitada ao que a imagem
> expõe. Mudar o backend de persistência é uma decisão de migração de plataforma.

---

## Aprendizado 2 — Redis tem quatro papéis distintos no LangGraph

Quando Redis é mencionado com LangGraph em produção, pode significar coisas muito diferentes:

#### Padrão A — Redis substitui o Postgres (`langgraph-redis`)
```
Node → Redis (<1ms) → próximo Node   ← Redis É o checkpointer
```
- Lib: `langgraph-redis` (redis-developer, 223 stars)
- Ganho: ~1.2s por conversa vs Neon free
- Risco: Redis volátil — restart apaga histórico de conversas
- **Exige sair do managed server**

#### Padrão B — Redis como job queue entre runs (Aegra)
```
Browser → Redis queue → Worker executa o grafo → checkpoints ainda vão pro Postgres
```
- Resolve concorrência entre usuários, não latência por conversa
- Projeto Aegra: 961 stars, Apache 2.0

#### Padrão C — Redis como broker entre nós (proposta original do projeto)
```
Node 1 → Redis (<1ms) → Node 2 começa imediatamente
              ↓ background: Postgres persiste async
```
- Padrão arquitetural válido (write-behind cache)
- **Não existe implementação de referência para LangGraph**
- Também exige sair do managed server

#### Padrão D — Redis como cache de output de nós (oficial LangChain, PR #5834)
```
Node buscar_horarios executa → resultado salvo no Redis (TTL)
Próxima chamada igual → Redis retorna sem re-executar o nó
```
- Não elimina o checkpoint Postgres — evita re-execução de nós com mesmo input
- Disponível em LangGraph 1.0+ via `graph.compile(cache=RedisCache(...))`
- O Redis já presente no AgendAI (`REDIS_URI`) pode ser reutilizado

> **Conclusão**: ao falar em "usar Redis com LangGraph", sempre esclarecer qual padrão.
> São trade-offs completamente diferentes.

---

## Aprendizado 3 — A frequência de checkpoint é o gargalo real

O problema não é **onde** o LangGraph escreve (Postgres vs Redis), mas **com que frequência**.

#### Comportamento padrão: escreve após cada nó
Para 6 nós com tool calling (benchmark langchain-aws issue #806):

| Modo | Writes | Overhead medido |
|------|--------|-----------------|
| Por nó (padrão) | ~62 writes | ~8.7s |
| End-of-workflow | 2 writes | ~300ms |

#### Os três modos de durabilidade (vadim.blog)
- `'sync'` — bloqueante antes de cada nó (padrão atual — mais seguro, mais lento)
- `'async'` — não-bloqueante entre nós (risco pequeno de perda em crash)
- `'exit'` — apenas ao final do workflow (máxima performance, sem recovery mid-workflow)

#### Por que `'exit'` é seguro para AgendAI
- Falha no meio → usuário retenta a mensagem (sem perda permanente)
- O único nó com side effect real (`email_sender`) já tem retry com `tenacity`
- As 6 tools da API são idempotentes

#### Evidência acadêmica (Crab 2026, via vadim.blog)
> "Over 75% of agent turns produce no recovery-relevant state — blanket checkpointing is mostly waste."
> Checkpointing semântico reduz tráfego em até **87%**.

> **Conclusão**: antes de trocar infra, testar `checkpoint_mode='exit'` no managed server.
> Se funcionar: 2 linhas de código, maior ganho de latência disponível sem custo.

---

## Aprendizado 4 — O maior ganho não é o checkpoint, é o número de rounds de LLM

Mesmo eliminando o checkpoint, cada round de LLM soma 800ms–2s. Com 4 rounds por conversa:

| Fonte de latência | Ganho potencial | Esforço |
|-------------------|-----------------|---------|
| Prompt engineering (4→2 rounds) | 5–7s | Médio |
| Parallel tool calls | 1–3s | Mínimo (2 linhas) |
| checkpoint_mode='exit' | potencial ~8s | Investigar |
| Groq Whisper (fluxo de áudio) | ~1.7s | Baixo |
| Neon paid | ~1s | Nenhum (só $) |

> **Conclusão**: a ordem de implementação importa. Parallel tool calls e prompt engineering
> têm maior ROI que qualquer otimização de checkpoint.

---

## Aprendizado 5 — O Redis já presente é para SSE, não para dados

`REDIS_URI` no docker-compose serve o LangGraph Server para **streaming SSE** (buffer de
mensagens entre servidor e clientes). Não armazena estado do grafo.

Esse mesmo Redis pode ser reutilizado para o Padrão D (cache de output de nós) sem
infraestrutura adicional — requer investigar se o managed server expõe a configuração
de cache na compilação do grafo.

---

## O que este research trouxe de novo vs o que já estava documentado

### Já estava na Spec 005 / ADR-025
- Padrões A, B, C, D de Redis no LangGraph (ADR-025)
- Benchmark de frequência (62→2 writes, ADR-025)
- checkpoint_mode='exit' como QW-3 (Spec 005)
- Parallel tool calls como QW-1 (Spec 005)

### Contribuições novas que ainda faltam na Spec 005

**1. Padrão D como tarefa investigativa concreta (QW pendente)**
Verificar se `graph.compile(cache=RedisCache(...))` funciona no managed server
usando o Redis já existente (`REDIS_URI`). Zero custo de infra — só investigação.

**2. Migração para fora do managed server como P10 futuro**
Se `checkpoint_mode='exit'` não for suportado e o checkpoint continuar sendo gargalo
após QW-1/4, a saída do managed server (FastAPI + PostgresSaver customizado) deve ser
documentada como decisão futura com critérios de ativação claros.

**3. Hierarquia clara de fontes de latência**
A spec 005 lista os QWs mas não deixa explícito que LLM rounds > checkpoint overhead.
Um diagrama de impacto relativo ajuda na tomada de decisão de prioridade.

---

## Referências

- [ADR-025 — Estratégia de Checkpoint LangGraph](../adr/ADR-025-langgraph-checkpoint-strategy.md)
- [GitHub langchain-aws issue #806](https://github.com/langchain-ai/langchain-aws/issues/806)
- [vadim.blog — Durable Execution](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)
- [langgraph-redis](https://github.com/redis-developer/langgraph-redis)
- [Aegra](https://github.com/ibbybuilds/aegra)
