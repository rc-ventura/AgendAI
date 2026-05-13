---
description: "Lista de tarefas para N8N Medical Scheduling Automation"
---

# Tasks: N8N Medical Scheduling Automation

**Input**: Documentos de design em `specs/001-n8n-medical-scheduling/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Stack**: Node.js 20 + Express 4 + better-sqlite3 + node-cache + Jest/Supertest | N8N Docker | GPT-4o-mini | OpenAI TTS/Whisper | Gmail API

**Convenção**: `[P]` = paralelo (arquivos diferentes, sem dependência), `[USn]` = user story

---

## Phase 1: Setup

**Objetivo**: Estrutura de projeto, Docker e configuração de ambiente.

- [x] T001 Criar estrutura de pastas completa conforme plan.md (`api/src/db/`, `api/src/routes/`, `api/src/cache/`, `api/src/middlewares/`, `api/tests/`, `n8n/data/`, `postman/`, `docs/prints/`, `data/`); criar `n8n/data/.gitkeep` para que o volume Docker `./n8n/data:/home/node/.n8n` funcione sem erro na primeira execução
- [x] T002 Inicializar projeto Node.js em `api/` com `npm init` e instalar dependências: `express`, `better-sqlite3`, `node-cache` em `api/package.json`
- [x] T003 [P] Instalar dependências de desenvolvimento em `api/package.json`: `jest`, `supertest`, `nodemon`; configurar scripts `test` e `dev`
- [x] T004 [P] Criar `api/Dockerfile` (node:20-alpine, copia src, instala deps, expõe porta 3000, cmd: `node src/server.js`)
- [x] T005 [P] Criar `docker-compose.yml` na raiz com serviços `api` (porta 3000, volume `./data:/app/data`) e `n8n` (porta 5678, volume `./n8n/data:/home/node/.n8n`, env N8N_BASIC_AUTH)
- [x] T006 [P] Criar `.env.example` na raiz com variáveis `PORT=3000`, `DB_PATH=/app/data/clinica.db` (caminho dentro do container Docker — o volume `./data:/app/data` mapeia o host), `OPENAI_API_KEY=`; adicionar comentário no arquivo explicando o caminho do container
- [x] T007 [P] Criar `data/.gitkeep` e adicionar `data/clinica.db` ao `.gitignore`

**Checkpoint**: Estrutura criada — `docker compose build` deve concluir sem erros.

---

## Phase 2: Foundational

**Objetivo**: Banco de dados, app Express e infraestrutura compartilhada que TODAS as user stories dependem.

**⚠️ CRÍTICO**: Nenhuma user story pode ser implementada antes desta fase estar completa.

- [x] T008 Criar `api/src/db/schema.sql` com DDL das 5 tabelas: `medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos` conforme `specs/001-n8n-medical-scheduling/data-model.md`
- [x] T009 Implementar `api/src/db/connection.js`: singleton `better-sqlite3` que lê `DB_PATH` do env, executa `schema.sql` na inicialização e exporta a instância `db`
- [x] T010 Implementar `api/src/db/seed.js`: verifica se `medicos` está vazio; se sim, insere 3 médicos (Clínico Geral, Cardiologista, Dermatologista), 5 pacientes com email/telefone fictícios, 10 horários nos próximos 7 dias (`disponivel=1`), 2 agendamentos pré-confirmados e 1 registro de pagamento conforme `data-model.md`
- [x] T011 [P] Implementar `api/src/middlewares/errorHandler.js`: middleware Express que captura erros e retorna `{ "error": "<mensagem>" }` com status adequado
- [x] T012 [P] Implementar `api/src/cache/index.js`: instância `node-cache` com TTL padrão 60s; exportar funções `get(key)`, `set(key, value, ttl?)`, `del(key)` e `delByPrefix(prefix)`
- [x] T013 Implementar `api/src/middlewares/requestLogger.js`: middleware Express com `pino` (instalar via `npm install pino`) que emite log JSON em toda requisição com campos `correlation_id` (lido de `X-Request-ID` header ou gerado via `crypto.randomUUID()`), `timestamp`, `method`, `path`, `status_code` e `duration_ms`; conforme Constitution Principle IV
- [x] T014 Implementar `api/src/app.js`: criar app Express, registrar `express.json()`, `requestLogger` (T013), todas as rotas (horarios, agendamentos, pacientes, pagamentos, painel) e `errorHandler`
- [x] T015 Implementar `api/src/server.js`: importar `app`, importar e rodar `seed()`, iniciar `app.listen(PORT)`

**Checkpoint**: `docker compose up api` deve subir sem crash; `GET http://localhost:3000/` pode retornar 404 (sem rota raiz) mas sem erro de processo. Logs JSON estruturados devem aparecer no `docker compose logs api`.

---

## Phase 3: US1 — Consultar Horários Disponíveis (P1) 🎯 MVP

**Objetivo**: Paciente consegue listar horários disponíveis via API, com cache.

**Independent Test**: `GET http://localhost:3000/horarios/disponiveis` retorna array JSON com médico, data_hora e disponivel=1; segunda chamada é servida do cache (header ou log confirma).

### Testes (TDD — escrever ANTES e verificar que FALHAM)

- [x] T016 [P] [US1] Escrever testes Jest em `api/tests/horarios.test.js`: (a) GET sem filtro retorna array com objetos `{id, data_hora, disponivel, medico}`; (b) GET com `?data=YYYY-MM-DD` retorna somente horários daquela data; (c) GET com data sem horários retorna `[]`; garantir que os testes falham antes de implementar a rota

### Implementação

- [x] T017 [US1] Implementar `api/src/routes/horarios.js`: `GET /horarios/disponiveis` — query SQLite JOIN `horarios` + `medicos` WHERE `disponivel=1` (e filtro `date()` se `?data` presente); aplicar cache com chave `"horarios"` ou `"horarios:YYYY-MM-DD"`; retornar array formatado conforme contrato em `contracts/api-contracts.md`
- [x] T018 [US1] Registrar rota `horarios` em `api/src/app.js` e verificar que `npm test` passa para `horarios.test.js`

**Checkpoint**: US1 funcional e testável de forma independente — `GET /horarios/disponiveis` retorna dados reais do seed.

---

## Phase 4: US2 — Realizar Agendamento (P1) 🎯 MVP

**Objetivo**: Paciente consegue criar agendamento via API identificado pelo e-mail; slot é marcado como indisponível; cache invalidado.

**Independent Test**: `POST /agendamentos` com `{ paciente_email, horario_id }` retorna 201 com objeto de agendamento; `GET /horarios/disponiveis` não lista mais o horário agendado; e-mail de confirmação é enviado (testado via Flow D do N8N mais adiante).

### Testes (TDD — escrever ANTES e verificar que FALHAM)

- [x] T019 [P] [US2] Escrever testes Jest em `api/tests/pacientes.test.js`: (a) GET `/pacientes/:email` com email existente retorna 200 com `{id, nome, email, telefone}`; (b) GET com email inexistente retorna 404 `"Paciente não encontrado"`; garantir que os testes falham antes de implementar
- [x] T020 [P] [US2] Escrever testes Jest em `api/tests/agendamentos.test.js`: (a) POST com `paciente_email` e `horario_id` válidos retorna 201 com `status: "ativo"`; (b) POST com e-mail inexistente retorna 404 `"Paciente não encontrado"`; (c) POST com horário já ocupado retorna 409 `"Horário não está mais disponível"`; (d) GET `/agendamentos/:id` retorna objeto completo; garantir que os testes falham antes de implementar

### Implementação

- [x] T021 [US2] Implementar `GET /pacientes/:email` em `api/src/routes/pacientes.js`: query `WHERE email = ?`; retornar 404 `{ "error": "Paciente não encontrado" }` se não existir
- [x] T022 [US2] Implementar `POST /agendamentos` em `api/src/routes/agendamentos.js`: (1) buscar paciente por email → 404 se não encontrado; (2) verificar `horarios.disponivel = 1` → 409 se ocupado; (3) em transação: INSERT agendamentos + UPDATE horarios SET disponivel=0; (4) invalidar cache `"horarios"` e `"horarios:*"`; (5) retornar 201 com objeto conforme contrato
- [x] T023 [US2] Implementar `GET /agendamentos/:id` em `api/src/routes/agendamentos.js`: query JOIN `agendamentos + pacientes + horarios + medicos`; retornar 404 se não encontrado
- [x] T024 [US2] Registrar rotas `agendamentos` e `pacientes` em `api/src/app.js` e verificar que `npm test` passa para `pacientes.test.js` e `agendamentos.test.js`

**Checkpoint**: US1 + US2 funcionais e independentemente testáveis — MVP da API completo.

---

## Phase 5: US3 — Cancelar Agendamento (P2)

**Objetivo**: Paciente consegue cancelar agendamento; status atualizado para "cancelado"; slot liberado; cache invalidado.

**Independent Test**: `PATCH /agendamentos/2/cancelar` retorna 200 com `{ id: 2, status: "cancelado" }`; `GET /horarios/disponiveis` volta a listar o horário liberado.

### Testes (TDD — escrever ANTES e verificar que FALHAM)

- [x] T025 [P] [US3] Adicionar testes de cancelamento em `api/tests/agendamentos.test.js`: (a) PATCH `/:id/cancelar` com agendamento ativo retorna 200 `{ id, status: "cancelado" }`; (b) PATCH com ID inexistente retorna 404; (c) PATCH em agendamento já cancelado retorna 400 `"Agendamento já está cancelado"`; garantir que falham antes de implementar

### Implementação

- [x] T026 [US3] Implementar `PATCH /agendamentos/:id/cancelar` em `api/src/routes/agendamentos.js`: (1) verificar existência → 404 se não encontrado; (2) verificar status ≠ `"cancelado"` → 400 se já cancelado; (3) em transação: UPDATE `agendamentos SET status="cancelado"` + UPDATE `horarios SET disponivel=1`; (4) invalidar cache; (5) retornar 200 `{ id, status: "cancelado" }`
- [x] T027 [US3] Verificar que todos os testes de `agendamentos.test.js` (POST + GET + PATCH) passam

**Checkpoint**: US3 funcional — ciclo completo de agendamento e cancelamento via API testado.

---

## Phase 6: US4 — Consultar Valores e Pagamentos (P2)

**Objetivo**: Paciente consegue obter informações de valores e formas de pagamento.

**Independent Test**: `GET /pagamentos` retorna array com `{ descricao, valor, formas }` populado pelo seed.

### Testes (TDD — escrever ANTES e verificar que FALHAM)

- [x] T028 [P] [US4] Escrever testes Jest em `api/tests/pagamentos.test.js`: (a) GET retorna array não-vazio; (b) cada item tem `descricao`, `valor` (number) e `formas` (array); garantir que falham antes de implementar

### Implementação

- [x] T029 [US4] Implementar `GET /pagamentos` em `api/src/routes/pagamentos.js`: query `SELECT * FROM pagamentos`; fazer `JSON.parse(item.formas)` para deserializar o array; retornar array formatado
- [x] T030 [US4] Registrar rota `pagamentos` em `api/src/app.js` e verificar que `npm test` passa para `pagamentos.test.js`

**Checkpoint**: US1 + US2 + US3 + US4 funcionais — API completa para todos os fluxos de texto. `npm test` passa todos os 4 arquivos de teste (horarios, pacientes, agendamentos, pagamentos).

---

## Phase 7: Painel de Visualização (Diferencial)

**Objetivo**: Endpoint HTML com tabela de todos os agendamentos para facilitar validação manual durante avaliação.

- [x] T031 Implementar `GET /painel` em `api/src/routes/painel.js`: query JOIN `agendamentos + pacientes + horarios + medicos` ORDER BY `data_hora`; retornar HTML com tabela contendo ID, paciente, médico, data_hora, status (colorido: verde para ativo, vermelho para cancelado) e criado_em
- [x] T032 Registrar rota `painel` em `api/src/app.js`

**Checkpoint**: `http://localhost:3000/painel` exibe tabela HTML com os 2 agendamentos pré-confirmados do seed.

---

## Phase 8: N8N — Fluxos Core (US1, US2, US3, US4, US6)

**Objetivo**: Fluxos N8N que atendem os intents de texto via GPT-4o-mini com function calling.

**Pré-requisito**: API completa e rodando (`docker compose up api`).

- [x] T033 Criar `n8n/flow-d-email.json`: sub-workflow com `Execute Workflow Trigger` → Switch por tipo (`agendamento`|`cancelamento`) → Set com template de e-mail → Gmail node (OAuth2, configurado em Settings → Credentials) com retry nativo 3x intervalo 5s; templates conforme `contracts/n8n-function-tools.md`; importar e ativar no N8N antes do flow-b
- [x] T034 [P] Criar `n8n/flow-b-ai-core.json`: Set histórico de mensagens → OpenAI Chat node (GPT-4o-mini) com system prompt e 5 function definitions (`buscar_horarios_disponiveis`, `criar_agendamento`, `cancelar_agendamento`, `buscar_pagamentos`, `buscar_paciente`) conforme `contracts/n8n-function-tools.md` → Switch por function chamada → HTTP Request nodes para cada endpoint da API (`API_BASE_URL` via env N8N) → após `criar_agendamento` e `cancelar_agendamento` chamar `flow-d-email` → Respond to Webhook; nomes de todos os nodes em português descritivo (ex: "Buscar Horários na API"); importar e ativar
- [x] T035 Criar `n8n/flow-a-entrada.json`: Chat Trigger (webhook `/webhook/chat`) → IF `type === "audio"` → SIM: executar flow-c | NÃO: executar flow-b; node Error Trigger para capturar falhas; importar e ativar; anotar URL do webhook
- [ ] T036 Testar manualmente os 5 intents de texto via `curl` conforme `quickstart.md` (passo 6): horários disponíveis, agendamento (com e-mail de paciente do seed), cancelamento, pagamento e saudação; verificar respostas e e-mails recebidos

**Checkpoint**: US1, US2, US3, US4 e US6 funcionais via chat de texto; e-mails de confirmação enviados para agendamento e cancelamento. Tirar screenshots para `docs/prints/`.

---

## Phase 9: N8N — Fluxo de Áudio (US5)

**Objetivo**: Paciente pode enviar áudio e receber resposta em áudio (.mp3).

**Pré-requisito**: flow-b-ai-core ativo e credencial OpenAI configurada no N8N.

- [x] T037 Criar `n8n/flow-c-audio.json`: recebe binário do Chat Trigger → HTTP POST OpenAI `/audio/transcriptions` (whisper-1) → Set injeta transcrição como texto → Executa flow-b → HTTP POST OpenAI `/audio/speech` (tts-1, voz `alloy`) com retry nativo 3x intervalo 3s → Respond com arquivo `.mp3`; se TTS falhar em todas as tentativas retornar resposta texto do flow-b com aviso ao paciente; importar e ativar
- [ ] T038 Testar manualmente envio de áudio conforme `quickstart.md` (passo 7); verificar que resposta contém arquivo .mp3 reproduzível; testar fallback simulando falha do TTS

**Checkpoint**: US5 funcional — áudio entra, áudio sai. Fallback para texto funciona. Tirar screenshot/gravação para evidência.

---

## Phase 10: Polish & Entregáveis Obrigatórios

**Objetivo**: Documentação, coleção Postman, GIF demonstrativo, evidências e organização final.

- [x] T039 Criar `postman/clinica.collection.json`: coleção com todas as rotas da API (`GET /horarios/disponiveis`, `GET /horarios/disponiveis?data=`, `POST /agendamentos`, `PATCH /agendamentos/:id/cancelar`, `GET /agendamentos/:id`, `GET /pacientes/:email`, `GET /pagamentos`, `GET /painel`); incluir variável `BASE_URL`; exemplos de body e response esperada para cada endpoint
- [x] T040 Criar `README.md` na raiz com: pré-requisitos, instruções de instalação passo a passo, configuração de variáveis de ambiente, configuração do N8N (OAuth2 Gmail + importação dos 4 flows em ordem D→B→A→C), como rodar os testes (`npm test`), exemplos de uso via curl, link para o painel (`/painel`); estrutura conforme seção 10 do `docs/initial_plan.md`
- [x] T041 Criar `CHECKLIST.md` na raiz com tabela de 7 cenários: (1) consultar horários disponíveis, (2) agendar consulta, (3) cancelar agendamento, (4) consultar pagamentos, (5) entrada por áudio, (6) horário já ocupado, (7) paciente não encontrado; colunas: #, Cenário, Input, Esperado, Resultado, Status; preencher com evidências (prints/curl output) de cada teste manual executado
- [ ] T042 [P] Adicionar screenshots em `docs/prints/`: N8N flows ativados, e-mail de confirmação recebido, resposta de áudio reproduzindo, painel HTML com agendamentos, curl de cada intent respondendo corretamente
- [ ] T043 [P] Gravar `docs/demo.gif` (ou `demo.mp4`): vídeo/GIF demonstrando os 4 fluxos principais — consulta de horários, agendamento com e-mail, cancelamento com e-mail e resposta em áudio; ferramenta sugerida: LICEcap (GIF) ou OBS (vídeo)
- [x] T044 [P] Executar suite completa de testes unitários (`npm test` em `api/`) e confirmar que todos os 4 arquivos passam; corrigir eventuais falhas antes da entrega
- [ ] T045 [P] Rodar `docker compose down -v && docker compose up --build` do zero e executar todos os 7 cenários do CHECKLIST.md para validação final end-to-end; marcar cada cenário como ✅ no CHECKLIST.md

---

## Dependências e Ordem de Execução

### Dependências entre Fases

- **Setup (Phase 1)**: Sem dependências — pode iniciar imediatamente
- **Foundational (Phase 2)**: Depende de Setup — **bloqueia todas as user stories**
- **US1 (Phase 3)**: Depende de Foundational — sem dependência de outras stories
- **US2 (Phase 4)**: Depende de Foundational — sem dependência de US1 (mas US1 deve estar completa para MVP útil)
- **US3 (Phase 5)**: Depende de US2 (reutiliza rota de agendamentos)
- **US4 (Phase 6)**: Depende de Foundational — independente de US1/US2/US3
- **Painel (Phase 7)**: Depende de US2 + US3 (exibe agendamentos)
- **N8N Core (Phase 8)**: Depende de US1 + US2 + US3 + US4 estarem implementadas e API rodando
- **N8N Áudio (Phase 9)**: Depende de N8N Core (flow-b deve estar ativo)
- **Polish (Phase 10)**: Depende de todos os flows N8N ativos

### Dependências entre User Stories

- **US1 (P1)**: Independente após Foundational
- **US2 (P1)**: Independente após Foundational (não depende de US1)
- **US3 (P2)**: Depende de US2 (usa mesma tabela e rota de agendamentos)
- **US4 (P2)**: Independente após Foundational
- **US5 (P3)**: Depende de N8N Core (flow-b) estar ativo
- **US6 (P3)**: Incluída em flow-b-ai-core (T032) — sem fase separada

### Dentro de Cada User Story

- Testes DEVEM ser escritos e FALHAR antes da implementação (Constitution Principle III)
- Modelos/queries antes de rotas
- Rotas antes de cache e invalidação
- API completa antes dos flows N8N

### Oportunidades de Paralelismo

- Tarefas marcadas `[P]` dentro de cada fase podem ser executadas em paralelo
- Após Foundational: US1, US2 e US4 podem ser iniciadas em paralelo
- T033 (flow-d-email) e T034 (flow-b-ai-core) podem ser criados em paralelo
- T039 (Postman), T042 (prints), T043 (GIF), T044 (npm test) podem rodar em paralelo na fase final

---

## Exemplo de Execução Paralela — Phase 4 (US2)

```bash
# Escrever testes primeiro — em paralelo pois são arquivos diferentes (T019 + T020):
Test file: "api/tests/pacientes.test.js"      # T019 — GET /pacientes/:email
Test file: "api/tests/agendamentos.test.js"   # T020 — POST /agendamentos + GET /:id

# Confirmar que FALHAM:
cd api && npm test  # deve mostrar falhas em pacientes.test.js e agendamentos.test.js

# Após testes falhando — implementar em paralelo (T021 + T022 são arquivos diferentes):
Task: "GET /pacientes/:email em api/src/routes/pacientes.js"    # T021
Task: "POST /agendamentos em api/src/routes/agendamentos.js"    # T022
```

---

## Estratégia de Implementação

### MVP da API (Phases 1–6) — Entregável Mínimo

1. Phase 1: Setup do projeto (T001–T007)
2. Phase 2: Banco de dados + Express + log estruturado (T008–T015) ← CRÍTICO
3. Phase 3: US1 → Horários disponíveis com cache (T016–T018) ✅ Testar independentemente
4. Phase 4: US2 → Agendamento (T019–T024) ✅ Testar independentemente
5. Phase 5: US3 → Cancelamento (T025–T027) ✅ Testar independentemente
6. Phase 6: US4 → Pagamentos (T028–T030) ✅ **API completa — `npm test` 4 arquivos passando**

### Entrega Completa com N8N (Phases 7–10)

7. Phase 7: Painel HTML diferencial (T031–T032)
8. Phase 8: N8N Core (flows D→B→A) → chat de texto + e-mails (T033–T036)
9. Phase 9: N8N Áudio (flow C) → áudio entrada + saída (T037–T038)
10. Phase 10: Polish → README, CHECKLIST, Postman, GIF demo, evidências (T039–T045)

---

## Notas

- `[P]` = arquivos diferentes, sem dependências entre si
- `[USn]` = rastreabilidade para a user story correspondente
- Cada checkpoint valida a story de forma independente antes de avançar
- Constitution Principle III: testes DEVEM falhar antes de qualquer implementação
- Commitar após cada fase (Conventional Commits: `feat:`, `test:`, `docs:`)
- Parar em qualquer checkpoint para validar antes de prosseguir
