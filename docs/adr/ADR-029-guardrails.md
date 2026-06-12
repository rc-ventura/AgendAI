# ADR-029 — Guardrails: dois caminhos (determinístico vs semântico) — decisão atual

**Status:** Accepted  
**Data:** 2026-06-12  
**Spec relacionada:** [Spec 005 — Agent Hardening (B7/US3)](../../specs/005-agent-hardening/spec.md)  
**Depende de:** [ADR-026](./ADR-026-create-agent-middleware-vs-manual.md) (create_agent + middleware)

---

## Contexto

O ADR-026 estabeleceu que o `create_agent` + middleware é o padrão para o AgendAI. Para B7/US3
(FR-011..017), o sistema precisa de três controles de guardrail:

1. **Injection guard** (FR-011): bloquear padrões de prompt injection antes do LLM.
2. **Off-scope filter** (FR-013): recusar pedidos claramente fora do escopo (não médico-agendamento).
3. **PII redaction** (FR-014/016): redigir e-mail, CPF e telefone em input, output e resultados de ferramentas.

---

## Os dois caminhos para injection guard + off-scope

Todo guardrail de injection/off-scope cai em uma de duas categorias. Esta seção documenta
ambas para que a decisão de upgrade seja consciente, não reativa.

### Caminho 1 — Determinístico (regex)

| Dimensão | Valor |
|----------|-------|
| Latência por turno | ~0 ms (compilado em import, sem I/O) |
| Custo por mensagem | R$ 0 |
| Cobertura | Padrões estruturais conhecidos (OWASP LLM Top 10, keywords off-scope) |
| Limitação | Não detecta ataques semânticos novos (paráfrases, metáforas, jailbreaks indiretos) |
| Calibração | Adicionar/atualizar regex; regressão via `test_guardrails.py` |
| Infra necessária | Nenhuma |

**Backstop**: o system prompt do LLM já instrui o modelo a recusar off-scope e rejeitar
redefinição de identidade. O regex é uma camada rápida para casos óbvios; o LLM é o backstop
semântico para edge cases que o regex não cobre.

### Caminho 2 — Semântico (LLM classificador)

| Dimensão | Valor |
|----------|-------|
| Latência por turno | +100–500 ms (round-trip extra ao modelo) |
| Custo por mensagem | ~USD 0.0001–0.001 (depende do modelo/provedor) |
| Cobertura | Compreensão semântica — detecta paráfrases, metáforas, ataques novos |
| Limitação | **Requer calibração antes de go-live** — taxa de falso-positivo precisa ser medida em corpus pt-BR real (frases legítimas de agendamento que o classificador marque como "unsafe") |
| Calibração | Construir corpus anotado pt-BR, medir precision/recall, ajustar threshold ou allowlist |
| Infra necessária | Modelo classificador (ex.: Llama Guard, GPT-4o-mini binary prompt, NeMo Guardrails) |

**Quando usar**: se monitoramento pós-launch mostrar bypass recorrente do path determinístico,
ou se o público-alvo escalar para acesso aberto/não controlado.

**Trigger de revisão documentado**: > N bypasses por semana identificados nos logs de produção
(parâmetro N a definir com base em tolerância de risco do produto).

---

## Spike: regex determinístico vs NeMo Guardrails

### NeMo Guardrails (NVIDIA)

**O que oferece:**
- Compreensão semântica de injeção e off-scope via modelo de linguagem menor
- Configuração via Colang DSL (linguagem declarativa de regras)
- Suporte a pt-BR possível via prompt customizado

**Problemas para este caso:**
- Requer servidor NeMo Guardrails separado (nova infraestrutura, +1 serviço no docker-compose)
- Latência adicional de ~200–500ms por chamada (inferência de modelo)
- Overhead operacional: manter o servidor, versionar regras Colang, debugging distribuído
- Overkill para uma clínica com corpus pequeno e padrões de ataque bem definidos

**Decisão:** descartado. Constitution V (Simplicity) proíbe infra extra sem necessidade demonstrada.

### Regex determinístico (adotado)

**O que oferece:**
- Zero latência adicional (compilado, executado em microsegundos)
- Sem nova infraestrutura
- Determinístico: comportamento previsível, testável de forma unitária
- Padrões de injeção bem documentados (OWASP LLM Top 10)

**Limitações:**
- Não detecta injeção semântica sofisticada (ex.: metáforas que "redefinem" o assistente)
- Off-scope detection limitada a padrões explícitos — edge cases passam para o LLM
- Manutenção do corpus de regex se o domínio expandir

**Mitigação das limitações:** o system prompt já instrui o LLM a recusar off-scope e rejeitar
instruções de redefinição de identidade. O regex é uma camada de defesa rápida para os casos
óbvios; o LLM serve como backstop semântico para os casos de borda.

---

## Decisão

**`InjectionGuardMiddleware` (custom, `awrap_model_call`) + `PIIMiddleware` built-in com
`detector=` customizado para CPF e telefone.**

O `PIIMiddleware` suporta `detector=` regex, tornando desnecessário um custom class para PII.
Injection/off-scope não são suportados por nenhum built-in, logo requerem um custom middleware.
A separação de concerns fica explícita: `guardrails.py` só conhece bloqueio de injeção;
`middleware.py` é o composition root que monta o stack completo.

```python
# agent/agent/guardrails.py
class InjectionGuardMiddleware(AgentMiddleware):
    async def awrap_model_call(self, request, handler) -> AIMessage:
        # Extrai último HumanMessage; bloqueia injection ou off-scope sem chamar handler
        # Caso limpo: retorna await handler(request)

# agent/agent/middleware.py  (composition root)
pii_email  = PIIMiddleware("email", strategy="redact",  apply_to_input=True, apply_to_output=True, apply_to_tool_results=True)
pii_cpf    = PIIMiddleware("cpf",   detector=_CPF_REGEX, strategy="redact", ...)
pii_phone  = PIIMiddleware("phone", detector=_PHONE_REGEX, strategy="redact", ...)
```

### Posição no LLM_MIDDLEWARE

```python
LLM_MIDDLEWARE = [
    injection_guard_middleware,       # outermost — bloqueia injection/off-scope pré-LLM
    pii_email,                        # PIIMiddleware built-in (before_model/after_model)
    pii_cpf,                          # CPF com detector= regex (não coberto pelo built-in)
    pii_phone,                        # telefone com detector= regex
    llm_circuit_breaker_middleware,
    _llm_retry_middleware,
    _tool_retry_middleware,
    api_circuit_breaker_middleware,
]
```

`InjectionGuardMiddleware` é o primeiro (outermost): injection/off-scope são bloqueados ANTES
de qualquer retry ou circuit breaker. `PIIMiddleware` usa hooks `before_model`/`after_model`
(state-level), ortogonais ao `awrap_model_call` — não interferem na posição.

---

## Padrões implementados

### Injection guard (pre-LLM)

Regex case-insensitive cobrindo os padrões OWASP LLM Top 10 mais comuns:
- `ignore/disregard/forget/bypass/override ... instructions/prompt`
- `you are now a(n) ...`
- `act as (a/an) (ai/assistant/bot/model/...)`
- `pretend (you are/to be) ...`
- `jailbreak`, `DAN`, `do anything now`
- `<system>` tags, `[[nested injection]]`

### Off-scope filter (pre-LLM)

Regex cobrindo pedidos claramente fora de agendamento médico:
- Pedidos de escrita de código (pt-BR + en)
- Padrões `help me write a [language] script/program`

### PII redaction

| Tipo | Regex | Token |
|------|-------|-------|
| Email | RFC 5321 simplificado | `[EMAIL]` |
| CPF | `\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}` | `[CPF]` |
| Telefone | +55 prefixo opcional, DDD, 8–9 dígitos | `[PHONE]` |

Aplicado a: input (HumanMessage), output (AIMessage), tool results (ToolMessage).

---

## Alternativas consideradas

### A) Tudo em um único `SecurityMiddleware` custom

`awrap_model_call` cuidaria de injection + off-scope + PII (input, output, tool results).
Descartado: conflata concerns distintos; PIIMiddleware built-in já cobre o caso via hooks
state-level, tornando um custom class redundante para PII.

### B) Chamada a modelo pequeno (GPT-4o-mini) para classificar injection/off-scope

Latência extra por turno, custo adicional, complexidade de resposta estruturada. Descartado
per Constitution V e pelo fato de que o corpus de ataque já é bem definido.

### C) NeMo Guardrails (descartado — ver spike acima)

---

## Consequências

### Positivas
- Zero latência adicional para bloqueios (regex em microsegundos)
- Nenhuma nova infraestrutura
- CPF coberto nativamente (domínio brasileiro)
- Injection bloqueado ANTES do LLM ser chamado (SC-009)
- PII ausente de logs quando o logger registra o conteúdo das mensagens (SC-010)
- 83 pytest verdes (68 originais + 15 novos guardrail); 41 Jest verdes

### Negativas / riscos
- Injection semântico sofisticado pode passar. Mitigado pelo system prompt.
- Off-scope regex limitado a padrões conhecidos. Mitigado pelo LLM como backstop.

### Condições que revisam esta decisão
1. Corpus de ataques real (após go-live) mostrar bypass recorrente → adicionar NeMo Guardrails
   ou modelo classificador leve por turno.
2. CPF pattern falso-positivo frequente → ajustar regex (adicionar contexto ao redor).

---

## Relação com outras decisões

- **ADR-026**: `SecurityMiddleware` é middleware do `create_agent` — arquitetura confirmada.
- **ADR-024**: `SecurityMiddleware` é outermost, antes do `LLMCircuitBreakerMiddleware` — injection
  não chega ao circuit breaker.
- **ADR-030** (B8): `SummarizationMiddleware` será adicionado ao `LLM_MIDDLEWARE` após `SecurityMiddleware`.
