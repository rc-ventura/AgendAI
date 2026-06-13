# Circuit Breaker em Agentes de IA: Libs vs. Implementação Customizada

**Contexto:** Pesquisa realizada durante o B6 (Spec 005 — Agent Hardening) ao avaliar como
proteger as chamadas ao OpenAI contra falhas transientes e cascata.

**Data:** 2026-06-10

---

## 1. Landscape de Bibliotecas Python

| Biblioteca | Stars | Async asyncio | Último release | Veredicto |
|---|---|---|---|---|
| **pybreaker** (danielfm) | 677 | ❌ Tornado only | Set 2025 | Mantida mas async quebrado |
| **circuitbreaker** (fabfuel) | 521 | ✅ desde v2.0 | Mai 2023 | Funciona; modo manutenção |
| **aiobreaker** (arlyon) | 29 | ✅ | >12 meses atrás | Abandonada (Snyk: unhealthy) |
| **purgatory** (mardiros) | 4 | ✅ | Nov 2024 | Niche, pouca adoção |
| **tenacity** | ~6k | ✅ | 2025 ativo | Retry only — sem state machine |
| **stamina** | ~500 | ✅ | 2025 ativo | Wrapper do tenacity, retry only |

### Por que pybreaker não funcionou

`pybreaker 1.4.1` documenta explicitamente suporte async apenas via `@gen.coroutine` do
**Tornado**. Em ambiente `asyncio` puro (LangGraph, httpx, OpenAI SDK), chamar `call_async`
resulta em `NameError: name 'gen' is not defined` — o namespace do Tornado não está presente.
Soluções consideradas e descartadas:

- Instalar Tornado como dependência → framework web completo (~5 MB) por 30 linhas de lógica
- Wrapper com `asyncio.to_thread()` → derrota o propósito de um circuit breaker async-native
- Versões mais antigas → sem `call_async`, sem suporte async algum

### Por que circuitbreaker (fabfuel) não foi adotado

Tecnicamente viável (v2.0+ suporta `async def` via decorator `@circuit`). Descartado por:
1. Sem releases desde mai/2023 — modo manutenção, risco de bit-rot
2. Para o `StateGraph` do LangGraph, o estado do breaker deveria idealmente residir no
   `AgentState` do grafo (ver Seção 3). Uma lib externa não integra com isso sem wrapping.

---

## 2. Por que a Comunidade de Agentes Usa Implementação Customizada

Pesquisa em Medium, DEV.to, Reddit (r/LangChain) e fóruns LangGraph revelou que **todos os
write-ups de produção** encontrados usam classes customizadas de 30–150 linhas. Nenhum artigo
recomenda pybreaker, aiobreaker ou similar por nome para agentes de IA.

**Razão central:** Circuit breakers clássicos detectam falha binária — `exception raised = fail`.
LLMs produzem uma classe diferente de falha que retorna HTTP 200:

| Tipo de falha | Detectado por lib genérica? | Detectado por nossa impl? |
|---|---|---|
| Connection error / timeout | ✅ | ✅ |
| Rate limit (429) | ✅ | ✅ |
| Resposta alucinada (HTTP 200, JSON válido, dados falsos) | ❌ | ❌ |
| Loop infinito de tool calls | ❌ | ❌ |
| Output semanticamente incoerente | ❌ | ❌ |

A nossa implementação atual cobre apenas a primeira coluna — **hard failures**. Isso é correto
para o escopo do B6 (proteção contra OpenAI offline), mas insuficiente para o modelo completo.

---

## 3. O Modelo Completo: Hannecke (2025)

**Referência:** https://medium.com/@michael.hannecke/resilience-circuit-breakers-for-agentic-ai-cc7075101486

### 3.1 Quatro estados (não dois)

```
CLOSED ──(health < 0.8)──► DEGRADED ──(health < 0.5)──► OPEN
  ▲                                                         │
  └────────── HALF-OPEN (graduated recovery) ◄─────────────┘
```

| Estado | Significado | Ação |
|---|---|---|
| **CLOSED** | Saudável | Operação normal |
| **DEGRADED** | health 0.5–0.8 | Tools de alto risco desabilitadas, output marcado "baixa confiança", human review |
| **OPEN** | health < 0.5 | Rejeição imediata; fallback em cache/template ou escalação humana |
| **HALF-OPEN** | Recuperação graduada | 5% → 20% → 50% do tráfego; N sucessos necessários por nível |

### 3.2 Health score com decay exponencial (não contador inteiro)

```python
TYPE_WEIGHTS = {
    "hard": 1.0,        # exceptions, timeouts, 5xx
    "structural": 0.7,  # output malformado (bad JSON, campos ausentes)
    "semantic": 0.85,   # alucinação, citação falsa (HTTP 200!)
    "behavioral": 0.8,  # loop infinito, runaway tokens
    "emergent": 0.95,   # reward hacking, specification gaming
}

def calculate_health(failures: list[Failure], window_seconds: int = 300) -> float:
    now = time.time()
    total_impact = 0.0
    for f in failures:
        age = now - f.timestamp
        if age < window_seconds:
            decay = math.exp(-age / window_seconds)  # falhas antigas pesam menos
            total_impact += f.severity * decay * TYPE_WEIGHTS[f.type]
    return max(0.0, 1.0 - (total_impact / 5.0))  # 5 falhas max-severity = health 0.0
```

### 3.3 Recuperação graduada (não flip binário após timeout)

```python
class GraduatedRecovery:
    LEVELS = {
        1: {"traffic": 0.05, "successes_needed": 10, "max_failures": 0},
        2: {"traffic": 0.20, "successes_needed": 20, "max_failures": 2},
        3: {"traffic": 0.50, "successes_needed": 50, "max_failures": 3},
    }
    def should_route_to_agent(self) -> bool:
        return random.random() < self.LEVELS[self.level]["traffic"]
```

**Lógica:** Após OPEN, passa para HALF-OPEN Level 1 (apenas 5% das requests passam).
10 sucessos consecutivos avançam para Level 2. Qualquer falha em Level 1 devolve ao OPEN.
Somente após Level 3 (50% do tráfego, 50 sucessos) o circuito fecha completamente.

### 3.4 Custo da detecção semântica

O artigo cita: "Uma query de $0.002 vira $0.009 com validação semântica completa" (~+200%).
Schema validation (estrutural) adiciona ~0% de overhead. LLM-as-Judge para semântico: +200%.
A solução prática: heurísticas baratas primeiro (verificação de campos obrigatórios, spot-check
de citações, self-consistency sampling em 2-3 respostas).

---

## 4. Gap Analysis: Nossa Implementação vs. Modelo Hannecke

| Dimensão | Nossa impl (B6) | Modelo completo |
|---|---|---|
| Estados | CLOSED / OPEN | CLOSED / DEGRADED / OPEN / HALF-OPEN |
| Falhas detectadas | Hard (exceptions) | 5 tipos incl. semântico e behavioral |
| Métrica interna | `int` contador | `float` health score com decay |
| Recovery | Timeout fixo → CLOSED | Graduated 3 levels, success-count based |
| State em grafo | Variável de módulo | Idealmente em `AgentState` |
| Observabilidade | ✅ logs Python (B6) | LangSmith + Arize Phoenix + OTEL |
| Thresholds por risco | Fixo | Por perfil de agente (financeiro vs. criativo) |

**O que entregamos no B6:** proteção contra OpenAI offline/throttling — o caso mais comum e
imediato. O modelo completo do Hannecke é o upgrade path natural quando o sistema escalar ou
a qualidade semântica virar requisito de compliance (e.g., agendamento médico com verificação
de diagnóstico).

---

## 5. LangGraph-Native: estado do breaker no grafo

Para sistemas multi-agente (Spec 007+), o estado do circuit breaker deve residir no
`AgentState` para que workers paralelos compartilhem visibilidade:

```python
from typing import Annotated
import operator

class AgendAIState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # ... campos existentes ...
    failed_services: Annotated[list[str], operator.add]  # ["openai", "api"] quando abertos
```

Nós verificam `"openai" in state["failed_services"]` antes de chamar. O orchestrator
escreve no estado quando detecta falha. Isso substitui a variável de módulo por estado
distribuído e auditável via LangSmith.

---

## 6. `AgentMiddleware` do LangChain 1.3.1

O LangChain Agent SDK (v1.x) expõe `AgentMiddleware` com `awrap_model_call` — permite
interceptar chamadas de modelo com lógica de retry/circuit breaker no nível do middleware:

```python
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRetryMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

class CircuitBreakerMiddleware(AgentMiddleware):
    def __init__(self, breaker: CircuitBreaker):
        self._breaker = breaker

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        if self._breaker.is_open:
            from langchain_core.messages import AIMessage
            return AIMessage(content=PT_BR_UNAVAILABLE)
        try:
            result = await handler(request)
            self._breaker.close()
            return result
        except (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError):
            self._breaker._fails += 1
            if self._breaker._fails >= self._breaker._fail_max:
                self._breaker._opened_at = time.monotonic()
            raise

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=[...],
    middleware=[
        CircuitBreakerMiddleware(llm_breaker),  # importa de agent.resilience
        ModelRetryMiddleware(max_retries=3, backoff_factor=2.0),
    ],
)
```

**Nota:** Este padrão só se aplica ao grafo criado via `create_agent`. O `StateGraph` manual
(nossa implementação atual de `graph.py`) não passa por `AgentMiddleware`. A migração para
`create_agent` está planejada no B7 (ADR-026).

---

## 7. Referências Completas

| Recurso | URL | Relevância |
|---|---|---|
| Hannecke — Circuit Breakers for Agentic AI (Pt 1) | https://medium.com/@michael.hannecke/resilience-circuit-breakers-for-agentic-ai-cc7075101486 | Modelo de referência completo |
| AI Agent Circuit Breakers — DEV.to (waxell) | https://dev.to/waxell/ai-agent-circuit-breakers-the-reliability-pattern-production-teams-are-missing-5bpg | Padrões de produção |
| Cost Circuit Breaker: 9 AI Agents (sebastian_chedal) | https://dev.to/sebastian_chedal/the-cost-circuit-breaker-how-we-prevent-runaway-spending-across-9-ai-agents-4i5k | Caso real: $47k runaway incident |
| 7 LangChain Retry & Timeout Patterns | https://medium.com/@connect.hashblock/7-langchain-retry-timeout-patterns-for-flaky-tools-a371c3edc1d3 | Retry patterns no ecossistema |
| Retry Storms in Multi-Agent LangGraph (LifeTidesHub) | https://www.lifetideshub.com/retry-storms-multi-agent-systems/ | Problema de workers paralelos |
| Error Handling in LangGraph (DEV.to — aiengineering) | https://dev.to/aiengineering/a-beginners-guide-to-handling-errors-in-langgraph-with-retry-policies-h22 | `with_retry()` nativo do LangGraph |
| pybreaker GitHub | https://github.com/danielfm/pybreaker | Lib rejeitada (Tornado async) |
| circuitbreaker GitHub (fabfuel) | https://github.com/fabfuel/circuitbreaker | Alternativa viável mas em manutenção |
| aiobreaker Snyk health | https://snyk.io/advisor/python/aiobreaker | Por que aiobreaker foi descartada |

---

## Relação com ADRs

- **ADR-024** — Estratégia de retry e resiliência; atualizado para refletir implementação real
- **ADR-026** — `create_agent` + middleware; `CircuitBreakerMiddleware` é o upgrade path do B7
