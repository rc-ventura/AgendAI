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

## Cuidado registrado (lição de processo)

Uma versão anterior desta análise (e do ADR-026) afirmava que `create_agent` "foi removido em
`langchain v1.1.0` sem aviso". **Isso era falso** — a verificação na fonte primária mostrou que
`create_agent` é o método oficial e estável do LangChain v1 (v1.1 o expande), e o relato de
"removido" foi um erro de ambiente (pacotes stale) num post de fórum, depois desmentido.

**Lição**: toda alegação de remoção/deprecação de API deve ser confirmada em **release notes
oficiais**, não num relato isolado de fórum. A afirmação errada quase virou base de uma decisão
arquitetural (um "gate de estabilidade" + fallback para nós manuais) — ver
[[arquitetura_redis_postgress]] para o princípio de verificar antes de decidir.

Prudência que **permanece válida** (genérica, não um gate dramático): pinar a versão e verificar o
import na versão pinada antes de depender.

## Referências

- [LangChain Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
- [PIIMiddleware reference](https://reference.langchain.com/python/langchain/agents/middleware/pii/PIIMiddleware)
- [NeMo Guardrails — LangChain agent middleware](https://docs.nvidia.com/nemo/guardrails/latest/integration/langchain/agent-middleware.html)
- [[arquitetura_redis_postgress]] · [ADR-026](../adr/ADR-026-create-agent-middleware-vs-manual.md)
