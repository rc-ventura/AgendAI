# ADR-012: `ApiClient` como singleton de módulo sob asyncio

**Status**: Accepted
**Data**: 2026-05-16
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/api_client.py:58-66`

---

## Contexto

O agente LangGraph (`agent/`) precisa chamar a API REST (`api/`) a partir de múltiplos nós do grafo (`tools.py`, `tool_result_processor.py` indiretamente, etc.). Cada chamada usa `httpx.AsyncClient`, que mantém internamente um **connection pool** (até 100 conexões TCP keep-alive por padrão) e estado HTTP/2 / SSL.

Criar uma nova instância de `httpx.AsyncClient` a cada chamada teria dois custos:

1. **Performance**: handshake TCP + TLS a cada request (~50-200ms extra).
2. **Recursos**: socket aberto e fechado a cada chamada, sem reuso de conexão.

Por isso queremos uma única instância compartilhada por todo o processo.

O serviço roda como **servidor asyncio single-thread** (`langgraph dev`, baseado em uvicorn/FastAPI). Cada execução do grafo é uma `Task` no event loop, e múltiplas execuções concorrentes compartilham a mesma thread do Python.

## Decisão

Implementar um **singleton lazy de módulo** com check-then-act simples, sem lock:

```python
_client: ApiClient | None = None

def get_client() -> ApiClient:
    global _client
    if _client is None:
        _client = ApiClient()
    return _client
```

A inicialização é preguiçosa (na primeira chamada) e o acesso posterior é apenas um `return`.

## Alternativas consideradas

### Alternativa A: Eager init no import

```python
_client: ApiClient = ApiClient()

def get_client() -> ApiClient:
    return _client
```

**Por que não escolhido (por enquanto)**: cria o `httpx.AsyncClient` no momento do import do módulo, o que pode falhar se `API_BASE_URL` ainda não estiver setado (ex.: durante testes que não usam o cliente real). O check-then-act preserva flexibilidade de testes.

**Vantagem**: elimina por completo qualquer possibilidade de race condition em qualquer arquitetura (single-thread, multi-thread, asyncio). É **a opção recomendada** caso futuramente o projeto migre para um modelo de execução multi-thread.

### Alternativa B: Lock (`threading.Lock` ou `asyncio.Lock`) com double-check

```python
import threading
_lock = threading.Lock()
_client: ApiClient | None = None

def get_client() -> ApiClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = ApiClient()
    return _client
```

**Por que não escolhido**: adiciona complexidade que não traz benefício no modelo asyncio single-thread atual. O lock seria *dead code* em todas as execuções práticas.

### Alternativa C: `threading.local()` (1 cliente por thread)

```python
import threading
_local = threading.local()

def get_client() -> ApiClient:
    if not hasattr(_local, "client"):
        _local.client = ApiClient()
    return _local.client
```

**Por que não escolhido**: fragmenta o connection pool entre threads, reduzindo eficiência de reuso de conexões. Só faria sentido se a biblioteca não fosse thread-safe — `httpx.AsyncClient` é thread-safe, então não há necessidade de isolamento.

## Consequências

### Aceitas

- **Funciona perfeitamente sob asyncio.** A função `get_client()` é `def` (síncrona) e **não contém `await`**. No modelo cooperativo do asyncio, o event loop só pode trocar de Task em pontos `await`. Logo, o bloco `if _client is None: _client = ApiClient()` é **atômico do ponto de vista do loop** — duas Tasks concorrentes nunca podem ambas executar a criação.
- **Singleton verdadeiro**: 1 `ApiClient` por processo, 1 connection pool compartilhado, eficiência máxima de reuso.
- **Código simples**: 5 linhas, fácil de ler, sem dependências externas.

### Trade-offs assumidos

- **Race condition latente sob multi-thread**. Se o projeto migrar para um modelo de execução com múltiplas OS threads (ex.: `uvicorn --workers N` em modo thread em vez de processo, ou nós do grafo embrulhados em `ThreadPoolExecutor`), o padrão check-then-act pode criar instâncias órfãs durante o boot:
  - Thread A vê `_client is None`, começa a criar.
  - Antes da atribuição, SO preempta para Thread B.
  - Thread B também vê `None`, cria sua própria instância.
  - Ambas atribuem; a última sobrescreve a primeira.
  - A instância "perdedora" fica órfã com seu `httpx.AsyncClient` aberto. O GC eventualmente coleta e o httpx loga `ResourceWarning: unclosed transport`.
- **Severidade do trade-off**: baixa.
  - O race só pode acontecer **uma vez por vida do processo** (na primeira chamada simultânea). Depois de `_client` estar setado, todas as chamadas seguintes apenas retornam a referência existente.
  - O pior caso é vazamento finito de N-1 instâncias órfãs, onde N = número de threads ativas no boot. Não é vazamento contínuo.
  - Não corrompe estado, não perde dados, não afeta usuário final.

### Condições que invalidam esta decisão

Esta decisão deve ser **revisitada** se:

1. **Servidor for configurado com múltiplas OS threads**, ex.: `gunicorn --workers 4 --threads 4` na frente do agente, ou `uvicorn` em modo thread.
2. **Nós do grafo forem envolvidos em `ThreadPoolExecutor`** para paralelização de operações CPU-bound.
3. **Logs de produção começarem a mostrar** `ResourceWarning: unclosed transport <httpx.AsyncHTTPTransport>`.
4. **Code review** identificar acoplamento crítico entre nós e a identidade do `ApiClient` (ex.: tentar usar mocks por-Task).

Em qualquer um desses casos, migrar para a **Alternativa A (eager init)** é a correção mais simples — uma única linha de mudança, sem trade-offs significativos.

## Referências

- Discussão original: Devin Review flag em PR #2 (commit `28cd6b6b`).
- `httpx.AsyncClient` é thread-safe: <https://www.python-httpx.org/async/#using-async-context-managers>
- Python `asyncio` event loop é single-thread por padrão: <https://docs.python.org/3/library/asyncio-eventloop.html>
