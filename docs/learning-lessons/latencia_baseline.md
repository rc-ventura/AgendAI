# Latência Baseline — AgendAI Agent (Spec 005 / B0)

**Data**: 2026-06-09
**Harness**: `agent/tests/perf/measure_latency.py` (T002)
**Ref**: research.md R1, tasks T004

---

## Contexto

Baseline capturado antes de qualquer otimização, para que SC-004/006/007/008 possam ser
validados como percentuais concretos. As métricas abaixo são comparadas após cada batch
(B1–B5) do ciclo de performance.

---

## Resultados

> **Estado**: aguardando medição com sistema em execução.
> Preencher após executar:
> ```
> cd agent
> uv run python tests/perf/measure_latency.py --scenario text --runs 20
> uv run python tests/perf/measure_latency.py --scenario voice --runs 20
> ```

### Cenário A — Texto ("Quais horários disponíveis na quarta-feira?")

| Métrica | Valor | Notas |
|---------|-------|-------|
| P50 latência total | TBD | |
| P99 latência total | TBD | |
| Latência mínima | TBD | |
| Latência máxima | TBD | |
| Rounds de LLM (média) | TBD | target: ≤2 após B2 |
| Tokens de entrada (média) | TBD | |
| Tokens de saída (média) | TBD | |
| Custo estimado/conversa (USD) | TBD | baseline para SC-008 |
| Writes de checkpoint por turno | TBD | baseline para SC-006 |

### Cenário B — Voz (proxy de texto — sem áudio real no harness)

| Métrica | Valor | Notas |
|---------|-------|-------|
| P50 latência total | TBD | |
| P99 latência total | TBD | |
| Rounds de LLM (média) | TBD | |
| Custo estimado/conversa (USD) | TBD | |

---

## Achados da Sonda B0 (T005 + T006)

### R2 — Durabilidade do checkpoint no servidor gerenciado (**POSITIVO**)

- `graph.compile()` **não** aceita parâmetro `durability` (não é config de compile-time)
- O servidor gerenciado expõe `durability` como **parâmetro de criação de run** na API:
  - `"sync"` / `"async"` (default) — checkpoint após cada nó
  - `"exit"` — checkpoint apenas ao final do run (turn boundary)
- **Implementação B3**: passar `durability="exit"` no SDK do agent-ui-pro ao criar runs
  - Não requer alterar `graph.py`
  - Redução esperada: ~6 writes → 1 write por turno (graph de 6 nós)

**Referência no código**: `langgraph_api/models/run.py:125` — `RunCreateDict.durability`

### R3 — Cache Redis no servidor gerenciado (**POSITIVO**)

- `from langgraph.cache.redis import RedisCache` — disponível em langgraph 1.2.0
- `graph.compile(cache=cache)` — o atributo `cache` é preservado no objeto compilado
- O servidor gerenciado **não filtra** o atributo `cache` (apenas `checkpointer` e `store` geram aviso)
- `RedisCache(redis=<async_redis_client>, prefix="langgraph:cache:")` — assinatura confirmada
- **Implementação B4**: adicionar `cache=RedisCache(...)` no `builder.compile()` em `graph.py`
  - Escopo: apenas lookups write-stable (Constitution IV — nunca servir stale)

---

## R6 — `create_agent` + middleware: verificado e funcional (**CORRETO**)

Após pesquisa nas docs oficiais e instalação do pacote correto:

- `langchain>=1.0` (PyPI: `langchain`, não `langchain-core`) foi adicionado ao projeto
- Versão instalada: **langchain 1.3.1**
- `from langchain.agents import create_agent` → OK ✅
- `from langchain.agents.middleware import PIIMiddleware, SummarizationMiddleware, ModelRetryMiddleware` → OK ✅

**Padrão**: `create_agent(model="openai:gpt-4o-mini", tools=[...], middleware=[...], cache=...)` —
sem `bind_tools` manual; retorna `CompiledStateGraph` que pode ser nó do grafo pai.

**Lição de processo consolidada**: `langchain-core` e `langchain` são PyPI packages distintos.
Sempre instalar o pacote e testar os imports antes de documentar disponibilidade.
Ver detalhes em [guardrails_langchain_middleware.md](./guardrails_langchain_middleware.md).

---

## Targets de Otimização (baseline → target)

| SC | Métrica | Baseline | Target |
|----|---------|----------|--------|
| SC-004 | Latência P50 texto | TBD | −≥50% do baseline |
| SC-006 | Writes de checkpoint/turno | TBD | −≥80% (exit mode = ~1 em vez de ~6) |
| SC-007 | Latência voz (transcrição+síntese) | TBD | −≥50% do baseline |
| SC-008 | Custo/conversa | TBD | ≤ baseline à medida que histórico cresce |

---

## B1 — Parallel tool calls (`parallel_tool_calls=True`) — implementado 2026-06-10

**Tática**: `bind_tools(ALL_TOOLS, parallel_tool_calls=True)` em `agent/agent/nodes/llm_core.py`.

**Problema original**: sem o flag, quando o modelo OpenAI decide emitir múltiplas chamadas de
ferramenta em um único turno, a ausência do flag `parallel_tool_calls` pode fazer com que o SDK
não sinalize concorrência explicitamente — e em algumas versões o `ToolNode` executava as chamadas
sequencialmente, adicionando uma round-trip extra por ferramenta.

**Solução**: o flag `parallel_tool_calls=True` é passado na API OpenAI como parâmetro top-level.
O `ToolNode` do LangGraph já executa as tool calls de um `AIMessage` em concorrência (asyncio gather);
o flag garante que o modelo as emita em um único AIMessage ao invés de em AIMessages separados.

**Ganho esperado**: turnos que chamam ≥2 ferramentas independentes (ex.: `buscar_horarios` +
`buscar_paciente` no mesmo turno) ganham concorrência — sem polling sequential adicional.

**Validação**: `test_llm_bound_with_parallel_tool_calls` (T008) + 63 pytest verdes.

**Lição de processo**: para qualquer flag de configuração de chamada LLM/tool, preferir ser
explícito no `bind_tools` (ou no objeto `ChatOpenAI` passado ao `create_agent`) ao invés de
depender do default do SDK, que pode mudar entre versões.
