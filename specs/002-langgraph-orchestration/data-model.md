# Data Model: LangGraph Medical Scheduling Orchestration

**Feature**: 002-langgraph-orchestration
**Phase**: 1 — Design
**Date**: 2026-05-14

---

## Entidades do Serviço LangGraph (Python)

### AgendAIState

Estado compartilhado entre todos os nós do grafo. Imutável por nó — cada nó retorna delta.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `messages` | `Annotated[list[AnyMessage], add_messages]` | Histórico da conversa; acumulado automaticamente (não sobrescreve) |
| `input_type` | `Literal["text", "audio"]` | Tipo de entrada detectado pelo nó `detect_input_type` |
| `audio_data` | `bytes \| None` | Bytes do arquivo de áudio recebido; `None` para entrada de texto |
| `session_id` | `str` | ID da thread LangGraph Platform — identifica a sessão do paciente |
| `email_pending` | `bool` | Flag setada pelo nó de tools quando criar/cancelar agendamento é executado |
| `email_payload` | `dict \| None` | Dados do agendamento/cancelamento para montar o e-mail de confirmação |
| `final_response` | `str \| None` | Texto final da resposta antes de TTS (se audio) ou envio direto (se texto) |

**Transições de estado**:
```
START → input_type definido
detect_input_type → audio_data preenchido (se áudio) ou None (se texto)
transcribe_audio → messages recebe HumanMessage com transcrição
chat_with_llm → messages recebe AIMessage (com ou sem tool_calls)
execute_tools → messages recebe ToolMessage(s); email_pending = True se tool foi criar/cancelar
send_email → email_pending = False; email_payload = None
synthesize_tts → final_response em bytes (audio/mpeg)
```

---

### Tool (Definição de Ferramenta)

Cada tool é uma função Python decorada com `@tool` do LangChain, mapeada 1:1 para endpoint da API REST.

| Tool | Endpoint REST | Parâmetros | Retorno |
|------|---------------|------------|---------|
| `buscar_horarios_disponiveis` | `GET /horarios/disponiveis` | `data?: str (YYYY-MM-DD)` | lista de horários com médico |
| `criar_agendamento` | `POST /agendamentos` | `paciente_email: str`, `horario_id: int` | agendamento criado |
| `cancelar_agendamento` | `PATCH /agendamentos/{id}/cancelar` | `agendamento_id: int` | agendamento cancelado |
| `buscar_pagamentos` | `GET /pagamentos` | — | valores e formas de pagamento |
| `buscar_paciente` | `GET /pacientes/{email}` | `email: str` | dados do paciente |

---

### EmailPayload

Estrutura interna passada do nó `execute_tools` para `send_email`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `tipo` | `Literal["agendamento", "cancelamento"]` | Determina o template do e-mail |
| `paciente_email` | `str` | Destinatário |
| `paciente_nome` | `str` | Nome para personalização |
| `medico_nome` | `str` | Nome do médico |
| `data_hora` | `str` | Data e hora formatadas |
| `valor` | `float \| None` | Valor da consulta (apenas para agendamento) |
| `formas_pagamento` | `list[str] \| None` | Formas aceitas (apenas para agendamento) |

---

## Entidades da LangGraph Platform API (Runtime)

Gerenciadas automaticamente pelo `langgraph-cli` — não requerem implementação manual.

### Thread

Representa uma sessão de conversa do paciente.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `thread_id` | `str (UUID)` | Identificador único da sessão |
| `created_at` | `datetime` | Criação da thread |
| `updated_at` | `datetime` | Última atualização |
| `metadata` | `dict` | Metadados livres (ex: `{"patient_session": true}`) |

### Run

Representa uma execução do grafo dentro de uma thread.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `run_id` | `str (UUID)` | ID da execução |
| `thread_id` | `str` | Thread à qual pertence |
| `graph_id` | `str` | Sempre `"agendai_agent"` |
| `status` | `Literal["pending", "running", "success", "error"]` | Estado da execução |
| `input` | `dict` | Input enviado (mensagem ou áudio) |
| `output` | `dict \| None` | Output do grafo ao finalizar |

---

## Entidades Existentes (API REST — sem alteração)

As tabelas SQLite abaixo são consumidas via HTTP pelo serviço LangGraph. Nenhuma migração necessária.

| Tabela | Chave | Relacionamentos |
|--------|-------|-----------------|
| `medicos` | `id` | → `horarios.medico_id` |
| `pacientes` | `id`, único em `email` | → `agendamentos.paciente_id` |
| `horarios` | `id` | → `agendamentos.horario_id`; `disponivel: 0\|1` |
| `agendamentos` | `id` | → `pacientes`, `horarios`; `status: ativo\|cancelado` |
| `pagamentos` | `id` | Dado estático — valor e formas de pagamento |

---

## Diagrama de Fluxo de Dados

```
Paciente
  │ POST /runs (texto ou áudio)
  ▼
Agent UI (Next.js :3001)
  │ LangGraph Platform API
  ▼
LangGraph Server (:8123)
  │ StateGraph execution
  ├── detect_input_type
  │     └── (áudio) transcribe_audio → OpenAI Whisper
  ├── chat_with_llm → OpenAI GPT-4o-mini
  │     └── (tool_call) execute_tools
  │           ├── buscar_horarios_disponiveis → API REST :3000
  │           ├── criar_agendamento → API REST :3000 → email_pending=True
  │           ├── cancelar_agendamento → API REST :3000 → email_pending=True
  │           ├── buscar_pagamentos → API REST :3000
  │           └── buscar_paciente → API REST :3000
  ├── send_email (se email_pending) → Gmail SMTP
  └── synthesize_tts (se áudio) → OpenAI TTS
  │
  ▼
LangSmith (rastreia cada nó acima automaticamente)
```
