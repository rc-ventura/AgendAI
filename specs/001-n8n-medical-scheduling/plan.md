# Implementation Plan: N8N Medical Scheduling Automation

**Branch**: `001-n8n-medical-scheduling` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-n8n-medical-scheduling/spec.md`

## Summary

Construir um sistema de atendimento médico automatizado composto por: (a) API REST em
Node.js + Express com banco SQLite que gerencia médicos, pacientes, horários,
agendamentos e pagamentos fictícios; (b) 4 fluxos N8N que orquestram a inteligência —
detectam modalidade (texto/áudio), classificam intenção via GPT-4o-mini com function
calling, chamam a API REST e retornam resposta em texto ou áudio sintetizado; (c)
integração com Gmail API via node nativo do N8N para e-mails transacionais; e (d)
OpenAI TTS + Whisper para síntese e transcrição de áudio. Todos os componentes sobem
com um único `docker compose up`.

## Technical Context

**Language/Version**: Node.js 20 LTS + Express 4 (API REST). N8N roda como serviço
Docker.

**Primary Dependencies**:
- API: `express`, `better-sqlite3` (síncrono, sem driver externo), `node-cache`
  (cache TTL), `jest` + `supertest` (testes), `nodemon` (dev)
- Workflow: N8N self-hosted (Docker `n8nio/n8n`), OpenAI Chat node (GPT-4o-mini),
  HTTP Request nodes, Gmail node (OAuth2 nativo N8N), N8N Chat Trigger
- Tooling: Docker Compose, `.env` para segredos

**Storage**: SQLite via `better-sqlite3` (operações síncronas — adequado para carga
de demo). Arquivo: `api/data/clinica.db`. Schema e seed rodados na inicialização da
API se o banco estiver vazio.

**Testing**: Jest + Supertest. Banco in-memory (`:memory:`) para testes unitários de
rota. Três arquivos de teste cobrindo horários, agendamentos e pagamentos.

**Target Platform**: Container Linux via Docker Compose. Funciona em qualquer máquina
com Docker ≥ 24 e Docker Compose v2.

**Project Type**: Web service (REST API) + fluxos de automação N8N + Docker Compose.

**Performance Goals**: Resposta da API P95 < 500 ms. Consulta de disponibilidade
end-to-end < 5 s. Fluxo de agendamento completo < 30 s. Round-trip de áudio < 60 s.

**Constraints**: SQLite single-node (sem DB externo). Áudio como arquivo binário via
Chat Trigger do N8N. Credenciais Gmail configuradas no N8N (não na API). Todos os
segredos via `.env` (nunca commitado).

**Scale/Scope**: Demo de avaliação — até 10 usuários simultâneos simulados, 3 médicos,
5 pacientes, 10 horários pré-populados nos próximos 7 dias.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Gate | Status | Notas |
|-----------|------|--------|-------|
| I. AI-Assisted by Default | GPT-4o-mini com function calling; todas as respostas de dados fluem pela API (sem alucinação); erros de IA logados com correlation ID | ✅ PASS | N8N OpenAI Chat node + 5 functions mapeadas para endpoints REST |
| II. User-Centric Scheduling | Todas as intenções acessíveis em ≤ 1 turno de chat; fallback para texto preserva acessibilidade no fluxo de áudio | ✅ PASS | Chat-first UX; rota de áudio degrada graciosamente |
| III. Test-First | Testes Jest escritos e falhando antes da implementação; Red-Green-Refactor aplicado em cada rota | ✅ PASS | tasks.md vai enforçar ordenação test-first |
| IV. Observability & Reliability | Log JSON em toda requisição da API; retry no node Gmail (3x, 5s) e no HTTP Request TTS (3x, 3s); P95 < 500 ms | ✅ PASS | Retry gerenciado no N8N; `morgan` ou middleware próprio na API |
| V. Simplicity | `better-sqlite3` síncrono sem ORM; Express sem framework adicional; `node-cache` in-process; sem camada de repositório | ✅ PASS | Complexidade mínima compatível com os requisitos do desafio |

**Re-check pós-Phase 1**: ✅ Todos os gates passam após o design. Nenhuma entrada na
Complexity Tracking é necessária.

## Project Structure

### Documentation (this feature)

```text
specs/001-n8n-medical-scheduling/
├── plan.md              # Este arquivo
├── research.md          # Saída da Phase 0
├── data-model.md        # Saída da Phase 1
├── quickstart.md        # Saída da Phase 1
├── contracts/           # Saída da Phase 1
│   ├── api-contracts.md
│   └── n8n-function-tools.md
└── tasks.md             # Saída da Phase 2 (/speckit-tasks — não criado aqui)
```

### Source Code (repository root)

```text
api/
├── src/
│   ├── app.js                  # Express setup, middlewares, rotas
│   ├── server.js               # Inicialização, seed condicional
│   ├── db/
│   │   ├── connection.js       # Singleton better-sqlite3
│   │   ├── schema.sql          # DDL das 5 tabelas
│   │   └── seed.js             # Popula banco se estiver vazio
│   ├── routes/
│   │   ├── horarios.js         # GET /horarios/disponiveis
│   │   ├── agendamentos.js     # POST /agendamentos, PATCH /:id/cancelar, GET /:id
│   │   ├── pacientes.js        # GET /pacientes/:email
│   │   ├── pagamentos.js       # GET /pagamentos
│   │   └── painel.js           # GET /painel (HTML dashboard — diferencial)
│   ├── cache/
│   │   └── index.js            # node-cache, TTL 60s, helpers get/set/del
│   └── middlewares/
│       └── errorHandler.js
├── tests/
│   ├── horarios.test.js
│   ├── agendamentos.test.js
│   └── pagamentos.test.js
├── Dockerfile
└── package.json

n8n/
├── flow-a-entrada.json         # Detecção texto|áudio → roteia para B ou C
├── flow-b-ai-core.json         # LLM + function calling + chamadas à API
├── flow-c-audio.json           # Whisper STT → Flow B → TTS
└── flow-d-email.json           # Sub-workflow de e-mail Gmail (reutilizado por B e C)

postman/
└── clinica.collection.json

docs/
├── prints/                     # Evidências de teste (screenshots)
└── demo.gif                    # GIF demonstrando os 4 fluxos

data/
└── .gitkeep                    # clinica.db criado em runtime (gitignored)

docker-compose.yml
.env.example
README.md
CHECKLIST.md
```

**Structure Decision**: `api/` e `n8n/` são componentes independentes com suas próprias
responsabilidades. Os 4 fluxos N8N são exportados como arquivos JSON separados para
facilitar importação incremental (A→B→C→D). `data/` mantém o SQLite em volume Docker
gitignored. `docs/prints/` e `docs/demo.gif` são entregáveis obrigatórios do desafio.
