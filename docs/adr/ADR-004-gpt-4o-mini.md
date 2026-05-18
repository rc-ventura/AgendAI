# ADR-004: GPT-4o-mini como LLM com function calling

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/nodes/llm_core.py`, `agent/agent/nodes/tools.py`

---

## Contexto

O agente precisa de um LLM para interpretar intenções do paciente em linguagem natural e decidir quais ferramentas chamar (buscar horários, criar agendamento, cancelar, consultar pagamentos). O modelo precisa suportar **function calling nativo** e ter latência aceitável para chat (<5s).

## Decisão

Usar **GPT-4o-mini** (`gpt-4o-mini`) como LLM principal, com **5 tools** definidas via `@tool` decorator do LangChain e executadas por `ToolNode` do LangGraph.

### Tools disponíveis

| Tool | Endpoint REST | Ação |
|------|--------------|------|
| `buscar_horarios_disponiveis` | `GET /horarios/disponiveis` | Lista horários com médico, data, hora |
| `criar_agendamento` | `POST /agendamentos` | Agenda consulta para paciente |
| `cancelar_agendamento` | `PATCH /agendamentos/:id/cancelar` | Cancela agendamento existente |
| `buscar_pagamentos` | `GET /pagamentos` | Consulta valores e formas de pagamento |
| `buscar_paciente` | `GET /pacientes/:email` | Localiza paciente por e-mail |

## Alternativas consideradas

### Alternativa A: Claude API (Anthropic)
**Por que não**: O desafio técnico especifica OpenAI explicitamente. Claude seria preferível pela constituição do projeto, mas é um requisito do avaliador.

### Alternativa B: GPT-4o (modelo completo)
**Por que não**: 3-5x mais caro que GPT-4o-mini, latência maior (~5-8s vs ~2-4s). Para function calling simples de agendamento, o mini é suficiente.

### Alternativa C: Modelo open-source local (Llama, Mistral)
**Por que não**: Exige GPU ou latência proibitiva em CPU. Function calling em modelos open-source é menos confiável. Adiciona complexidade de servir o modelo.

### Alternativa D: Múltiplos modelos por intenção
**Por que não**: Complexidade de roteamento de modelos. Um modelo único com function calling cobre todos os casos do MVP.

## Consequências

### Aceitas
- **Function calling confiável**: GPT-4o-mini tem suporte nativo a tools — o LLM decide quando chamar ferramenta vs responder diretamente.
- **Custo baixo**: ~$0.15/1M input tokens, ~$0.60/1M output tokens. Conversa típica custa <$0.01.
- **Latência aceitável**: 2-4s por chamada em condições normais.
- **Streaming**: tokens aparecem progressiveamente no Agent UI.

### Trade-offs
- **Dependência de fornecedor único**: OpenAI para LLM + Whisper + TTS. Se API cair, sistema inteiro para.
- **Qualidade em pt-BR**: GPT-4o-mini é competente em português, mas ocasionalmente mistura inglês em termos médicos.
- **Sem fine-tuning**: modelo genérico, não especializado em terminologia médica.

### Condições que invalidam
1. Custos escalarem em produção → avaliar GPT-4o-mini fine-tuned ou modelo open-source.
2. OpenAI descontinuar GPT-4o-mini → migrar para sucessor (GPT-5o-mini?).
3. Requisitos de privacidade impedirem API externa → modelo local.

## Referências

- `agent/agent/nodes/llm_core.py` — `ChatOpenAI(model="gpt-4o-mini")`
- `agent/agent/nodes/tools.py` — 5 `@tool` definitions + `ToolNode`
- Spec 002: `specs/002-langgraph-orchestration/spec.md:140` — FR-003 (5 tools)
