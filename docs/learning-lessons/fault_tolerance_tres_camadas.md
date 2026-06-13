# Fault Tolerance em Três Camadas: tenacity + RetryPolicy + error_handler

**Contexto:** Descoberta durante o B6 (Spec 005) ao analisar o `RetryPolicy` nativo do LangGraph
vs. nossa abordagem com tenacity + CircuitBreaker. A conclusão foi que as abordagens são
complementares — cada uma cobre o que a outra não alcança.

**Data:** 2026-06-11

**Intenção futura:** adicionar RetryPolicy + error_handler como segunda e terceira camadas
nos nós críticos (`chat_with_llm`, `send_email`, futuros nós de pagamento).

---

## O Modelo Mental: Três Anéis

```
┌──────────────────────────────────────────────────┐
│  RetryPolicy  (nó inteiro — orquestração)        │
│  ┌────────────────────────────────────────────┐  │
│  │  tenacity + CircuitBreaker  (call level)   │  │
│  │  ┌──────────────────────────────────────┐  │  │
│  │  │  a chamada externa em si             │  │  │
│  │  └──────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
           ↓ tudo falhou?
     error_handler  (compensação / Saga)
```

| Camada | Onde age | O que cobre | O que não cobre |
|---|---|---|---|
| **tenacity + CB** | Dentro do nó, na call | Erros transientes isolados; fail-fast quando serviço está fora | Timeout do nó inteiro; estratégia diferente no retry |
| **RetryPolicy** | Fronteira do nó (LangGraph) | Timeout do nó; retry com estratégia alternativa via `node_attempt` | Circuit breaker; granularidade de call |
| **error_handler** | Após todos os retries | Compensação de efeito colateral já persistido (Saga); encerramento gracioso | Nada — é o fim da linha |

---

## API do LangGraph (verificada em langgraph==1.2.0)

### RetryPolicy

```python
from langgraph.types import RetryPolicy

RetryPolicy(
    max_attempts=3,       # inclui a primeira tentativa
    initial_interval=0.5, # segundos antes do primeiro retry
    backoff_factor=2.0,   # multiplicador exponencial
    max_interval=128.0,   # teto em segundos
    jitter=True,          # aleatoriedade anti-thundering-herd
    retry_on=Exception,   # tipo, sequência de tipos, ou callable → bool
)
```

`default_retry_on` exclui: `ValueError`, `TypeError`, `ArithmeticError`, `ImportError`,
`LookupError`, `NameError`, `SyntaxError`, `RuntimeError`, `ReferenceError`,
`StopIteration`, `StopAsyncIteration`, `OSError`.

### runtime.execution_info

```python
from langgraph.runtime import Runtime

def meu_no(state: State, runtime: Runtime) -> State:
    runtime.execution_info.node_attempt        # int, começa em 1
    runtime.execution_info.node_first_attempt_time  # float | None
    runtime.execution_info.thread_id           # str | None
    runtime.execution_info.run_id              # str | None
    runtime.execution_info.checkpoint_id       # str
    runtime.execution_info.task_id             # str
```

### error_handler (Saga)

```python
from langgraph.errors import NodeError
from langgraph.types import Command

def meu_handler(state: State, error: NodeError) -> Command:
    return Command(
        update={"status": "compensado"},
        goto="no_de_compensacao",
    )

builder.add_node("meu_no", fn, retry_policy=..., error_handler=meu_handler)
```

### Overwrite — bypass do reducer

```python
from langgraph.types import Overwrite

def meu_no(state):
    # Força substituição mesmo em campo com reducer acumulativo (add_messages etc.)
    return {"messages": Overwrite(["nova mensagem"])}
```

Útil em retries onde o reducer acumularia duplicatas. **Restrição:** apenas um nó por
super-step pode usar `Overwrite` no mesmo campo — `InvalidUpdateError` se dois nós paralelos
tentarem simultaneamente.

---

## Exemplos para o AgendAI

### 1. `chat_with_llm` — fallback de modelo no retry do nó

```python
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy
from langgraph.errors import NodeError
from langchain_core.messages import AIMessage
from langgraph.types import Command

fallback_llm = ChatOpenAI(model="gpt-4o-nano", temperature=0.2).bind_tools(
    ALL_TOOLS, parallel_tool_calls=True
)

async def chat_with_llm(state: AgendAIState, runtime: Runtime) -> dict:
    # node_attempt > 1 = o nó falhou antes (CB provavelmente aberto)
    model = fallback_llm if runtime.execution_info.node_attempt > 1 else llm
    if state.get("input_type") == "audio":
        model = audio_llm if runtime.execution_info.node_attempt == 1 else fallback_llm

    try:
        response = await invoke_with_resilience(model, messages)
        return {"messages": [response]}
    except (CircuitOpenError, *RETRYABLE_EXCEPTIONS):
        raise  # deixa RetryPolicy tentar de novo com fallback_llm

def llm_error_handler(state: AgendAIState, error: NodeError) -> Command:
    msg = AIMessage(content=PT_BR_UNAVAILABLE)
    return Command(update={"messages": Overwrite([msg])}, goto=END)

# Registro no grafo:
builder.add_node(
    "chat_with_llm",
    chat_with_llm,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=5.0),
    error_handler=llm_error_handler,
)
```

**Divisão de responsabilidades:**
- tenacity: erro transiente isolado → retry silencioso (usuário não percebe)
- CB: 3 falhas seguidas → fail-fast, não martela a API
- RetryPolicy: nó falhou (CB aberto) → tenta com `fallback_llm`
- error_handler: fallback também falhou → PT-BR limpo, sem exception propagando no grafo

---

### 2. `send_email` — sem try/except inline + compensação declarativa

**Problema atual:** capturamos exceção dentro do nó e retornamos `email_pending: False` de
qualquer jeito — funciona, mas esconde o erro e mistura lógica de negócio com fault tolerance.

```python
async def send_email(state: AgendAIState) -> dict:
    # tenacity DENTRO de _send_smtp: retry SMTP 3x
    # Se esgotar → levanta exception → nó falha → RetryPolicy age
    await _send_smtp(state["email_payload"])
    return {"email_pending": False, "email_payload": None}

def email_error_handler(state: AgendAIState, error: NodeError) -> Command:
    logger.error(
        "email_definitive_failure payload=%s error=%s",
        state.get("email_payload"),
        error.error,
    )
    # Grafo continua — email falhou mas agendamento está salvo
    return Command(
        update={"email_pending": False, "email_payload": None},
        goto=END,
    )

builder.add_node(
    "send_email",
    send_email,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=10.0),
    error_handler=email_error_handler,
)
```

**Divisão de responsabilidades:**
- tenacity: retry de conexão SMTP (rede passageira)
- RetryPolicy: nó inteiro expirou (SMTP demorou demais) → reexecuta
- error_handler: SMTP fora definitivamente → limpa estado, loga, segue sem exception

**Vantagem sobre o atual:** `send_email` fica sem try/except — só lógica de negócio. A fault
tolerance é declarativa no registro do nó.

---

### 3. Futuro nó de pagamento — Saga completo

```python
async def cobrar_pagamento(state: AgendAIState, runtime: Runtime) -> dict:
    if runtime.execution_info.node_attempt > 1:
        # Primeira tentativa falhou — usa gateway de backup
        resultado = await gateway_backup.cobrar(state["agendamento_id"], state["valor"])
    else:
        resultado = await gateway_principal.cobrar(state["agendamento_id"], state["valor"])
    return {"pagamento_id": resultado["id"], "status_pagamento": "pago"}

def reverter_cobranca(state: AgendAIState, error: NodeError) -> Command:
    # Todas as tentativas falharam — cancela o agendamento já criado
    logger.error("payment_failure agendamento=%s", state.get("agendamento_id"))
    return Command(
        update={"status": "cancelado", "motivo": "falha no pagamento"},
        goto="cancelar_agendamento",  # nó de compensação
    )

builder.add_node(
    "cobrar_pagamento",
    cobrar_pagamento,
    retry_policy=RetryPolicy(max_attempts=2, retry_on=ConnectionError),
    error_handler=reverter_cobranca,
)
```

**Divisão de responsabilidades:**
- http_retry (nosso): retry da call HTTP ao gateway (erro de rede)
- `node_attempt > 1`: gateway de backup na segunda tentativa do nó
- error_handler: agendamento criado mas pagamento falhou → Saga cancela o agendamento

---

## Por que RetryPolicy sozinho não substitui tenacity + CB

| Situação | tenacity + CB | RetryPolicy | Resultado sem CB |
|---|---|---|---|
| 1 de 3 calls falha, outras ok | ✅ retry call | ✗ | ok |
| OpenAI fora, 30 usuários simultâneos | ✅ CB → 3 calls totais | ✗ | 30 × 3 = **90 calls** |
| Nó inteiro trava por timeout | ✗ | ✅ | ok |
| Retry com modelo diferente | ✗ | ✅ node_attempt | ok |
| Efeito colateral já persistido | ✗ | ✗ | ✅ error_handler |

**O circuit breaker é o que RetryPolicy não tem e não pode ter** — ele opera no nível do nó,
mas o CB precisa de estado compartilhado entre chamadas de múltiplos usuários. Uma variável
de módulo (nosso `llm_breaker`) ou estado do grafo (`failed_services` no `AgentState`) são
as únicas formas de implementar isso. RetryPolicy reinicia por request, sem memória entre requests.

---

## Relação com ADRs e próximos passos

- **ADR-024** — decisão de retry atual (tenacity + CB customizado); este documento é o upgrade path
- **ADR-026** — `create_agent` + middleware; quando migrar, `ModelRetryMiddleware` substitui
  `RetryPolicy` nos nós do `create_agent`, mas a lógica é análoga
- **Spec 006** (auth/session) e **Spec 007** (HITL/memory) — primeiros candidatos a usar
  `error_handler` para compensação (pagamento, confirmação humana com timeout)
- **B9** (logs estruturados) — `error_handler` deve emitir evento estruturado para correlacionar
  falha definitiva com thread/run IDs do LangGraph
