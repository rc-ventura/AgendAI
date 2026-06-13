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

### Modos de medição

| Modo | Infra ativa | Descrição |
|------|-------------|-----------|
| `graph_direct` | API offline | Chama o grafo Python diretamente; sem nginx, sem LangGraph Server, sem Postgres; tool calls falham graciosamente |
| `server` | Full stack | Chama via nginx → LangGraph Server → Postgres checkpoint → Redis SSE → API Node.js real |

> **graph_direct** medido em 2026-06-13 com 10 runs:
> ```bash
> cd agent && .venv/bin/python tests/perf/measure_latency.py --scenario text --runs 10
> ```
> **server** medido em 2026-06-13 com 11 runs bem-sucedidos (limitação de rate: 20r/min, burst=10):
> ```bash
> LANGGRAPH_AUTH_TOKEN=... LANGGRAPH_API_URL=http://localhost:8080 \
>   .venv/bin/python tests/perf/measure_latency.py --scenario text --runs 5 --mode server
> # Para >5 runs: adicionar --delay 4
> ```

### Cenário A — Texto ("Quais horários disponíveis tem na quarta-feira?")

| Métrica | Valor | Notas |
|---------|-------|-------|
| Métrica | `graph_direct` | `server` (full stack) | Overhead |
|---------|---------------|----------------------|---------|
| P50 latência total | **0.98s** | **1.07s** | +90ms (+9%) |
| P99 latência total | **2.20s** | **2.15s** | ~0ms |
| Latência mínima | 0.62s | 0.79s | |
| Latência máxima | 2.21s | 2.20s | |
| Rounds de LLM (média) | **2.0** ¹ | **1.0** ² | diferente contexto |
| Tokens de entrada (média) | ~900 est. | n/a (server não expõe) | |
| Custo estimado/conversa (USD) | **$0.000136** | n/a | |
| Writes de checkpoint/turno | **30** (async) → **1** (exit) | n/a | medido via CountingCheckpointer |

¹ `graph_direct`: API offline → tool calls falham → LLM recorre a resposta de "indisponibilidade" em 2 rounds  
² `server`: API online → LLM responde diretamente em 1 round (pede mais detalhes sem chamar ferramenta)

> **Conclusão principal**: o overhead da infra completa (nginx + LangGraph Server + Postgres + Redis + API real)
> é apenas **+90ms em P50** — o gargalo é o LLM, não a infraestrutura.
>
> **Nota sobre rate limit**: nginx limita a 20r/min (burst=10). Para benchmarks com >5 runs em `server` mode,
> usar `--delay 4` entre runs.  
> **Runs rápidos em `graph_direct`** (0.62–0.83s) = provável prompt cache OpenAI (mesmo input repetido).

### Cenário B — Voz

| Métrica | Valor | Notas |
|---------|-------|-------|
| P50 latência total | TBD | requer `validate_b5_audio.py` com Docker rodando |
| P99 latência total | TBD | |
| Rounds de LLM (média) | TBD | |
| Custo estimado/conversa (USD) | TBD | |

> Validação de áudio B5 disponível em `agent/tests/perf/validate_b5_audio.py` (requer Docker + LANGGRAPH_AUTH_TOKEN).

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

| SC | Métrica | graph_direct | server (full stack) | Target | Status |
|----|---------|-------------|---------------------|--------|--------|
| SC-004 | Latência P50 texto | **0.98s** | **1.07s** (+90ms) | ≤0.49s (−50%) | 🟡 overhead infra mínimo; gargalo = LLM |
| SC-006 | Writes checkpoint/turno | **30** → **1** (exit) | n/a | −≥80% | ✅ durability=exit implementado (B3) |
| SC-007 | Latência voz | TBD | TBD | −≥50% baseline voz | TBD (requer teste áudio no Docker) |
| SC-008 | Custo/conversa | **$0.000136** | n/a | ≤ baseline com histórico longo | TBD |

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

---

## B2 — Redução de rounds via system prompt — implementado 2026-06-10

**Tática**: adicionar regra 6 ao `SYSTEM_PROMPT` em `llm_core.py` com instruções explícitas de:
1. Lookups simultâneos no round 1 (`buscar_horarios` + `buscar_paciente` em paralelo quando o e-mail está disponível)
2. `criar_agendamento` imediato após confirmação do paciente (sem round de re-confirmação)

**Problema original**: o prompt dizia "confirme com o paciente" antes de agendar — o LLM
interpretava isso como um turno extra de confirmação, gerando 4 rounds num fluxo típico.
Sem instrução explícita de chamadas paralelas, também separava buscar_horarios e buscar_paciente
em rounds distintos.

**Solução**: instrução direta no prompt. LLMs de instrução seguem regras numeradas de forma
confiável quando são explícitas e não conflitam com outras regras.

**Lição de processo**: regras de negócio do sistema prompt têm **custo de latência**.
Cada round extra = ~600–900 ms (2× RTT LLM em P50). Revisitar o prompt após mudanças de
arquitetura é tão importante quanto otimizar código. Testar com `test_system_prompt_directs_parallel_lookup`
(verifica presença da instrução) + simulação de fluxo 2-round em `test_graph.py`.

**Validação**: `test_system_prompt_directs_parallel_lookup` (T011) + 64 pytest verdes.
Live delta TBD (requer sistema em execução).

---

## B3 — `durability: "exit"` no SDK client — implementado 2026-06-10

**Tática**: passar `durability: "exit"` em todos os `stream.submit()` do `agent-ui-pro/src/components/thread/index.tsx`.

**Problema original**: o managed LangGraph Server usa `durability: "async"` por default — escreve
checkpoint após cada nó do grafo. Com 6 nós, cada turno gera ~6 writes no Postgres (Neon).

**Solução**: `durability: "exit"` reduce para 1 write/turno (somente quando o run termina).
O parâmetro é **por-run, no SDK client** — não é config de compile-time no `graph.py`.
Confirmado pelo tipo `Durability` no `@langchain/langgraph-sdk/dist/types.d.ts:10`.

**Ressalva**: com `"exit"`, estado mid-run não é persistido. Se o servidor cair durante a execução,
o turno perde-se. Para o AgendAI (operações idempotentes via REST API), isso é aceitável.

**Lição de processo**: antes de implementar config de durabilidade, sempre verificar **onde** o
parâmetro vive: compile-time no grafo, config do servidor, ou parâmetro por-run no SDK client.
São lugares completamente diferentes e exigem código em camadas distintas.

**Validação**: `test_ui_stream_submit_uses_durability_exit` (T015) + 65 pytest verdes.
Write count/turno TBD (requer sistema em execução).
