# Technical Design — Spec 005 — Agent Hardening (Production-Grade Resilience)

> **Note**: This is the **technical design document** for Spec 005 — the detailed gap
> analysis, code sketches, performance Quick Wins, model evaluation and prioritization that
> feed the planning phase. The business/requirements-level specification (user stories,
> functional requirements, success criteria) lives in [`spec.md`](./spec.md), written in the
> Spec-Driven Development (SDD) format. Use this file as input for `/speckit-plan`.

**Feature Branch**: `005-agent-hardening`

**Created**: 2026-06-03

**Updated**: 2026-06-09

**Status**: Draft (technical design)

**Input**: Análise de gaps agênticos mapeados no `docs/AgendAI_Architecture_Roadmap.pdf` (V2.0)
e observações de produção na Fase 1 (Render). Baseado nos whitepapers *Prototype to Production*,
*Context Engineering: Sessions & Memory* e *Agentic Design Patterns* (Google Cloud, 2025).

---

## Why This Feature Exists

O AgendAI está em produção na Fase 1 (Render + GitHub Actions). Esta spec foca nos gaps
que podem ser endereçados **sem autenticação de usuário**: resiliência a falhas, segurança
de conteúdo, observabilidade, gerenciamento de contexto e performance.

Gaps dependentes de identidade de usuário (sessão persistente, memória de longo prazo,
HITL com interrupt) foram separados em specs dedicadas:
- **Spec 006** — Autenticação + sessão persistente por usuário
- **Spec 007** — Memória de longo prazo + Human-in-the-Loop

---

## Gaps Mapeados (P1, P4, P5, P6, P8)

### P1 — Retry + Circuit Breaker

**Problema:** `llm_core.py`, `transcriber.py` e `api_client.py` não têm retry. Uma falha
transiente da OpenAI (`RateLimitError`, `APITimeoutError`) ou da API interna (cold start no
Render) encerra o run do grafo permanentemente. `tts.py` e `email_sender.py` já têm tenacity.

**Decisão técnica:** Ver [ADR-024](../../docs/adr/ADR-024-retry-resilience-strategy.md).

**Escopo:**
- `agent/agent/nodes/llm_core.py` — retry tenacity + circuit breaker pybreaker
- `agent/agent/nodes/transcriber.py` — retry tenacity
- `agent/agent/api_client.py` — retry tenacity (só `ConnectError`/`TimeoutException`, não 4xx)
- `api/src/db/connection.js` — async-retry no startup (5x, até 30s)
- `api/src/repositories/*.js` — p-retry em queries transientes

---

### P4 — Guardrails de input e output

**Problema:** Sem validação de entrada nem filtragem de saída. O agente está exposto a:
- **Input:** prompt injection, jailbreak, tópicos off-scope (não médicos), PII enviado pelo
  usuário (CPF, número de cartão) que pode ser logado ou vazado
- **Output:** resposta do LLM pode conter PII do paciente, informações médicas incorretas,
  ou conteúdo fora do escopo da clínica

**Decisão:** Dois pontos de controle no grafo — antes e depois do LLM:

```
[input] → validate_input → chat_with_llm → validate_output → [resposta ao usuário]
```

**validate_input** (novo nó LangGraph):
```python
def validate_input(state: AgendAIState) -> dict:
    text = state["input"]
    if is_injection(text):      return {"blocked": True, "reason": "prompt_injection"}
    if is_off_scope(text):      return {"blocked": True, "reason": "off_scope"}
    if contains_pii(text):      return {"blocked": True, "reason": "pii_detected"}
    return state
```

**validate_output** (novo nó LangGraph):
```python
def validate_output(state: AgendAIState) -> dict:
    response = state["messages"][-1].content
    if contains_pii(response):      redact_pii(response)
    if is_off_scope(response):      return {"response": FALLBACK_MESSAGE}
    return state
```

**Evolução por fase:**
```
Fase 1/2: nós manuais (regex + lista de padrões)
Fase 3:   AWS Bedrock Guardrails via ApplyGuardrail API
          → funciona com GPT-4o-mini sem trocar de LLM
          → configuração no console AWS: checkboxes, sem código
```

**Tipos de verificação:**

| Verificação | Input | Output | Fase 1/2 | Fase 3 |
|-------------|-------|--------|----------|--------|
| Prompt injection | ✅ | — | regex patterns | Bedrock |
| Off-scope (não médico) | ✅ | ✅ | lista de tópicos | Bedrock |
| PII detection | ✅ | ✅ | regex CPF/email/tel | Bedrock |
| Conteúdo tóxico | — | ✅ | lista de palavras | Bedrock |
| Informação médica incorreta | — | ✅ | — | Bedrock |

---

### P5 — Logs estruturados + correlation IDs

**Problema:** Sem `request_id` propagado entre nginx → API → agente → LangSmith. Impossível
correlacionar um erro do usuário com o trace correto no LangSmith.

**Decisão:** Middleware Express gerando `request_id` (UUID) por request, propagado nos headers
(`X-Request-ID`) e nos logs de cada serviço. No agente Python: `structlog` com output JSON.
Liga `request_id` ao `trace_id` do LangSmith via metadata.

```
nginx (X-Request-ID gerado) → API (loga com request_id) → agente (structlog JSON)
                                                                   ↓
                                                            LangSmith trace_id
```

---

### P6 — Context Manager

**Problema:** O agente acumula todas as mensagens da conversa na janela de contexto sem nenhum
gerenciamento. Em conversas longas, o contexto cresce indefinidamente, aumentando latência e
custo por token, e podendo exceder o limite de contexto do GPT-4o-mini (128k tokens).

**O que é context management:**
Decidir **o que entra na janela de contexto** enviada ao LLM a cada turno — não apenas
concatenar todas as mensagens anteriores.

**Estratégias:**

| Estratégia | Quando usar | Como |
|-----------|-------------|------|
| **Sliding window** | Conversas longas | Mantém últimas N mensagens |
| **Summarization** | Histórico volumoso | Resume mensagens antigas em um bloco |
| **Selective retrieval** | Memória longa (P7) | Busca mensagens relevantes via embedding |
| **Token budget** | Controle de custo | Trunca contexto ao atingir X tokens |

**Decisão para Fase 1/2:** Sliding window com summarization — mantém as últimas 10 trocas
completas e comprime o restante em um resumo injetado no system prompt.

```python
# agent/agent/context_manager.py
MAX_TURNS = 10
SUMMARY_PROMPT = "Resuma em 3 frases o histórico da conversa anterior:"

def trim_context(messages: list, llm) -> list:
    if len(messages) <= MAX_TURNS * 2:
        return messages
    old = messages[:-MAX_TURNS * 2]
    recent = messages[-MAX_TURNS * 2:]
    summary = llm.invoke([SystemMessage(SUMMARY_PROMPT)] + old)
    return [SystemMessage(f"[Resumo anterior]: {summary.content}")] + recent
```

**Evolução por fase:**
```
Fase 1/2: sliding window + summarization manual
Fase 3:   Vertex AI Memory Bank → extração semântica automática via Gemini
          → contexto enriquecido com fatos relevantes do paciente
```

---

### P8 — Modernização do Core Agêntico: `create_agent` + Middleware (LangChain v1 + LangGraph v1)

> **Correção em relação ao rascunho anterior:** `create_react_agent` foi **depreciado** no
> LangGraph v1.0 em favor de `create_agent` da `langchain.agents`. Os primitivos do grafo
> (`StateGraph`, nós, arestas) são **inalterados** — não há breaking change no grafo em si.
> O que muda é a camada de orquestração acima do grafo: o sistema de **middleware**.
>
> **Correção (2026-06-09)**: uma versão anterior desta nota afirmava que `create_agent` "foi
> removido em `langchain v1.1.0` sem aviso". **Isso é FALSO** — verificação na fonte primária
> mostra que `create_agent` é o método oficial e recomendado do LangChain v1, e a v1.1 o expande.
> O relato de "removido" foi um erro de ambiente (pacotes stale) num post de fórum, depois
> desmentido pela comunidade. Os primitivos do LangGraph permanecem estáveis.
>
> **Decisão registrada em [ADR-026](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md)**:
> adotar `create_agent` + middleware como caminho padrão para P1/P4/P6 (`PIIMiddleware`,
> `SummarizationMiddleware`, `ModelRetryMiddleware`) — é o caminho oficial estável. `MessagesState`
> é aditivo e compatível. Injection/off-scope exigem middleware custom ou NeMo (não são built-in).

**Problema:** O grafo atual (`graph.py`) implementa manualmente lógica que o novo sistema de
middleware do LangChain v1 provê como prebuilt: retry de LLM, summarização de contexto,
detecção de PII, e human-in-the-loop. Além disso, `MessagesState` como base do estado elimina
boilerplate no `AgendAIState`.

**Documentação oficial:**
- [LangGraph v1.0 release](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- [LangChain v1.0 release](https://docs.langchain.com/oss/python/releases/langchain-v1)
- [Middleware overview](https://docs.langchain.com/oss/python/langchain/middleware/overview)

---

#### 1. `MessagesState` como base do estado (LangGraph v1 — estável)

Os primitivos do LangGraph v1 são inalterados. A única mudança de estado recomendada é
usar `MessagesState` como classe base em vez de `TypedDict` manual:

```python
# Antes — TypedDict com add_messages manual:
from typing import Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgendAIState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input_type: Literal["text", "audio"]
    ...

# Depois — MessagesState já inclui messages com add_messages:
from langgraph.graph import MessagesState

class AgendAIState(MessagesState):
    input_type: Literal["text", "audio"]
    audio_data: bytes | None
    session_id: str
    email_pending: bool
    email_payload: dict | None
    final_response: str | bytes | None
```

O grafo (`StateGraph`, nós, arestas, roteamento condicional) permanece **idêntico**.

---

#### 2. `create_agent` + Middleware (LangChain v1 — substitui `create_react_agent`)

`create_react_agent` (de `langgraph.prebuilt`) foi depreciado. O substituto é `create_agent`
de `langchain.agents`, que executa sobre o LangGraph e expõe um sistema de middleware com
hooks em cada etapa do loop agêntico:

```
before_agent → before_model → wrap_model_call → [LLM] → after_model
                                                              ↓
                                               wrap_tool_call → [Tools] → after_agent
```

**Hooks disponíveis:**

| Hook | Quando executa | Casos de uso |
|------|---------------|-------------|
| `before_agent` | Uma vez, no início | Carregar memória, validar input |
| `before_model` | Antes de cada chamada ao LLM | Trim de histórico, PII input |
| `wrap_model_call` | Envolve a chamada ao LLM | Retry, cache, troca de modelo |
| `after_model` | Após LLM, antes de tools | Human-in-the-loop, PII output |
| `wrap_tool_call` | Envolve cada tool call | Injetar contexto, interceptar resultado |
| `after_agent` | Uma vez, ao final | Salvar memória, notificações, cleanup |

**Prebuilt middleware relevantes para o AgendAI:**

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    PIIMiddleware,             # P4: detecção e redação de PII input + output
    SummarizationMiddleware,   # P6: resume histórico quando excede token threshold
    HumanInTheLoopMiddleware,  # P9: pausa antes de tools irreversíveis
    ModelRetryMiddleware,      # P1 (complementa tenacity no llm_core)
)

agent = create_agent(
    model=llm,
    tools=ALL_TOOLS,
    middleware=[
        PIIMiddleware(),
        SummarizationMiddleware(token_threshold=8000),
        HumanInTheLoopMiddleware(interrupt_on={"criar_agendamento": True,
                                               "cancelar_agendamento": True}),
        ModelRetryMiddleware(retries=3),
    ],
)
```

**Impacto no grafo:** `create_agent` retorna um grafo LangGraph compilado. Pode ser usado
como nó/subgrafo dentro do grafo externo que mantém o pipeline de áudio:

```
START → detect_input_type
          ├─ (texto) → [agent: create_agent + middleware] → send_email? → END
          └─ (audio) → transcribe_audio → [agent] → synthesize_tts → END
```

---

#### 3. O que NÃO muda

- `StateGraph`, nós, arestas, roteamento condicional — **inalterados** (LangGraph v1 estável)
- Nós de áudio (`transcribe_audio`, `synthesize_tts`) — fora do `create_agent`
- `email_sender.py` — side effect pós-tool, permanece como nó externo
- `detect_input_type` — roteamento de entrada, externo ao core
- Tools (`@tool` functions) — API inalterada

---

#### 4. Relação entre Middleware e outros Ps

O sistema de middleware torna P4 e P6 redundantes como nós manuais no grafo:

| Gap | Solução manual (sem middleware) | Com middleware LangChain v1 |
|-----|---------------------------------|----------------------------|
| P4 (guardrails PII) | Nó `validate_input` + `validate_output` | `PIIMiddleware` |
| P6 (context manager) | Função `trim_context()` manual | `SummarizationMiddleware` |
| P9 (HITL) | `interrupt()` manual no nó | `HumanInTheLoopMiddleware` |
| P1 (retry LLM) | tenacity em `llm_core.py` | `ModelRetryMiddleware` (complementar) |

**Recomendação:** implementar P8 antes de P4 e P6 — o middleware elimina código manual que
seria escrito para esses gaps.

---

## Quick Wins de Performance — descobertos em produção (Spec 004)

> Itens identificados durante a operação em produção no Render (junho 2026). Nenhum deles
> requer mudança de arquitetura. Devem ser feitos **antes** de qualquer item P1–P9, pois têm
> ROI imediato e custo zero ou mínimo.

| # | Ação | Arquivo | Esforço | Ganho | Custo | Prioridade |
|---|------|---------|---------|-------|-------|------------|
| **QW-1** | **Parallel tool calls** — habilitar chamadas paralelas de tools no LLM | `agent/agent/nodes/llm_core.py` | ~30 min | 1–3s por conversa | Zero | ✅ Fazer agora |
| **QW-2** | **UptimeRobot** — ping a cada 14 min no nginx + UI para evitar hibernação Render | Externo (sem código) | ~5 min | Elimina cold start | Grátis | ⚙️ Opcional — só vale no free tier |
| **QW-3** | **`durability: "exit"`** — ~~investigar se o managed LangGraph Server aceita checkpoint só ao final~~ **B0 probe (T005) confirmou**: NÃO é parâmetro de compile-time em `graph.py`. É parâmetro **por-run no payload do SDK client** (`stream.submit({ durability: "exit" })`). Implementado em `agent-ui-pro/src/components/thread/index.tsx`. O servidor não expõe env var nem config de servidor para default — ver [ADR-025 B3](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md). | ~~`agent/agent/graph.py`~~ `agent-ui-pro/.../thread/index.tsx` | ✅ feito | ~83% redução writes/turno | Zero | ✅ Implementado (B3) |
| **QW-4** | **Prompt engineering** — reduzir rounds de LLM de 4 para 2 com system prompt mais preciso | `agent/agent/nodes/llm_core.py` | ~2–4h | 5–7s por conversa | Zero | ✅ Próximo |
| **QW-5** | **Neon paid** — upgrade para P99 <20ms nos checkpoints | Infraestrutura | ~10 min | ~1s por conversa | $19/mês | ⚙️ Opcional — avaliar após QW-3 |
| **QW-6** | **Avaliação de modelos alternativos** — LLM de texto mais rápido/barato; pipeline de áudio multimodal | `llm_core.py`, `transcriber.py`, `tts.py` | ~1 dia de benchmark | Latência e custo por token | Varia | 🔍 Investigar |
| **QW-7** | **Redis Padrão D** — investigar `graph.compile(cache=RedisCache(...))` usando o `REDIS_URI` já existente | `agent/agent/graph.py` | ~1h de teste | 0.5–2s em tool calls repetidas | Zero (infra já existe) | 🔍 Investigar |

**Contexto técnico dos quick wins:**
- **QW-1**: o GPT-4o-mini hoje executa tool calls em sequência. Com `parallel_tool_calls=True`, chama múltiplas tools simultaneamente — ganho direto de latência.
- **QW-2**: serviços no Render free tier hibernam após 15 min de inatividade. UptimeRobot resolve, mas é workaround — se migrar para plano pago do Render, o item deixa de existir.
- **QW-3**: LangGraph por padrão escreve no Postgres após **cada nó** (6 nós = ~62 writes). O modo `'exit'` escreve apenas uma vez ao final. **Sonda B0 (T005) corrigiu a hipótese inicial**: `durability` NÃO é parâmetro de `graph.compile()` nem de `langgraph.json`. É **parâmetro por-run no SDK client** (`stream.submit({ durability: "exit" })`). Nginx sem Lua/NJS não consegue injetar no body. Env var de server-side default não existe no `langgraph_api`. A única forma de impor isso como política de backend seria (a) nginx com `ngx_http_js_module` ou (b) proxy intermediário — ambos adicionam complexidade desproporcional. **Implementado no client** — ver [ADR-025 seção B3](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md). Seguro pois `email_sender` já tem retry. Ver [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md).
- **QW-4**: cada round extra de LLM soma 1–2s. Reduzir de 4 para 2 rounds (input → resposta direta com tools) é o maior ganho individual possível sem mudança de infra.
- **QW-5**: só faz sentido se QW-3 não resolver — se o checkpoint por nó continuar, Neon paid reduz o overhead de ~1.2s para ~160ms. Se QW-3 funcionar, QW-5 tem impacto mínimo.
- **QW-6**: ver detalhamento abaixo.
- **QW-7**: o AgendAI já tem Redis rodando (`REDIS_URI` para SSE). O Padrão D do LangGraph (PR #5834, merged ago/2025) permite cachear outputs de nós com `graph.compile(cache=RedisCache(...))`. Tool calls repetidas na mesma sessão (buscar horários, buscar médico) retornariam do cache sem re-executar o nó. Investigar se o managed LangGraph Server expõe essa config de compilação. Ver [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md).

---

### Hierarquia de fontes de latência (para priorizar QWs)

> **Regra prática**: antes de otimizar checkpoint ou infra, garantir que os rounds de LLM estão no mínimo — eles dominam a latência total.

| Fonte | Ganho potencial | Esforço | Depende de |
|-------|-----------------|---------|------------|
| **Rounds de LLM** (4→2 via prompt engineering) | **5–7s** | Médio | Nada |
| **Parallel tool calls** (QW-1) | **1–3s** | Mínimo | Nada |
| **`checkpoint_mode='exit'`** (QW-3) | **~8s** potencial | Investigar | Suporte do managed server |
| **Groq Whisper** (QW-6, fluxo de áudio) | **~1.7s** | Baixo | Apenas áudio |
| **Redis cache de nós** (QW-7) | **0.5–2s** em calls repetidas | Investigar | Suporte do managed server |
| **Neon paid** (QW-5) | **~1s** | Nenhum (só custo) | $19/mês |

---

### Estratégia de persistência em camadas (síntese — FR-009/FR-010)

Os itens de checkpoint (QW-3, QW-5, QW-7, P10) e os Padrões A/C/D do [ADR-025](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md)
convergem numa única estratégia de persistência em duas camadas. O problema-raiz: hoje o runtime
grava **o estado completo do grafo no Postgres após cada nó** — ~62 writes e ~8s de overhead por
turno de 6 nós, sendo que ~75% desses writes não têm valor de recovery (estudo Crab, via learning
lesson).

```
                      HOJE (tudo no Postgres, a cada nó)
   nó1 ─write─► PG   nó2 ─write─► PG   nó3 ─write─► PG  ...  (~62 writes, ~8s)

                      ALVO (persistência em camadas)
   ┌─ Camada efêmera (curto prazo) ──────────────────────────────────┐
   │  Redis (já implantado p/ SSE) guarda o estado de sessão em voo   │
   │  → leitura/escrita <1ms, não bloqueia a resposta                 │
   └──────────────────────────────────────────────────────────────────┘
   ┌─ Camada durável (longo prazo, seletivo) ────────────────────────┐
   │  Postgres grava só nos pontos de recovery (fim de turno),        │
   │  apenas o que precisa sobreviver — não o estado completo a       │
   │  cada nó.  (checkpoint "exit"/seletivo)                          │
   └──────────────────────────────────────────────────────────────────┘
```

**Duas decisões, uma estratégia:**

1. **Frequência (QW-3 — `checkpoint_mode='exit'`/seletivo)**: gravar durável só em fronteiras de
   recovery (fim de turno), não após cada nó. Reduz ~62 → ~2 writes por turno. Seguro porque o
   único side effect irreversível (`email_sender`) já tem retry; tools são idempotentes.

2. **Camadas (QW-7 + Padrões A/C do ADR-025)**: estado de sessão efêmero no **Redis** (já
   presente para streaming SSE) — rápido e volátil; persistência durável seletiva no **Postgres**
   — só o que importa a longo prazo. O Redis Padrão D (cache de output de nós) é o primeiro passo
   de baixo risco que reusa a infra existente.

**Sequência de implementação (menor risco → maior):**

| Passo | Ação | Reversível? | Depende do managed server expor |
|-------|------|-------------|----------------------------------|
| 1 | QW-3 `durability: "exit"` no SDK client (**não** compile-time) | ✅ config | ~~na compilação~~ → parâmetro per-run; implementado no frontend |
| 2 | QW-7 Redis cache de output de nós | ✅ config | `cache=RedisCache(...)` na compilação |
| 3 | QW-5 Neon paid (se ainda houver gargalo) | ✅ infra | — |
| 4 | P10 migração p/ runtime próprio (Padrão A/C completo) | ❌ arquitetural | — (sai do managed) |

> **Fronteira com a Spec 007**: aqui a "persistência de longo prazo seletiva" refere-se ao
> **estado de execução do grafo** (checkpoint para recovery da conversa). A **memória de fatos do
> paciente** ("prefere sextas", "convênio Amil") é um conceito distinto e vive na
> [Spec 007](../007-memory-hitl/spec.md) — embora ambas compartilhem o mesmo princípio
> arquitetural: Redis para o efêmero/rápido, Postgres para o durável/seletivo.

---

### QW-6 — Avaliação de Modelos Alternativos

O sistema hoje usa três modelos OpenAI: `gpt-4o-mini` (LLM), `whisper-1` (STT) e `tts-1` (TTS). A pesquisa de produção levanta alternativas que podem reduzir latência e custo.

#### LLM de texto (substitui `gpt-4o-mini` em `llm_core.py`)

| Modelo | Latência | Custo | Tool calling | Observação |
|--------|----------|-------|--------------|------------|
| `gpt-4o-mini` (atual) | ~800ms/round | $0.15/1M tok in | ✅ Nativo | Referência |
| `gpt-4.1-nano` | ~400ms/round | $0.10/1M tok in | ✅ Nativo | OpenAI mais rápido/barato disponível |
| **Nemotron Super** (NVIDIA) | ~600ms/round | **Gratuito** via build.nvidia.com | ✅ | 49B params, grátis com API key NVIDIA |
| **Grok 3 Mini** (xAI) | ~500ms/round | $0.30/1M tok in | ✅ | Forte em raciocínio, contexto 131k |
| `gemini-2.0-flash` (Google) | ~350ms/round | $0.10/1M tok in | ✅ | Mais rápido do mercado, multimodal |

**Critério de escolha para AgendAI**: function calling confiável é obrigatório (6 tools). Testar com o fluxo completo de agendamento antes de trocar — alguns modelos menores cometem erros em tool calling encadeado.

#### Pipeline de áudio (substitui `whisper-1` + `tts-1`)

| Abordagem | Latência STT | Custo | Real-time | Observação |
|-----------|-------------|-------|-----------|------------|
| `whisper-1` + `tts-1` (atual) | ~1–2s | $0.006/min STT | ❌ Upload | Referência — funciona mas adiciona ~3s no fluxo de áudio |
| **GPT-4o Realtime API** | ~200ms | $0.10/min | ✅ WebSocket | STT + LLM + TTS em uma única conexão; elimina `transcriber.py` e `tts.py` separados |
| **Groq Whisper** (`whisper-large-v3`) | ~0.3s | $0.111/hora de áudio | ❌ Upload | Whisper mas com inferência 10× mais rápida via Groq |
| `gemini-2.0-flash` multimodal | ~300ms | $0.10/1M tok | ✅ Live API | Áudio direto como input — elimina STT separado |

**Rota recomendada para investigar**:
1. Curto prazo: trocar `whisper-1` por Groq Whisper — mesma interface, 10× mais rápido, sem mudança de arquitetura
2. Médio prazo: avaliar GPT-4o Realtime — elimina 2 nós do grafo (`transcriber`, `tts`), mas muda a arquitetura de streaming

```
Atual:
  áudio → transcriber (whisper-1, ~2s) → llm_core (gpt-4o-mini) → tts (tts-1, ~1s) → resposta

Com Groq Whisper (curto prazo):
  áudio → transcriber (groq whisper, ~0.3s) → llm_core → tts → resposta  [economiza ~1.7s]

Com GPT-4o Realtime (médio prazo):
  áudio → [GPT-4o Realtime WebSocket: STT+LLM+TTS em tempo real] → áudio  [elimina 2 nós]
```

**Restrição**: GPT-4o Realtime API exige WebSocket bidirecional — o modelo de SSE unidirecional do LangGraph Server não se encaixa diretamente. Precisaria de um nó wrapper ou mudança na arquitetura do grafo.

---

## Prioridade de Implementação

| P | Gap | Esforço | Impacto | Fase | Status |
|---|-----|---------|---------|------|--------|
| P1 | Retry + Circuit Breaker | ~2h | Elimina erros silenciosos em produção | 1/2 | ADR-024 |
| P4 | Guardrails input+output | ~4h | Segurança de conteúdo | 1/2 | Simplificado por P8 |
| P5 | Logs estruturados | ~3h | Observabilidade end-to-end | 1/2 | — |
| P6 | Context Manager | ~3h | Custo + latência em conv. longas | 2 | Simplificado por P8 |
| P8 | `create_agent` + Middleware | ~1 dia | Menos boilerplate, simplifica P4/P6 | 2 | ADR-026 — adotar (caminho oficial estável) |
| P10 | Migração do managed server → FastAPI próprio | ~3 dias | Controle total do checkpointer | 3 | Ativar só se: QW-3 rejeitado E checkpoint gargalo após QW-1/4 |
| — | Auth + sessão persistente | — | — | — | → [Spec 006](../../specs/006-auth-session/) |
| — | Memory Management | — | — | — | → [Spec 007](../../specs/007-memory-hitl/) |
| — | Human-in-the-Loop (HITL) | — | — | — | → [Spec 007](../../specs/007-memory-hitl/) |

---

## Acceptance Criteria por gap

### P1 (Retry + Circuit Breaker)
1. `RateLimitError` em `llm_core.py` → retry automático, usuário não vê erro na 1ª falha
2. 3 falhas consecutivas ao OpenAI → circuit breaker abre, erro claro em <1s
3. Cold start do Render na API → agente aguarda e retenta, não falha imediatamente
4. Startup da API não falha se Postgres demorar até 30s
5. 70 pytest + 39 Jest continuam passando

### P4 (Guardrails input+output)
1. Input com padrão de prompt injection → bloqueado antes de chamar o LLM
2. Input off-scope (ex: "me ajude a escrever código") → recusado com mensagem clara
3. Output com PII do paciente → redactado antes de chegar ao usuário
4. Output off-scope → substituído por mensagem de fallback da clínica

### P6 (Context Manager)
1. Conversa com mais de 10 turnos → mensagens antigas resumidas, não truncadas abruptamente
2. Token count do contexto enviado ao LLM ≤ limite configurado
3. Resumo preserva fatos críticos (agendamentos feitos, cancelamentos, preferências)

---

## Dependências entre gaps desta spec

```
P1 (retry) ─── independente ──── pode implementar agora

P4 (guardrails) ─── independente ─── pode implementar agora (Bedrock na Fase 3)

P5 (logs) ─── independente ──── pode implementar agora

P6 (context) ─── independente de auth ─── pode implementar agora

P8 (create_agent + middleware) ─── recomendado antes de P4/P6
   ├─ PIIMiddleware           → substitui nós manuais de P4
   └─ SummarizationMiddleware → substitui código manual de P6

P10 (migração managed server) ─── condicional: só se QW-3 falhar E checkpoint gargalo
```

---

## Out of Scope desta spec

- Autenticação de usuário → [Spec 006](../../specs/006-auth-session/spec.md)
- Sessão persistente por usuário → [Spec 006](../../specs/006-auth-session/spec.md)
- Memory Management → [Spec 007](../../specs/007-memory-hitl/spec.md)
- Human-in-the-Loop (HITL) → [Spec 007](../../specs/007-memory-hitl/spec.md)
- Vertex AI Memory Bank → Spec 007 ou posterior
- AWS Bedrock Guardrails (managed) → Spec 007 ou posterior
- Vertex AI Agent Engine Sessions → Spec 007 ou posterior
- Terraform / Cloud IaC → Spec futura

## Referências

- [LangGraph v1.0 Release Notes](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- [LangChain v1.0 Release Notes](https://docs.langchain.com/oss/python/releases/langchain-v1)
- [Middleware Overview](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [How Middleware Lets You Customize Your Agent Harness](https://www.langchain.com/blog/how-middleware-lets-you-customize-your-agent-harness)
- [ADR-024 — Retry e Resiliência](../../docs/adr/ADR-024-retry-resilience-strategy.md)
- [ADR-025 — Estratégia de Checkpoint](../../docs/adr/ADR-025-langgraph-checkpoint-strategy.md)
- [ADR-026 — create_agent + middleware vs. nós manuais](../../docs/adr/ADR-026-create-agent-middleware-vs-manual.md)
- [Architecture Roadmap V2.0](../../docs/AgendAI_Architecture_Roadmap.pdf)
