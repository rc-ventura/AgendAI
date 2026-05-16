# Architecture Decision Records (ADRs)

Este diretório consolida as **decisões arquiteturais** do projeto AgendAI. Cada ADR registra uma decisão técnica significativa: o contexto que motivou, as opções consideradas, a escolha final e suas consequências.

## Formato

Cada ADR segue o template:

```markdown
# ADR-XXX: Título da Decisão

**Status**: Proposed | Accepted | Superseded by ADR-YYY | Deprecated
**Data**: YYYY-MM-DD
**Spec relacionada**: 001-... | 002-... | —

## Contexto
O problema, as forças em jogo, o ambiente.

## Decisão
A escolha feita, em uma frase.

## Alternativas consideradas
Outras opções e por que foram descartadas.

## Consequências
Trade-offs aceitos, riscos conhecidos, condições futuras
que invalidariam a decisão.
```

## Índice

| ADR | Título | Status | Spec |
|---|---|---|---|
| [ADR-001](./ADR-001-node-express.md) | Stack da API REST: Node.js 20 + Express 4 | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-002](./ADR-002-sqlite-better-sqlite3.md) | Banco SQLite via `better-sqlite3` síncrono | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-003](./ADR-003-stateless-conversation.md) | Conversação stateless por sessão | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-004](./ADR-004-gpt-4o-mini.md) | GPT-4o-mini para LLM com function calling | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-006](./ADR-006-openai-whisper.md) | OpenAI Whisper para STT | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| [ADR-007](./ADR-007-openai-tts.md) | OpenAI TTS para síntese de voz | 📝 Referenciado, não documentado | [001](../../specs/001-n8n-medical-scheduling/) |
| ADR-011 | Caminho evolutivo para MCP (pendente — T063) | ⏳ Planejado | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-012](./ADR-012-apiclient-singleton-async.md) | `ApiClient` como singleton de módulo sob asyncio | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |
| [ADR-013](./ADR-013-langgraph-dev-server.md) | `langgraph dev` como servidor do agente (MVP) | ✅ Accepted | [002](../../specs/002-langgraph-orchestration/) |

> **Nota**: ADRs marcados como "Referenciado, não documentado" foram citados em outros documentos do projeto (`docs/initial_plan.md`, `specs/001-n8n-medical-scheduling/research.md`) mas ainda não têm arquivo dedicado. Tarefa de documentação retroativa pendente.

## Como adicionar um novo ADR

1. Use o próximo número livre na sequência (`ADR-013`, `ADR-014`, ...).
2. Crie o arquivo `docs/adr/ADR-XXX-titulo-kebab-case.md` seguindo o template acima.
3. Adicione uma linha na tabela de índice acima.
4. Linke o ADR a partir do código (comentário) ou da spec relacionada quando aplicável.
5. Ao **substituir** ou **descontinuar** um ADR, atualize o status e referencie o novo ADR que o substitui.
