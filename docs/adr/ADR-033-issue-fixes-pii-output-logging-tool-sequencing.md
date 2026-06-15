# ADR-033 — Correções pós-spec-005: saída PII, nível de log e sequenciamento de ferramentas

**Status:** Accepted
**Data:** 2026-06-15
**Spec relacionada:** [Spec 005 — Agent Hardening](../../specs/005-agent-hardening/spec.md)
**Relacionado a:** [ADR-024](./ADR-024-retry-resilience-strategy.md) (resiliência/log),
[ADR-027](./ADR-027-latency-tactics.md) (parallel tool calls),
[ADR-029](./ADR-029-guardrails.md) (guardrails/PII),
[ADR-031](./ADR-031-structured-logging.md) (structured logging)

---

## Contexto

Após a PR #10 (spec 005), três issues foram abertas apontando problemas no agente:

- **#11** — CPF mascarado expõe o formato interno `[REDACTED_CPF]` (e a estrutura de
  content blocks serializada) ao cliente.
- **#12** — chamada paralela de `buscar_paciente` + `buscar_horarios` é incoerente:
  o fluxo não trata "paciente não encontrado".
- **#13** — `configure_logging()` ignora `setLevel` quando o uvicorn já instalou
  handlers; logs INFO podem desaparecer silenciosamente. Inclui também um ajuste de
  documentação sobre `circuit_breaker=closed`.

Este ADR registra as decisões tomadas para cada uma.

---

## Decisão

### #11 — Sanitização de PII na saída via middleware dedicado

A redação de saída de CPF/telefone sai do `PIIMiddleware` built-in e passa a ser feita
por um `PIIOutputSanitizerMiddleware` (`agent/agent/pii_output.py`).

**Causa raiz:** `PIIMiddleware.after_model` faz `str(message.content)`. Quando o modelo
retorna *content blocks* (lista `[{"type": "text", "text": ...}]`), o `str()` serializa
a lista inteira; a regex então redige o CPF dentro dessa string e o cliente recebe
`[{'text': '[REDACTED_CPF]', 'type': 'text'}]` — vazando tanto a estrutura interna quanto
o token `[REDACTED_*]`.

**Solução:** o novo middleware, posicionado após os `PIIMiddleware` no stack:
1. Achata os content blocks em texto puro (sem vazar a lista serializada);
2. Mascara CPF/telefone **inline** (`***.***.***-**`, `(**) *****-****`), mantendo a
   mensagem legível;
3. Substitui qualquer token `[REDACTED_CPF]`/`[REDACTED_PHONE]` que o LLM tenha ecoado.

Só atua quando há PII na mensagem — respostas normais com content blocks passam intactas.
`apply_to_output=False` foi setado em `pii_cpf`/`pii_phone`; a redação de **input** e
**tool results** continua no built-in (esses caminhos não chegam ao usuário diretamente).

> Por que mask inline e não uma mensagem genérica ("dados ocultos"): preserva o resto da
> resposta e a usabilidade, conforme a opção (b) sugerida na issue. O CPF real nunca é
> exposto e o token interno nunca vaza.

### #12 — Sequenciamento de ferramentas no agendamento (reverte parallel lookup do ADR-027 para este fluxo)

Apenas o **system prompt** (`agent/agent/nodes/llm_core.py`) foi alterado — sem mudança de
arquitetura nesta etapa, conforme decidido com o requester. O prompt deixa de instruir a
chamada **simultânea** de `buscar_horarios_disponiveis` + `buscar_paciente` e passa a exigir:

- uma ferramenta por vez (sem chamadas em paralelo);
- `buscar_paciente` **primeiro**; o resultado decide o fluxo:
  - paciente **não encontrado** → informar que não está cadastrado, **não** prosseguir e
    orientar cadastro;
  - paciente **encontrado** → então `buscar_horarios_disponiveis`.

Isto supera, **apenas para o fluxo de agendamento**, a tática de parallel tool calls do
ADR-027 (QW-4/B2): a dependência lógica entre as duas chamadas torna o paralelismo
incoerente. A decisão arquitetural completa (remover `buscar_paciente` sob autenticação —
spec 006 — vs. nó dedicado de "paciente não encontrado") fica para a spec 006; aqui apenas
estancamos o comportamento improvisado do LLM.

### #13 — `setLevel(INFO)` antes do guard de handlers + nota no ADR-024

`configure_logging()` (`agent/agent/logging_config.py`) passa a chamar
`root.setLevel(logging.INFO)` **antes** do `if root.handlers: return`. Assim o nível é
sempre garantido, mesmo quando o uvicorn do LangGraph Server já instalou handlers antes de
importar o grafo. O guard segue evitando duplicar handlers.

Sem isso, se o servidor mudar o nível default para acima de INFO, todos os `logger.info(...)`
do agente (`circuit_breaker=open`, `pii_redacted`, `summarization_triggered`) sumiriam
silenciosamente — bomba-relógio de observabilidade.

A tabela de observabilidade do ADR-024 ganhou uma nota explicitando que
`circuit_breaker=closed` só é emitido **na recuperação** (`_fails > 0`), não no caminho feliz.

---

## Alternativas consideradas

- **#11 — usar `strategy="mask"` do built-in:** ainda passaria pelo `str(content)` e
  vazaria a estrutura de content blocks; não resolve a causa raiz.
- **#12 — desabilitar `parallel_tool_calls` no modelo:** o paralelismo aqui era guiado
  pelo prompt (não há flag setado no código atual), então ajustar o prompt é suficiente e
  menos invasivo. A reestruturação do grafo foi deferida para a spec 006.
- **#13 — não fazer nada (funciona hoje):** rejeitado; é um risco latente de observabilidade
  com custo de correção de 1 linha.

---

## Consequências

- **#11:** saída sempre em texto limpo; CPF/telefone mascarados inline; nenhuma estrutura
  interna ou token de redação vaza. Coberto por testes em `tests/test_guardrails.py` (seção 7).
- **#12:** +1 round de LLM no agendamento (sequencial em vez de paralelo) em troca de um
  fluxo coerente para "paciente não encontrado". Decisão arquitetural final pendente na spec 006.
- **#13:** nível INFO garantido independ. da ordem de import do servidor; logs de
  observabilidade não desaparecem se o default do servidor mudar. Coberto por teste em
  `tests/test_nodes.py`.
