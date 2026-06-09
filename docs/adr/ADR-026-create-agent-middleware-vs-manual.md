# ADR-026 — Modernização do core agêntico: `create_agent` + Middleware

**Status:** Proposed — adotar middleware como caminho padrão (revisado 2026-06-09; ver Correção)

**Data:** 2026-06-09 (revisado no mesmo dia após verificação de fonte primária)

**Spec relacionada:** [Spec 005 — Agent Hardening (P8)](../../specs/005-agent-hardening/spec.md)

**Depende de:** [ADR-024](./ADR-024-retry-resilience-strategy.md) (retry), [ADR-013](./ADR-013-langgraph-dev-server.md), [ADR-014](./ADR-014-checkpointer-inmem.md)

---

## ⚠️ Correção factual (2026-06-09)

A primeira versão deste ADR afirmava que **"`create_agent` foi removido em `langchain v1.1.0`
sem aviso prévio"** e construía toda a decisão sobre um "gate de estabilidade" por causa disso.

**Essa premissa era FALSA.** Ela foi herdada do `technical-design.md` (rascunho anterior) e
propagada sem verificação. A checagem na fonte primária mostra:

- A [doc oficial de release do LangChain v1](https://docs.langchain.com/oss/python/releases/langchain-v1)
  apresenta `create_agent` como **o método padrão e recomendado** de construir agentes; a
  [v1.1](https://changelog.langchain.com/announcements/langchain-1-1) **expande** `create_agent`
  (aceita `SystemMessage` via `system_prompt`, model-profile system, middleware expandido).
- O único relato de "removido em v1.1.0" foi
  [um post de fórum](https://forum.langchain.com/t/create-agent-no-longer-exists-in-langchain-agents-v1-1-0/2350)
  que se revelou **erro de ambiente do usuário** (pacotes stale no virtualenv). A comunidade
  confirmou *"It has not been removed"* e o autor reconheceu que era o venv dele.

Conclusão: **não há instabilidade de remoção**. O "gate de estabilidade" perde a razão de ser e
é substituído pela prudência normal de engenharia (pinar versão, verificar import, testes verdes).

---

## Contexto

O grafo atual (`agent/agent/graph.py`) implementa manualmente lógica que o sistema de
**middleware** do LangChain v1 provê como prebuilt:

- retry de LLM (P1 / ADR-024 — `tenacity` em `llm_core.py`)
- guardrails de PII input/output (P4)
- summarização de contexto (P6)

O LangChain v1 introduziu `create_agent` (de `langchain.agents`) — o método **oficial e
recomendado** — que executa sobre o LangGraph e expõe hooks (`before_model`, `wrap_model_call`,
`after_model`, `wrap_tool_call`, ...) com middlewares prontos: `PIIMiddleware`,
`SummarizationMiddleware`, `ModelRetryMiddleware`, `HumanInTheLoopMiddleware`,
`LLMToolSelectorMiddleware`. `create_react_agent` (de `langgraph.prebuilt`) foi depreciado em
favor dele.

**Esta decisão é o "como" — não o "o quê".** Os requisitos (FR-001 retry, FR-014/015 guardrails,
FR-018/019 contexto) são satisfeitos de qualquer modo; o que muda é se via middleware prebuilt ou
via nós manuais.

> Nota de cobertura (ver [learning-lesson de guardrails](../learning-lessons/guardrails_langchain_middleware.md)):
> `PIIMiddleware` cobre PII built-in; **prompt injection / jailbreak / off-scope NÃO são built-in**
> e exigem middleware custom ou NeMo Guardrails. "Usar middleware" não significa "tudo pronto".

---

## Decisão

**Adotar `create_agent` + middleware como o caminho padrão de implementação de P1/P4/P6.** É o
método oficial e estável do LangChain v1.

1. **`MessagesState`** como classe base de `AgendAIState` — primitivo estável do LangGraph v1,
   elimina boilerplate de `add_messages`. Mudança aditiva, compatível com threads existentes.
2. **P4 (guardrails)**: `PIIMiddleware` built-in para PII; middleware custom (ou NeMo Guardrails)
   para injection/off-scope. Ver [ADR-029] (a criar no B7).
3. **P6 (contexto)**: `SummarizationMiddleware`.
4. **P1 (retry)**: `ModelRetryMiddleware` complementando o `tenacity`/`pybreaker` do ADR-024.
5. **Prudência normal de engenharia** (não um "gate" dramático): pinar a versão de
   `langchain`/`langgraph`, verificar o import na versão pinada, manter os testes verdes
   (constituição II), e confirmar que o managed LangGraph Server aceita o grafo de `create_agent`
   como subgrafo (verificação técnica de integração, não de estabilidade da API).

O pipeline de áudio (`transcribe_audio`/`synthesize_tts`), o `email_sender` e o
`detect_input_type` permanecem como nós externos ao `create_agent`.

---

## Alternativas consideradas

### A) `create_agent` + middleware (adotada)
- **Prós**: caminho oficial/recomendado; menos código manual; comportamentos prebuilt testados;
  ponto único de extensão para PII, summarização, retry e (futuro) HITL.
- **Contras**: acoplamento ao framework do LangChain — risco normal de dependência (não
  "remoção sem aviso", como antes se temia incorretamente).

### B) Nós manuais (a implementação legada, substituída)
- **Prós**: controle total; só primitivos do LangGraph.
- **Contras**: mais código para escrever e manter; reimplementa o que o middleware já oferece.
- **Status**: deixa de ser "fallback por risco de remoção" — é apenas a abordagem anterior,
  preterida. Permanece como referência se um requisito específico não couber no middleware.

---

## Consequências

### Positivas
- Menos código manual para P1/P4/P6; um ponto de extensão coeso.
- Alinha o projeto ao caminho oficial do LangChain v1 (suporte e docs futuros).
- `PIIMiddleware` entrega a parte de PII de P4 sem regex caseiro.

### Negativas / Trade-offs
- Acoplamento ao sistema de middleware do LangChain (dependência normal).
- Injection/off-scope ainda exigem trabalho (custom/NeMo) — middleware não cobre tudo.

### Condições que revisam esta decisão
1. LangChain depreciar/quebrar o middleware **de fato** (verificado em release notes oficiais, não
   em relato de fórum) → reavaliar.
2. O managed LangGraph Server não aceitar o grafo de `create_agent` como subgrafo → manter nós
   manuais para os gaps afetados.

---

## Lição de processo

Uma afirmação factual ("API removida") entrou numa spec e numa ADR **sem verificação de fonte
primária**, e quase virou base de uma decisão arquitetural (gate + fallback). Registrado em
[learning-lessons/guardrails_langchain_middleware.md](../learning-lessons/guardrails_langchain_middleware.md):
**toda alegação de remoção/deprecação de API deve ser confirmada em release notes oficiais, não
em um relato isolado de fórum.**

---

## Relação com outras decisões

- **ADR-024** (retry): `ModelRetryMiddleware` complementa o `tenacity`/`pybreaker`.
- **ADR-029** (a criar, B7): guardrails — `PIIMiddleware` + custom/NeMo.
- **ADR-030** (a criar, B8): contexto — `SummarizationMiddleware`.
- **Spec 007** (HITL): `HumanInTheLoopMiddleware` é a via natural do P9.
