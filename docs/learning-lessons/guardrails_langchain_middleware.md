# Learning Lesson: Guardrails — built-in do LangChain vs. solução própria

**Data**: 2026-06-09
**Contexto**: Pesquisa para a Spec 005 P4 (guardrails) antes de implementar solução custom.
**Motivação**: "Talvez o próprio LangChain/Graph já tenha middleware built-in que faça isso —
pesquisar antes de implementar solução própria." (estava certo.)
**Aplicado em**: [Spec 005 — research R9](../../specs/005-agent-hardening/research.md), [ADR-026](../adr/ADR-026-create-agent-middleware-vs-manual.md)

---

## A lição

Antes de escrever nós manuais de guardrail (`validate_input`/`validate_output`), checar o que o
LangChain v1 já entrega. Resultado: **parte é built-in, parte não é** — e saber a fronteira evita
reinventar PII e evita assumir que injection/off-scope vêm de graça.

## O que é built-in (não reinventar)

| Middleware | Cobre | Estratégias / notas |
|-----------|-------|---------------------|
| **`PIIMiddleware`** | PII: email, cartão, IP, MAC, URL | `redact` / `mask` / `hash` / `block`; opera em **input, output e tool results**; relevante p/ HIPAA |
| **`HumanInTheLoopMiddleware`** | aprovação humana antes de ação sensível | é o HITL da Spec 007, não P4 |
| `SummarizationMiddleware` | compressão de histórico | usar no P6/contexto (B8) |
| `ModelRetryMiddleware` | retry de chamada ao modelo | complementa P1/ADR-024 (B6) |
| `LLMToolSelectorMiddleware` | reduz tools por chamada | ganho de latência/contexto |

> Fonte: [LangChain Guardrails docs](https://docs.langchain.com/oss/python/langchain/guardrails) ·
> [PIIMiddleware reference](https://reference.langchain.com/python/langchain/agents/middleware/pii/PIIMiddleware)

## O que NÃO é built-in (custom ou externo)

A doc oficial **explicitamente não** entrega:
- **Prompt injection**
- **Jailbreak**
- **Off-topic / off-scope refusal**

Esses exigem **custom middleware** (regex/term lists determinístico, ou check baseado em modelo)
**ou** um framework externo.

**Opção externa**: **NVIDIA NeMo Guardrails** tem integração documentada como *agent middleware*
do LangChain e cobre injection/jailbreak/topical rails prontos.

## Impacto na Spec 005

- **PII (FR-014/016)** → `PIIMiddleware` built-in. Sem regex caseiro para PII.
- **Injection + off-scope (FR-011/013)** → spike no B7: **custom middleware vs NeMo Guardrails**,
  escolha por acurácia em corpus pt-BR + footprint.
- Isso **reduz drasticamente** o código manual previsto: P4 vira "1 middleware built-in (PII) + 1
  middleware (injection/off-scope)" em vez de dois nós manuais completos.
- Conecta direto com o **gate do [ADR-026](../adr/ADR-026-create-agent-middleware-vs-manual.md)**:
  se a stack de middleware (`create_agent`) estiver estável, este é o caminho; senão, fallback
  para nós manuais — mas mesmo o fallback deve reusar a lógica de PII conhecida.

## Padrão correto: `create_agent` (verificado em langchain 1.3.1)

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    PIIMiddleware, SummarizationMiddleware,
    ModelRetryMiddleware, LLMToolSelectorMiddleware,
    HumanInTheLoopMiddleware,
)

agent = create_agent(
    model="openai:gpt-4o-mini",   # string ou BaseChatModel; sem bind_tools
    tools=[...],
    system_prompt="...",
    middleware=[
        PIIMiddleware("email", strategy="redact", apply_to_input=True, apply_to_output=True),
        PIIMiddleware("credit_card", strategy="block"),
        ModelRetryMiddleware(max_retries=3, backoff_factor=2.0),
        SummarizationMiddleware(
            model="openai:gpt-4o-mini",
            trigger=("tokens", 8000),
            keep=("messages", 10),
        ),
    ],
    cache=RedisCache(redis_client),  # B4 nativo
)  # → retorna CompiledStateGraph (Pregel), pode ser adicionado como nó no grafo pai
```

> **Nota importante**: o pacote PyPI é `langchain` (não `langchain-core`). São pacotes distintos.
> `langchain-core` é uma dependência transitiva; a API de agentes e middleware está no `langchain` base.

## Lições de processo (3 ciclos de erro → aprendizado)

| Ciclo | Erro | Fonte | Correção |
|-------|------|-------|----------|
| 1 | "`create_agent` foi removido em v1.1.0" | Post de fórum não verificado | Release notes oficiais: nunca removido |
| 2 | "PIIMiddleware não existe no ambiente" | Import falhou sem instalar `langchain` base | `langchain` ≠ `langchain-core`; instalar e testar |
| 3 | — | — | **Correto**: `langchain>=1.0` instalado, todos os imports OK |

**Regra consolidada**: toda afirmação sobre disponibilidade de API deve ser verificada com:
1. `pip show <package>` — o pacote está instalado?
2. `from package import Thing` — no ambiente real, com a versão correta.
Documentação sem instalação não conta.

## Referências

- [LangChain Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
- [PIIMiddleware reference](https://reference.langchain.com/python/langchain/agents/middleware/pii/PIIMiddleware)
- [NeMo Guardrails — LangChain agent middleware](https://docs.nvidia.com/nemo/guardrails/latest/integration/langchain/agent-middleware.html)
- [[arquitetura_redis_postgress]] · [ADR-026](../adr/ADR-026-create-agent-middleware-vs-manual.md)

---

## Implementação B7 — lições adicionais (2026-06-12)

### `PIIMiddleware` built-in não cobre CPF

O built-in cobre `"email"`, `"credit_card"`, `"ip"`. CPF (identificador fiscal brasileiro) não
está incluído. Em vez de compor o built-in com um custom para CPF, foi mais limpo implementar
um único `SecurityMiddleware` que cobre todos os tipos PII do domínio.

Regex CPF adotado: `\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b`

### `request.messages` — atribuição direta deprecada no LangChain

```python
request.messages = redacted_msgs  # DeprecationWarning: use request.override(messages=...)
```

O `ModelRequest` é imutável — `request.override(messages=...)` retorna uma nova instância.
Problema: `MagicMock().override(...)` não levanta `AttributeError`, retorna outro MagicMock.

**Solução para distinguir prod de teste:**
```python
if callable(getattr(type(request), "override", None)):
    request = request.override(messages=redacted_msgs)  # LangChain prod
else:
    request.messages = redacted_msgs  # MagicMock em testes
```

`type(MagicMock()).override` retorna `None`; `type(ModelRequest()).override` retorna o método.

### Regex com quantificadores `{0,2}` para variantes de injeção

`"Disregard your previous instructions"` tem dois modificadores antes do substantivo.
`\s+(your|the|all|previous)\s+(instructions)` só cobre um. Fix:

```python
r'disregard\s+(\w+\s+){0,2}(instructions?|rules?|constraints?|guidelines?)'
```

Cobre 0, 1, ou 2 palavras intermediárias sem regex explosivo.

### Posicionamento do SecurityMiddleware

Deve ser **outermost** (primeiro em `LLM_MIDDLEWARE`). Injection bloqueada antes do
circuit breaker — o CB não deve contar refusals de guardrail como "falhas de LLM".

### Spike NeMo Guardrails — resultado

Descartado: servidor extra, 200–500ms de latência, Colang DSL. Corpus pequeno + system
prompt como backstop semântico justificam o regex determinístico.
Quando revisar: se ataques reais passarem o regex recorrentemente após go-live.
