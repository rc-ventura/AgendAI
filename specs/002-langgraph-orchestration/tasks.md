# Tasks: LangGraph Medical Scheduling Orchestration

**Feature Branch**: `002-langgraph-orchestration`
**Input**: `specs/002-langgraph-orchestration/` — plan.md, spec.md, data-model.md, research.md, contracts/

**Format**: `[ID] [P?] [Story?] Description — file path`

- **[P]**: Parallelizável (arquivo diferente, sem dependência em task incompleta)
- **[Story]**: User story alvo (US1–US6)
- **TDD obrigatório**: escreva o teste, confirme que FALHA, então implemente

---

## Phase 1: Setup (Estrutura do Projeto)

**Propósito**: Scaffolding inicial do serviço Python e configuração Docker

- [X] T001 Criar estrutura de diretórios completa do serviço agent conforme plan.md — `agent/agent/nodes/`, `agent/tests/`
- [X] T002 Criar `agent/pyproject.toml` com dependências: `langgraph>=1.0`, `langchain-openai`, `langsmith`, `langgraph-cli`, `httpx`, `tenacity`, `pytest`, `pytest-asyncio`, `respx`
- [X] T003 [P] Criar `agent/Dockerfile` — imagem Python 3.11-slim, instala deps via pyproject.toml, expõe porta 8123
- [X] T004 [P] Criar `agent/langgraph.json` — aponta `agendai_agent` para `agent/graph.py:graph`
- [X] T005 [P] Atualizar `.env.example` com novas variáveis: `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `API_BASE_URL`
- [X] T006 Adicionar serviço `agent` ao `docker-compose.yml` — build `./agent`, porta `8123:8123`, env_file `.env`
- [X] T007 [P] Criar `agent/agent/__init__.py` e `agent/agent/nodes/__init__.py` vazios

---

## Phase 2: Foundational (Bloqueante para todas as User Stories)

**Propósito**: Componentes base que toda user story depende — estado, cliente HTTP, tools, nós core

**⚠️ CRÍTICO**: Nenhuma user story pode começar até esta fase estar completa

- [X] T008 Criar `agent/tests/conftest.py` — fixtures: `mock_api_client` (respx), `mock_openai` (AsyncMock), `base_state`
- [X] T009 [P] Escrever teste FALHANDO para `AgendAIState` em `agent/tests/test_state.py` — valida campos, acumulação de mensagens via `add_messages`, transições de `email_pending`
- [X] T010 [P] Implementar `agent/agent/state.py` — `AgendAIState` TypedDict com: `messages: Annotated[list[AnyMessage], add_messages]`, `input_type`, `audio_data`, `session_id`, `email_pending`, `email_payload`, `final_response`
- [X] T011 Escrever teste FALHANDO para `api_client` em `agent/tests/test_api_client.py` — mocka HTTP com respx, valida os 5 métodos e tratamento de 404/409
- [X] T012 Implementar `agent/agent/api_client.py` — `httpx.AsyncClient` com base_url `API_BASE_URL`; métodos: `buscar_horarios(data?)`, `criar_agendamento(email, horario_id)`, `cancelar_agendamento(id)`, `buscar_pagamentos()`, `buscar_paciente(email)`
- [X] T013 [P] Escrever teste FALHANDO para `detect_input_type` em `agent/tests/test_nodes.py` — valida `text` quando `audio_data=None`, `audio` quando bytes presentes
- [X] T014 [P] Implementar `agent/agent/nodes/input_detector.py` — retorna delta de estado com `input_type` setado
- [X] T015 Escrever teste FALHANDO para `tools.py` em `agent/tests/test_nodes.py` — mocka `api_client`, valida que cada `@tool` chama o método correto e retorna JSON formatado
- [X] T016 Implementar `agent/agent/nodes/tools.py` — 5 funções `@tool` que chamam `api_client`; instanciar `ToolNode(tools=[...])` exportado como `tool_node`
- [X] T017 Escrever teste FALHANDO para `llm_core` em `agent/tests/test_nodes.py` — mocka `ChatOpenAI`, valida que tools são bound e mensagens do state são passadas
- [X] T018 Implementar `agent/agent/nodes/llm_core.py` — `ChatOpenAI(model="gpt-4o-mini", temperature=0.2)` com `.bind_tools(tools)`; system prompt em português/inglês
- [X] T019 Criar `agent/agent/graph.py` — `StateGraph(AgendAIState)` com nós `detect_input_type`, `chat_with_llm`, `execute_tools`; arestas: `START→detect_input_type`, `detect_input_type→chat_with_llm` (caminho texto), `add_conditional_edges("chat_with_llm", tools_condition)`; compilar como `graph`
- [X] T020 [P] Configurar `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=AgendAI` no serviço `agent` do `docker-compose.yml`

**Checkpoint**: Foundation pronta — user stories podem começar em paralelo

---

## Phase 3: US1 — Paciente Consulta Horários por Texto (Priority: P1) 🎯 MVP

**Goal**: Paciente envia texto perguntando horários e recebe lista em linguagem natural via Agent UI

**Independent Test**: `POST http://localhost:8123/threads/{id}/runs/stream` com `{"messages": [{"role": "human", "content": "Quais horários disponíveis?"}]}` retorna stream com lista de horários e médicos

- [X] T021 [P] [US1] Escrever teste FALHANDO de integração do grafo para fluxo texto→horários em `agent/tests/test_graph.py` — usa graph compilado com api_client mockado
- [X] T022 [US1] Validar e ajustar `graph.py` para o caminho texto completo: `detect_input_type(text) → chat_with_llm → execute_tools(buscar_horarios) → chat_with_llm → END`
- [X] T023 [US1] Escrever teste FALHANDO para `buscar_horarios_disponiveis` tool com filtro de data em `agent/tests/test_nodes.py`
- [X] T024 [US1] Validar que a tool `buscar_horarios_disponiveis` passa parâmetro `data` opcional corretamente para `api_client.buscar_horarios(data)` em `agent/agent/nodes/tools.py`
- [X] T025 [US1] Testar manualmente via `docker compose up --build -d` + Agent UI em `http://localhost:3001` — digitar "Quais horários disponíveis?" e verificar resposta em linguagem natural

**Checkpoint**: US1 completa — paciente consegue consultar horários via chat de texto

---

## Phase 4: US2 — Paciente Agenda Consulta por Texto (Priority: P1)

**Goal**: Paciente confirma agendamento via chat; sistema grava no banco e envia e-mail de confirmação

**Independent Test**: Sequência de mensagens termina em `criar_agendamento` com `paciente_email` + `horario_id` válidos → agendamento aparece no `GET /painel` e e-mail chega ao destinatário

- [X] T026 [P] [US2] Escrever teste FALHANDO para `email_sender` em `agent/tests/test_nodes.py` — mocka `smtplib.SMTP_SSL`, valida template de agendamento e retry com `tenacity`
- [X] T027 [P] [US2] Implementar `agent/agent/nodes/email_sender.py` — `smtplib.SMTP_SSL` com `GMAIL_USER`/`GMAIL_APP_PASSWORD`; `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))`; templates para `agendamento` e `cancelamento`
- [X] T028 [US2] Escrever teste FALHANDO para fluxo completo de agendamento em `agent/tests/test_graph.py` — valida que após `criar_agendamento` o nó `send_email` é acionado e `email_pending` volta a `False`
- [X] T029 [US2] Adicionar nó `send_email` e lógica de roteamento pós-tools em `agent/agent/graph.py` — `router_email` verifica `email_pending`; se True → `send_email` → `END`; se False → `END`
- [X] T030 [US2] Escrever teste FALHANDO para tools `criar_agendamento` e `buscar_paciente` em `agent/tests/test_nodes.py`
- [X] T031 [US2] Validar tools `criar_agendamento` e `buscar_paciente` em `agent/agent/nodes/tools.py` — `criar_agendamento` seta `email_pending=True` e `email_payload` no estado retornado
- [X] T032 [US2] Testar manualmente fluxo completo: "Quero agendar para joao@email.com no horário 3" → verificar agendamento em `http://localhost:3000/painel` e e-mail recebido

**Checkpoint**: US1 + US2 completas — fluxo principal do desafio técnico funcionando

---

## Phase 5: US3 — Paciente Cancela Consulta por Texto (Priority: P2)

**Goal**: Paciente cancela agendamento via chat; sistema cancela via API e envia e-mail de confirmação

**Independent Test**: Mensagem "Cancelar agendamento 1" → status muda para `cancelado` no painel e e-mail de cancelamento é enviado

- [X] T033 [P] [US3] Escrever teste FALHANDO para tool `cancelar_agendamento` em `agent/tests/test_nodes.py` — valida que seta `email_pending=True` com template de cancelamento
- [X] T034 [US3] Validar tool `cancelar_agendamento` em `agent/agent/nodes/tools.py` — `email_payload.tipo = "cancelamento"` com dados corretos
- [X] T035 [US3] Escrever teste FALHANDO de integração para fluxo cancelamento em `agent/tests/test_graph.py`
- [X] T036 [US3] Validar `email_sender.py` renderiza template de cancelamento corretamente — subject e body distintos do template de agendamento
- [X] T037 [US3] Testar manualmente: "Cancelar minha consulta 1" → verificar status `cancelado` no painel e e-mail recebido

**Checkpoint**: US1 + US2 + US3 completas — todos os fluxos de texto do desafio funcionando

---

## Phase 6: US4 — Paciente Envia Áudio e Recebe Resposta em Áudio (Priority: P2)

**Goal**: Upload de áudio no Agent UI → transcrição Whisper → LLM → resposta TTS reproduzida no browser

**Independent Test**: Upload de arquivo `.m4a` no Agent UI → player de áudio aparece com resposta falada relevante

- [X] T038 [P] [US4] Escrever teste FALHANDO para `transcriber` em `agent/tests/test_nodes.py` — mocka `openai.audio.transcriptions.create`, valida que `HumanMessage` com texto transcrito é adicionado ao estado
- [X] T039 [P] [US4] Implementar `agent/agent/nodes/transcriber.py` — `client.audio.transcriptions.create(model="whisper-1", file=audio_data)` → adiciona `HumanMessage(content=transcription)` ao estado
- [X] T040 [P] [US4] Escrever teste FALHANDO para `tts` em `agent/tests/test_nodes.py` — mocka `openai.audio.speech.create`, valida bytes mp3 no `final_response`
- [X] T041 [P] [US4] Implementar `agent/agent/nodes/tts.py` — `client.audio.speech.create(model="tts-1", voice="alloy", input=final_text)` → seta `final_response` como bytes `audio/mpeg`
- [X] T042 [US4] Escrever teste FALHANDO de integração para fluxo áudio completo em `agent/tests/test_graph.py`
- [X] T043 [US4] Adicionar caminho áudio ao `agent/agent/graph.py` — `detect_input_type(audio) → transcribe_audio → chat_with_llm → ...existing... → synthesize_tts → END`; `router_audio` verifica `input_type` antes de `END`
- [X] T044 [US4] Construir `agent-ui/` customizado com Next.js 14 + `@langchain/langgraph-sdk` (repo oficial `langchain-ai/agent-ui` retornou 404)
- [X] T045 [US4] Criar `agent-ui/src/components/AudioUploadButton.tsx` — gravação de microfone (MediaRecorder) + upload de arquivo `audio/*`
- [X] T046 [US4] Integrar `AudioUploadButton` no `ChatWindow.tsx` — botões ao lado do campo de texto
- [X] T047 [US4] Criar `agent-ui/Dockerfile` — build multi-stage `node:20-alpine`, expõe porta 3001
- [X] T048 [US4] Adicionar serviço `agent-ui` ao `docker-compose.yml` — build `./agent-ui`, porta `3001:3001`, env `NEXT_PUBLIC_API_URL=http://localhost:8123`, `NEXT_PUBLIC_GRAPH_ID=agendai_agent`
- [X] T049 [US4] Testar manualmente: gravar ou usar arquivo `.mp3` de teste, fazer upload no Agent UI, verificar resposta em áudio reproduzida no browser

**Checkpoint**: US4 completa — fluxo multimodal (áudio ↔ áudio) funcionando

---

## Phase 7: US5 — Desenvolvedor Rastreia Execuções no LangSmith (Priority: P2)

**Goal**: 100% das execuções aparecem no painel LangSmith com todos os nós rastreados

**Independent Test**: Após qualquer mensagem via Agent UI, acessar `smith.langchain.com` → projeto `AgendAI` → execução aparece com nós, tool calls e latências

- [X] T050 [P] [US5] Validar que `LANGCHAIN_TRACING_V2=true` e `LANGCHAIN_PROJECT=AgendAI` estão presentes no serviço `agent` do `docker-compose.yml` (T020)
- [X] T051 [US5] Escrever teste de smoke para tracing em `agent/tests/test_graph.py` — executa o grafo com `RunnableConfig({"run_name": "test_trace"})` e valida que `run_id` é retornado no output
- [X] T052 [US5] Adicionar `run_name` e `tags` ao `graph.compile()` em `agent/agent/graph.py` — `graph.compile(tags=["agendai", "production"])`
- [X] T053 [US5] Testar manualmente: enviar 3 mensagens diferentes via Agent UI → verificar no LangSmith que 3 traces distintas aparecem com nós `detect_input_type`, `chat_with_llm`, `execute_tools` visíveis

**Checkpoint**: Observabilidade validada — todas as execuções rastreáveis

---

## Phase 8: US6 — Paciente Consulta Valores e Formas de Pagamento (Priority: P3)

**Goal**: Paciente pergunta sobre preços e formas de pagamento; sistema responde com dados da API

**Independent Test**: Mensagem "Quanto custa a consulta?" → resposta contém valor em R$ e lista de formas aceitas

- [X] T054 [P] [US6] Escrever teste FALHANDO para tool `buscar_pagamentos` em `agent/tests/test_nodes.py`
- [X] T055 [US6] Validar tool `buscar_pagamentos` em `agent/agent/nodes/tools.py` — retorna descrição, valor formatado em R$ e formas de pagamento como lista legível
- [X] T056 [US6] Escrever teste FALHANDO de integração para fluxo de pagamento em `agent/tests/test_graph.py`
- [X] T057 [US6] Testar manualmente: "Quais as formas de pagamento?" → verificar resposta com dados do seed

**Checkpoint**: Todas as 6 user stories completas

---

## Phase Final: Polish & Cross-Cutting

**Propósito**: Integração completa, docker-compose validado, documentação

- [X] T058 [P] Validar `docker compose up --build -d` sobe todos os serviços sem erro: `api`, `agent`, `nginx`, `agent-ui`
- [X] T059 [P] Atualizar `README.md` — adicionar seção LangGraph: pré-requisitos, variáveis de ambiente, como usar o Agent UI, como acessar LangSmith
- [X] T060 [P] Atualizar `quickstart.md` em `specs/002-langgraph-orchestration/quickstart.md` — confirmar comandos e URLs após implementação
- [X] T061 Executar suite de testes completa: `cd agent && pytest tests/ -v --tb=short` — 28/28 testes passando
- [X] T062 Validar que testes existentes da API REST não foram afetados: `cd api && npm test`
- [X] T063 [P] Documentar caminho evolutivo MCP em `docs/adr/ADR-11-mcp-evolution.md` — decisão de usar `@tool`+httpx agora, critérios para migrar para MCP (conforme plan.md)
- [X] T064 Smoke test end-to-end todos os fluxos do desafio técnico via Agent UI e registrar evidências em `docs/prints/`

---

## Dependencies & Execution Order

### Dependências entre Fases

- **Phase 1** (Setup): Sem dependências — começar imediatamente
- **Phase 2** (Foundational): Depende de Phase 1 — **bloqueia todas as user stories**
- **Phase 3** (US1): Depende de Phase 2 — pode começar assim que T019 estiver completo
- **Phase 4** (US2): Depende de Phase 2 + US1 concluída (reutiliza graph.py)
- **Phase 5** (US3): Depende de Phase 2 + US2 (reutiliza email_sender.py)
- **Phase 6** (US4): Depende de Phase 2 — independente de US2/US3 (novos nós)
- **Phase 7** (US5): Depende de T020 (já em Phase 2) — validação manual após qualquer US
- **Phase 8** (US6): Depende de Phase 2 — independente das demais
- **Phase Final**: Depende de todas as fases anteriores desejadas

### Dependências dentro de cada User Story

```
Teste FALHANDO → Implementação → Teste passando → Teste manual
```

### Oportunidades de Paralelismo

```bash
# Phase 2 — podem rodar em paralelo:
T008 conftest.py  |  T009+T010 state.py  |  T011+T012 api_client.py
T013+T014 input_detector.py  |  T017+T018 llm_core.py

# Phase 6 US4 — podem rodar em paralelo:
T038+T039 transcriber.py  |  T040+T041 tts.py  |  T044 agent-ui fork

# Phase Final — podem rodar em paralelo:
T058 docker validate  |  T059 README  |  T063 ADR
```

---

## Implementation Strategy

### MVP (US1 + US2 apenas)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (**bloqueante**)
3. Complete Phase 3: US1 — consulta horários
4. Complete Phase 4: US2 — agendamento com e-mail
5. **PARAR e VALIDAR**: chat texto funcionando, e-mail enviado, LangSmith rastreando
6. Demo MVP: Agent UI em `localhost:3001`, painel em `localhost:3000/painel`

### Entrega Incremental

| Milestone | Entrega         | Teste independente                   |
| --------- | --------------- | ------------------------------------ |
| MVP       | US1 + US2       | Chat texto → agendamento → e-mail  |
| +US3      | Cancelamento    | Chat texto → cancelamento → e-mail |
| +US4      | Áudio          | Upload áudio → resposta em áudio  |
| +US5      | Observabilidade | Traces no LangSmith                  |
| +US6      | Pagamentos      | Consulta preços                     |
| Full      | Polish + docs   | `docker compose up` + README       |

---

## Notes

- `[P]` = arquivo diferente, sem dependência em task incompleta desta fase
- TDD obrigatório (Constitution III): escreva o teste, confirme FALHA, então implemente
- `api_client.py` sempre mockado nos testes com `respx` — nunca chama API real em testes
- `openai` sempre mockado com `AsyncMock` nos testes — nunca consome créditos em testes
- Commitar após cada task ou grupo lógico
- Parar em qualquer checkpoint para validar a user story independentemente
- N8N foi removido do `docker-compose.yml` — substituído integralmente pelo agente LangGraph (`agent/`) e pelo proxy `nginx/`
