# ADR-026 — Modernização do core agêntico: `create_agent` + Middleware

**Status:** Proposed — adotar `create_agent` + middleware como caminho padrão  
**Data:** 2026-06-09 (3ª revisão — versão final correta)

**Spec relacionada:** [Spec 005 — Agent Hardening (P8)](../../specs/005-agent-hardening/spec.md)

**Depende de:** [ADR-024](./ADR-024-retry-resilience-strategy.md) (retry), [ADR-013](./ADR-013-langgraph-dev-server.md)

---

## Histórico de correções

| Versão | Erro | Correção |
|--------|------|----------|
| v1 | "`create_agent` foi removido em v1.1.0" | FALSO — era erro de venv de fórum, não remoção real |
| v2 | "PIIMiddleware etc. não existem" | FALSO — pacote `langchain` (base) não estava instalado; `langchain-core` ≠ `langchain` |
| **v3** | — | **Correto**: instalar `langchain>=1.0`, middleware existe em `langchain.agents.middleware` |

**Lição de processo consolidada**: verificar sempre nas *release notes oficiais* e no ambiente
*com o pacote correto instalado*. `langchain-core` e `langchain` são PyPI packages distintos.

---

## Contexto

O grafo atual (`agent/agent/graph.py`) implementa manualmente o loop LLM + ferramentas via
`chat_with_llm` + `ToolNode` + `process_tool_results`. O `langchain` v1 (PyPI: `langchain>=1.0`)
introduziu `create_agent` — o padrão oficial para agentes — que oferece:

- loop LLM + ferramentas embutido (sem `bind_tools` manual)
- sistema de middleware composável: `PIIMiddleware`, `SummarizationMiddleware`,
  `ModelRetryMiddleware`, `HumanInTheLoopMiddleware`, `LLMToolSelectorMiddleware`
- suporte a `cache=` direto (integra B4 redisCache)

**Versões verificadas** (2026-06-09): `langchain==1.3.1`, `langgraph==1.2.0`, `langchain-openai==1.2.1`

```python
# Padrão novo — sem bind_tools
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware, SummarizationMiddleware, ModelRetryMiddleware

graph = create_agent(
    model="openai:gpt-4o-mini",   # string OU ChatOpenAI object — ambos funcionam
    tools=[buscar_horarios, criar_agendamento, ...],  # sem bind_tools
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True),
        PIIMiddleware("credit_card", strategy="block"),
        ModelRetryMiddleware(max_retries=3, backoff_factor=2.0),
        SummarizationMiddleware(model="openai:gpt-4o-mini", trigger=("tokens", 8000)),
    ],
    cache=RedisCache(redis_client),   # B4 nativo
)  # → retorna CompiledStateGraph diretamente
```

---

## Decisão

**Adotar `create_agent` + middleware como caminho padrão para P1/P4/P6/B7/B8.**

1. **`langchain>=1.0`** adicionado às dependências do projeto (`pyproject.toml`).
2. **B7 PII** (FR-014/016): `PIIMiddleware("email"/"credit_card"/"ip", strategy="redact"/"block")`
   — cobre input, output e resultados de ferramentas.
3. **B7 injection/off-scope** (FR-011/013): NÃO coberto por middleware built-in — spike em B7
   entre regex determinístico e chamada a modelo pequeno. ADR-029 decide.
4. **B8 contexto** (FR-018/019): `SummarizationMiddleware(model=..., trigger=("tokens", 8000))`.
5. **P1 retry** (ADR-024): `ModelRetryMiddleware` complementa `tenacity`/`pybreaker` nos nós de
   transcrição/API (que ficam fora do `create_agent`).
6. **B4 cache**: `create_agent(..., cache=RedisCache(...))` — integração nativa, sem patch extra.
7. Nós de áudio (`transcribe_audio`/`synthesize_tts`), `email_sender` e `detect_input_type`
   **permanecem fora** do `create_agent` — o subgrafo substitui apenas `chat_with_llm` +
   `execute_tools` + `process_tool_results`.
8. **`AgendAIState`** migra para usar `MessagesState` como base (B7, aditivo, compatível com
   threads existentes).

---

## Alternativas consideradas

### A) `create_agent` + middleware (adotada)
- **Prós**: padrão oficial; menos código manual; PII e retry prebuilt; `cache=` nativo.
- **Contras**: dependência do pacote `langchain` além de `langchain-core`; injection/off-scope ainda exige trabalho custom.

### B) `create_react_agent` (langgraph.prebuilt) + `pre_model_hook`/`post_model_hook`
- **Prós**: sem depender do pacote `langchain` base; primitivos mais baixo nível.
- **Contras**: sem middleware prebuilt; PII e summarização exigem implementação manual completa.
- **Status**: fallback se `create_agent` mostrar incompatibilidade com o managed server.

### C) Nós manuais (legado)
- **Status**: mantido como referência; preterido mas preservado se houver requisito que não caiba no middleware.

---

## Consequências

### Positivas
- Redução de código: `chat_with_llm` + `execute_tools` + `process_tool_results` → 1 `create_agent`.
- PII (FR-014/016) e retry (FR-001) prebuilt — não precisam ser escritos do zero.
- `SummarizationMiddleware` resolve B8 sem nó extra.
- `cache=` nativo em `create_agent` simplifica B4.

### Negativas
- Injection/off-scope (FR-011/013) não são prebuilt — ainda precisam de spike em B7.
- `langchain>=1.0` é uma dependência adicional (mas esperada para um projeto LangChain).

### Condições que revisam esta decisão
1. Managed LangGraph Server rejeitar o grafo do `create_agent` como subgrafo → fallback para nós manuais.
2. `langchain` v2 mudar a API do `create_agent` de forma breaking → verificar e adaptar.

---

## Relação com outras decisões

- **ADR-024** (retry): `ModelRetryMiddleware` dentro de `create_agent`; `tenacity`/`pybreaker` nos nós externos (transcriber, api_client).
- **ADR-029** (B7): guardrails — `PIIMiddleware` built-in + spike para injection/off-scope.
- **ADR-030** (B8): contexto — `SummarizationMiddleware` built-in.
- **Spec 007** (HITL): `HumanInTheLoopMiddleware` é a via natural do P9.
