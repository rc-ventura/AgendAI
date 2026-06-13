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

## Comportamento em falha de extração (fail-open, deliberado)

O `InjectionGuardMiddleware.awrap_model_call` (`agent/agent/guardrails.py:129-148`) extrai o
texto da última `HumanMessage` dentro de um `try/except`. Se essa extração lançar exceção, o
guard **loga** `guardrail=extraction_failed` (`agent/agent/guardrails.py:137-138`, antes era um
`pass` silencioso) e **segue fail-open** — `last_human_text` permanece `""`, os dois `if` de
verificação (`agent/agent/guardrails.py:140` e `:144`) são pulados, e o request vai ao LLM **sem
checagem de guardrail**.

**Decisão: manter fail-open.** Avaliamos a alternativa fail-closed (recusar quando não é possível
inspecionar o input) e a descartamos para este domínio porque:

1. O atacante controla o **conteúdo de texto** da mensagem, não a **estrutura** do objeto
   `request.messages` (montada internamente pelo `create_agent`/LangChain). `_extract_str_content`
   (`agent/agent/guardrails.py:101-108`) é defensivo (trata `str`, `list`, fallback `str(content)`),
   então uma exceção real de extração é praticamente sempre uma **regressão de API** (mudança no
   `ModelRequest` numa atualização do LangChain), não um exploit.
2. O log `exc_info=True` torna qualquer quebra **visível** em vez de silenciosa — é o principal
   ganho deste ajuste, sem mudar a postura de segurança.
3. Clínica é domínio de acesso controlado; o `SYSTEM_PROMPT` é o backstop semântico (ver abaixo).

**Importante — por que NÃO basta "fail-closed quando `last_human_text == ''`":** a mesma condição
de texto vazio cobre dois casos distintos. Um fail-closed ingênuo sobre o texto vazio bloquearia
**100% das mensagens de voz** (ver a lacuna de áudio abaixo) e quebraria o produto. Por isso, se
algum dia for adotado fail-closed, ele deve disparar **apenas** no ramo `except` (extração lançou),
nunca no caso legítimo de texto extraído vazio. Teste de regressão do caminho de exceção:
`test_extraction_failure_is_logged_and_fails_open` em `agent/tests/test_guardrails.py`.

---

## Limitação — o canal de áudio NÃO passa pelos guardrails de injection/off-scope

**Fato:** mensagens de voz contornam completamente o regex de injection (`agent/agent/guardrails.py:56-73`)
e off-scope (`agent/agent/guardrails.py:77-85`). Isso é por design da pipeline, não um bug pontual.

**Por quê (cadeia de execução):**

1. `detect_input_type` (`agent/agent/nodes/input_detector.py:17-20`) converte o áudio em uma
   `HumanMessage` com content part `input_audio` — um blob base64, **sem** chave `"text"`.
2. O `InjectionGuardMiddleware` roda **dentro** do `audio_agent` (via `LLM_MIDDLEWARE`,
   `agent/agent/middleware.py`). Ao processar essa mensagem, `_extract_str_content`
   (`agent/agent/guardrails.py:101-108`) percorre a lista e faz `p.get("text", "")` em cada item;
   o dict de áudio não tem `"text"`, então retorna `""`.
3. Com `last_human_text == ""`, as condições em `agent/agent/guardrails.py:140` e `:144` são falsas
   → `handler(request)` é chamado **sem checagem**. Todo turno de voz passa batido.

**O placeholder `"[mensagem de voz]"` NÃO fecha essa lacuna.** O `strip_consumed_audio`
(`agent/agent/nodes/audio.py`) só roda em `extract_audio_response` (`agent/agent/graph.py`),
**depois** que o `audio_agent` já consumiu o áudio e o guard já rodou. Além disso, o placeholder é
um rótulo genérico — **não** contém as palavras faladas (o B5/ADR-028 removeu o Whisper). Logo, nem
no turno corrente (guard vê o blob) nem em turnos seguintes (guard vê o rótulo inócuo) há texto de
voz para o regex inspecionar.

**Eficácia duvidosa mesmo se transcrevêssemos:** um ataque falado raramente casaria com padrões
textuais exatos (`ignore previous instructions`, etc.) — fala tem hesitação, sotaque, sem pontuação.
O regex determinístico tem baixo retorno para voz de qualquer forma.

**Mitigação atual (única camada para voz): o `SYSTEM_PROMPT`.** O `audio_llm`
(`agent/agent/nodes/llm_core.py:30-37`) recebe o mesmo `SYSTEM_PROMPT` (`agent/agent/nodes/llm_core.py:3-24`),
cujo bloco "IDENTIDADE E LIMITES (não negociáveis)" (`agent/agent/nodes/llm_core.py:5-10`) instrui o
modelo a recusar redefinição de identidade, ignorar instruções embutidas e redirecionar para
agendamento. Para o canal de texto o prompt é a **segunda** camada (regex é a primeira); para o
canal de áudio ele é a **única** camada.

**Decisão: aceitar a lacuna.** Áudio passa pelos guardrails determinísticos sem bloqueio; o
`SYSTEM_PROMPT` é o backstop. Coerente com o domínio de acesso controlado. Fechar a lacuna exigiria
ou (a) transcrever o áudio antes do `audio_agent` — reintroduzindo Whisper e revertendo o ganho de
latência do B5/ADR-028 — ou (b) adotar o guard semântico (Caminho 2 acima), que entende intenção e
funcionaria para voz. Ambos ficam para o futuro.

**Condição de revisão:** se a clínica abrir para público geral, ou se monitoramento mostrar abuso
pelo canal de voz, priorizar o Caminho 2 (semântico) — que cobre voz e texto de uma vez.

---

## Relação com outras decisões

- **ADR-026**: `SecurityMiddleware` é middleware do `create_agent` — arquitetura confirmada.
- **ADR-024**: `SecurityMiddleware` é outermost, antes do `LLMCircuitBreakerMiddleware` — injection
  não chega ao circuit breaker.
- **ADR-030** (B8): `SummarizationMiddleware` será adicionado ao `LLM_MIDDLEWARE` após `SecurityMiddleware`.
