# ADR-026 — Modernização do core agêntico: `create_agent` + Middleware vs. nós manuais

**Status:** Proposed (decisão condicional — gate de estabilidade)

**Data:** 2026-06-09

**Spec relacionada:** [Spec 005 — Agent Hardening (P8)](../../specs/005-agent-hardening/spec.md)

**Depende de:** [ADR-024](./ADR-024-retry-resilience-strategy.md) (retry), [ADR-013](./ADR-013-langgraph-dev-server.md), [ADR-014](./ADR-014-checkpointer-inmem.md)

---

## Contexto

O grafo atual (`agent/agent/graph.py`) implementa manualmente lógica que o sistema de
**middleware** do LangChain v1 provê como prebuilt:

- retry de LLM (P1 / ADR-024 — `tenacity` em `llm_core.py`)
- guardrails de PII input/output (P4 — nós `validate_input`/`validate_output`)
- summarização de contexto (P6 — função `trim_context()`)

O LangChain v1 introduziu `create_agent` (de `langchain.agents`), que executa sobre o LangGraph
e expõe hooks (`before_model`, `wrap_model_call`, `after_model`, `wrap_tool_call`, ...) com
middlewares prontos: `PIIMiddleware`, `SummarizationMiddleware`, `ModelRetryMiddleware`,
`HumanInTheLoopMiddleware`. Adotá-los eliminaria código manual que, de outra forma, seria escrito
do zero para P1, P4 e P6.

**Esta decisão é o "como" — não o "o quê".** Os requisitos (FR-001 retry, FR-014/015 guardrails,
FR-018/019 contexto) são satisfeitos de qualquer modo; o que muda é se o fazemos via middleware
prebuilt ou via nós manuais.

### O bloqueador

`create_react_agent` (de `langgraph.prebuilt`) foi **depreciado** no LangGraph v1.0 em favor de
`create_agent`. Pior: **`create_agent` foi removido em `langchain v1.1.0` sem aviso prévio**. Os
primitivos do LangGraph (`StateGraph`, nós, arestas) permanecem estáveis; a instabilidade está na
camada de orquestração `create_agent` + middleware.

Isso transforma a adoção em uma decisão com risco real de manutenção: depender de uma API que já
demonstrou ser removida sem deprecação prévia.

---

## Decisão

**Abordagem preferida: implementar P1/P4/P6 via `create_agent` + middleware — condicionada a um
gate de estabilidade verificado no início da implementação.**

1. **Mudança estável e independente do gate**: adotar `MessagesState` como classe base do estado
   (`AgendAIState`). Isso é um primitivo estável do LangGraph v1, elimina boilerplate de
   `add_messages`, e pode ser feito já — não depende de `create_agent`.

2. **Gate de estabilidade** (avaliado quando P4/P6 entrarem em implementação):
   - A API `create_agent` + middleware está presente e estável na versão atual da `langchain`?
   - O changelog das últimas releases não sinaliza nova remoção/breaking?
   - O managed LangGraph Server suporta o grafo compilado via `create_agent` como subgrafo?

3. **Se o gate passar** → implementar guardrails (P4), context manager (P6) e retry complementar
   (P1) via middleware prebuilt. Uma implementação, menos código manual.

4. **Se o gate falhar** → implementar P4/P6/P1 via **nós manuais** (já especificados no
   technical-design da Spec 005 como fallback completo: `validate_input`/`validate_output`,
   `trim_context()`, `tenacity`). Os requisitos são atendidos do mesmo jeito.

O pipeline de áudio (`transcribe_audio`, `synthesize_tts`), o `email_sender` e o
`detect_input_type` permanecem como nós externos ao `create_agent` em qualquer cenário.

---

## Alternativas consideradas

### A) `create_agent` + middleware (preferida, condicional)
- **Prós**: menos código manual; comportamentos prebuilt testados; um único ponto de extensão
  para PII, summarização, retry e (futuramente) HITL.
- **Contras**: API removida em v1.1.0 sem aviso — risco de manutenção; acoplamento à camada de
  orquestração instável da `langchain`.

### B) Nós manuais (fallback)
- **Prós**: controle total; depende apenas dos primitivos estáveis do LangGraph; sem risco de
  remoção de API; padrão já usado no projeto.
- **Contras**: mais código para escrever e manter; reimplementa comportamentos que o middleware
  já oferece.

### C) Híbrido (adotado de fato)
- `MessagesState` agora (estável) + middleware **somente** se o gate passar; caso contrário, nós
  manuais. É a posição registrada acima — captura o ganho seguro sem apostar na API instável.

---

## Consequências

### Positivas
- A decisão fica explícita e auditável, com critério objetivo (gate) em vez de "depende".
- Captura imediatamente o ganho seguro (`MessagesState`) sem expor o projeto à API instável.
- Os requisitos de P1/P4/P6 não ficam bloqueados por P8 — há caminho garantido (nós manuais).

### Negativas / Trade-offs
- Se o gate falhar, escrevemos código manual que o middleware faria — retrabalho potencial se a
  API estabilizar depois.
- Manter dois caminhos mentais (middleware vs manual) até o gate ser avaliado.

### Condições que revisam esta decisão
1. `create_agent` + middleware estabiliza por ≥2 releases sem breaking → reavaliar adoção plena.
2. Surge necessidade de HITL (Spec 007) — `HumanInTheLoopMiddleware` reacende a avaliação do
   caminho middleware.

---

## Relação com outras decisões

- **ADR-024** (retry): `ModelRetryMiddleware` seria complementar ao `tenacity` já decidido lá.
- **Spec 005 P4/P6**: esta decisão define *como* esses gaps são implementados.
- **Spec 007** (HITL): se o caminho middleware for adotado, `HumanInTheLoopMiddleware` se torna a
  via natural para o P9 — caso contrário, `interrupt()` nativo.
