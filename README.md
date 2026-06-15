# AgendAI — Automação de Atendimento Médico com IA

Sistema de agendamento médico automatizado com agente LangGraph, GPT-4o-mini, API REST Node.js, Postgres e suporte a texto e áudio.

![CI](https://github.com/rc-ventura/AgendAI/actions/workflows/ci.yml/badge.svg)

---

## Quickstart

> Variáveis obrigatórias: `OPENAI_API_KEY`, `DATABASE_URL`, `DATABASE_URI`, `REDIS_URI`, `LANGSMITH_API_KEY`. Veja `.env.example`.

```bash
git clone https://github.com/rc-ventura/AgendAI.git
cd AgendAI
cp .env.example .env
# Edite .env e preencha as variáveis obrigatórias
docker compose up --build -d
```

Aguarde o build (~3 min na primeira vez) e acesse:

| Serviço | URL |
| --- | --- |
| Chat UI + Agente | http://localhost:8080 |
| Painel de agendamentos | http://localhost:8080/painel (via API interna) |

> Apenas nginx expõe porta pública (8080). API e LangGraph Server são internos à rede Docker.

Verifique se está no ar:

```bash
docker compose ps
curl -H "x-api-key: $LANGGRAPH_AUTH_TOKEN" http://localhost:8080/info
```

---

## Demonstração

### Tela inicial do chat

![Tela inicial](docs/prints/chat-ui-tela-inicial.png)

### Consulta de formas de pagamento

![Formas de pagamento](docs/prints/chat-formas-pagamento.png)

### E-mail de confirmação de agendamento

![Email de confirmação](docs/prints/email-confirmacao-agendamento.png)

### E-mail de cancelamento

![Email de cancelamento](docs/prints/email-cancelamento-consulta.png)

### Painel HTML de agendamentos (`GET /painel`)

![Painel de agendamentos](docs/prints/painel-agendamentos.png)

### Erros da API (Postman)

![404 Paciente não encontrado](docs/prints/postman-404-paciente-nao-encontrado.png)

![409 Horário indisponível](docs/prints/postman-409-horario-indisponivel.png)

### Testes passando

![API — 39 testes Jest](docs/prints/api-testes-39-passando.png)

![Agente — 70 testes pytest](docs/prints/agente-testes-70-passando.png)

### Grafo do agente (LangGraph Studio)

![LangGraph Studio](docs/prints/langgraph_studio.png)

### Gravações de tela

| Fluxo | Arquivo |
| --- | --- |
| Consulta de horários disponíveis | [demo-consulta-horarios.mov](docs/prints/demo-consulta-horarios.mov) |
| Fluxo de áudio (upload + resposta) | [demo-fluxo-audio.mov](docs/prints/demo-fluxo-audio.mov) |
| Agendamento via chat | [demo-agendamento-chat.mov](docs/prints/demo-agendamento-chat.mov) |
| Cancelamento via chat | [demo-cancelamento-chat.mov](docs/prints/demo-cancelamento-chat.mov) |

---

## Stack

| Componente | Tecnologia | Porta |
| --- | --- | --- |
| API REST | Node.js 20 + Express 4 + Postgres (`pg`) | 3000 (interno) |
| LangGraph Server | `langchain/langgraph-server` (imagem oficial) | 8123 (interno) |
| Agente | Python 3.11 + LangGraph v1.0+ + GPT-4o-mini | — |
| Chat UI | Next.js 14 + shadcn/ui + `@langchain/langgraph-sdk` | 3002 (interno) |
| Proxy | nginx (único ponto público) | **8080** |
| Banco (API) | Postgres — Neon (prod) / `postgres:16` (dev) | 5432 (interno) |
| Banco (Agent) | Postgres — Neon `agendai_lg` (threads/checkpoints) | — |
| Fila SSE | Redis — Upstash (prod) / `redis:7` (dev) | 6379 (interno) |
| LLM | GPT-4o-mini (tool calling) | — |
| STT | OpenAI Whisper (`whisper-1`) | — |
| TTS | OpenAI TTS (`tts-1`, voz `alloy`) | — |
| E-mail | Resend HTTP API + tenacity (retry 3x) | — |
| Observabilidade | LangSmith (Developer plan) | — |
| CI/CD | GitHub Actions → GHCR → Render | — |

---

## Fluxos suportados

| Fluxo | O que enviar no chat | Resultado |
| --- | --- | --- |
| Horários disponíveis | `"Quais horários vocês têm?"` | Lista com médico, data e hora |
| Agendar consulta | `"Agendar para joao@email.com no horário 3"` | Confirmação + e-mail ao paciente |
| Cancelar consulta | `"Cancelar minha consulta 1"` | Confirmação de cancelamento + e-mail |
| Valores e pagamento | `"Quanto custa a consulta?"` | Preço em R$ + formas aceitas |
| Entrada por áudio | Clique 🎙 ou 📎 e envie um `.mp3` | Whisper transcreve → agente responde |

---

## Variáveis de ambiente

Todas as variáveis estão documentadas no `.env.example`.

| Variável | Obrigatório | Descrição |
| --- | --- | --- |
| `OPENAI_API_KEY` | **Sim** | GPT-4o-mini, Whisper e TTS |
| `DATABASE_URL` | **Sim** | Postgres para a API (`agendai`) — ex: `postgres://...@neon.tech/agendai?sslmode=require` |
| `DATABASE_URI` | **Sim** | Postgres para o LangGraph Server (`agendai_lg`) |
| `REDIS_URI` | **Sim** | Redis para streaming SSE — ex: `rediss://default:xxx@upstash.io:6379` |
| `LANGSMITH_API_KEY` | **Sim** | Licença do LangGraph Server + tracing (Developer plan) |
| `LANGGRAPH_AUTH_TOKEN` | **Sim** | Token compartilhado: nginx `x-api-key` ↔ UI `NEXT_PUBLIC_LANGGRAPH_API_KEY` |
| `API_BASE_URL` | **Sim** | URL interna da API (agente → api). Default: `http://api:3000` |
| `RESEND_API_KEY` | Não | API key do Resend para envio de e-mails de confirmação |
| `EMAIL_FROM` | Não | Remetente dos e-mails. Default: `AgendAI <onboarding@resend.dev>` |
| `LANGSMITH_TRACING` | Não | `true` para habilitar traces no LangSmith |
| `LANGSMITH_PROJECT` | Não | Nome do projeto no LangSmith. Default: `AgendAI` |
| `PORT` | Não | Porta da API. Default: `3000` |

> `LANGSMITH_API_KEY` serve para os dois papéis: licença do servidor e tracing.

### Configurar e-mail com Resend (opcional)

1. Crie conta em [resend.com](https://resend.com) (3.000 e-mails/mês grátis)
2. Crie uma API key em **API Keys**
3. No `.env`: `RESEND_API_KEY=re_xxx` e `EMAIL_FROM=AgendAI <contato@seudominio.com>`

> O sistema funciona sem e-mail configurado — a confirmação é exibida apenas no chat.

---

## Testes

**API REST** (39 testes Jest — Postgres real, sem mock):

```bash
export DATABASE_URL=postgres://agendai:agendai@localhost:5433/agendai_test
cd api && npm install && npm test
```

**Agente Python** (70 testes — nodes, tools, grafo, roteamento, estado):

```bash
cd agent && uv run pytest --tb=short
```

O CI roda ambas as suites em cada push/PR via GitHub Actions (`.github/workflows/ci.yml`). Deploy automático para o Render só ocorre se os testes passarem.

---

## API REST — Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/horarios/disponiveis` | Lista horários com dados do médico (cache TTL 60s) |
| GET | `/horarios/disponiveis?data=YYYY-MM-DD` | Filtra por data |
| POST | `/agendamentos` | Cria agendamento e invalida cache |
| PATCH | `/agendamentos/:id/cancelar` | Cancela agendamento e invalida cache |
| GET | `/agendamentos/:id` | Detalhe de um agendamento |
| GET | `/pacientes/:email` | Busca paciente por e-mail |
| GET | `/pagamentos` | Valores e formas de pagamento |
| GET | `/painel` | Painel HTML com todos os agendamentos |

Importe a coleção Postman em `postman/clinica.collection.json` e configure `BASE_URL=http://localhost:3000`.

---

## Banco de dados

**Postgres** — Neon em produção; `postgres:16` container em dev.

| Banco | Usado por | Env var |
| --- | --- | --- |
| `agendai` | API REST (médicos, pacientes, horários, agendamentos, pagamentos) | `DATABASE_URL` |
| `agendai_lg` | LangGraph Server (threads, checkpoints, runs) | `DATABASE_URI` |

Seed executado automaticamente no boot (count-guard — não duplica):

| Paciente | E-mail | Telefone |
| --- | --- | --- |
| João Silva | joao@email.com | 11999990001 |
| Maria Santos | maria@email.com | 11999990002 |
| Pedro Oliveira | pedro@email.com | 11999990003 |
| Ana Ferreira | ana@email.com | 11999990004 |
| Lucas Pereira | lucas@email.com | 11999990005 |

3 médicos (Clínico Geral, Cardiologista, Dermatologista) · 10 horários nos próximos 7 dias.

Resetar banco:

```bash
docker compose down -v && docker compose up --build -d
```

---

## Arquitetura do agente

```
START → detect_input_type
          ├─ (texto) → chat_with_llm ⇄ execute_tools → process_tool_results
          │                                                  ├─ send_email
          │                                                  └─ END
          └─ (áudio) → transcribe_audio → chat_with_llm → synthesize_tts → END
```

| Nó | Arquivo | Função |
| --- | --- | --- |
| `detect_input_type` | `agent/nodes/input_detector.py` | Roteia texto vs. áudio |
| `transcribe_audio` | `agent/nodes/transcriber.py` | Whisper STT |
| `chat_with_llm` | `agent/nodes/llm_core.py` | GPT-4o-mini com 6 tools |
| `execute_tools` | `agent/nodes/tools.py` | Chama endpoints da API REST |
| `process_tool_results` | `agent/nodes/tool_result_processor.py` | Detecta agendamento/cancelamento e prepara e-mail |
| `send_email` | `agent/nodes/email_sender.py` | Resend HTTP API (retry 3x via tenacity) |
| `synthesize_tts` | `agent/nodes/tts.py` | OpenAI TTS voz alloy (retry 3x) |

O grafo é compilado **sem checkpointer** — o LangGraph Server injeta o checkpointer Postgres em runtime.

---

## CI/CD Pipeline

```
push → main
    │
    ├─ ci.yml: test-api (Postgres real) + test-agent (pytest)
    │               │ passou?
    │               ▼
    └─ deploy.yml: build imagens → push GHCR → 4 deploy hooks Render
                   api → langgraph → nginx → ui
```

Branch protection em `main` requer CI verde antes do merge.

---

## Produção (Render)

Deploy via `infra/render/render.yaml`. Providers gerenciados:

| Recurso | Provider | Plano |
| --- | --- | --- |
| Postgres API (`agendai`) | Neon | Free (0,5 GB) |
| Postgres Agent (`agendai_lg`) | Neon | Free (0,5 GB) |
| Redis SSE | Upstash | Free (10k cmd/dia) |
| LangSmith | LangSmith | Developer (5k traces/mês) |
| Deploy | Render | Free (4 serviços web) |

> No free tier do Render todos os serviços têm URL pública. nginx é o único ponto recomendado para o usuário — os demais são protegidos por `x-api-key`.

---

## Diferenciais implementados

| Diferencial | Detalhe |
| --- | --- |
| Testes API (39) | Jest + Supertest + Postgres real — 7 suites: rotas, cache, concorrência, validação |
| Testes agente (70) | pytest — nodes, grafo, roteamento, estado, tool result processor |
| Function calling | GPT-4o-mini com 6 ferramentas: horários, agendar, cancelar, pagamentos, paciente, detalhes |
| Retry e-mail | `tenacity` — 3 tentativas com backoff exponencial (Resend HTTP API) |
| Retry TTS | `tenacity` — 3 tentativas em `tts.py` |
| Persistência de threads | LangGraph Server com Postgres checkpointer (Neon) |
| Streaming SSE | Redis (Upstash) via LangGraph Server |
| Cache de disponibilidade | `node-cache` TTL 60s, invalidado em cada escrita |
| Painel de consultas | `GET /painel` — tabela HTML colorida por status |
| Arquitetura em camadas | `routes → controllers → services → repositories` com injeção de pool |
| Rate limiting | 100 req/15 min por IP via `express-rate-limit` |
| CI/CD | GitHub Actions → GHCR → Render (deploy automático com gate de testes) |

---

## Documentação técnica

### Decisões de arquitetura (ADRs)

| ADR | Decisão |
| --- | --- |
| [ADR-001](docs/adr/ADR-001-node-express.md) | Node.js + Express para a API REST |
| [ADR-002](docs/adr/ADR-002-sqlite-better-sqlite3.md) | SQLite com better-sqlite3 *(supersedido — migrado para Postgres na spec 004)* |
| [ADR-003](docs/adr/ADR-003-stateless-conversation.md) | Conversa stateless *(supersedido — LangGraph Server provê persistência na spec 004)* |
| [ADR-004](docs/adr/ADR-004-gpt-4o-mini.md) | GPT-4o-mini como LLM principal |
| [ADR-006](docs/adr/ADR-006-openai-whisper.md) | Whisper para transcrição de áudio |
| [ADR-007](docs/adr/ADR-007-openai-tts.md) | OpenAI TTS para síntese de voz |
| [ADR-012](docs/adr/ADR-012-apiclient-singleton-async.md) | API client singleton assíncrono |
| [ADR-013](docs/adr/ADR-013-langgraph-dev-server.md) | LangGraph dev server *(supersedido — LangGraph Server oficial na spec 004)* |
| [ADR-014](docs/adr/ADR-014-checkpointer-inmem.md) | Checkpointer in-memory *(supersedido — Postgres checkpointer via LangGraph Server)* |
| [ADR-015](docs/adr/ADR-015-langgraph-vs-n8n.md) | LangGraph vs N8N — justificativa da escolha |
| [ADR-016](docs/adr/ADR-016-nginx-reverse-proxy.md) | nginx como single edge reverse proxy |
| [ADR-017](docs/adr/ADR-017-api-security-tokens.md) | Segurança por tokens na API |
| [ADR-018](docs/adr/ADR-018-polyglot-node-python.md) | Stack poliglota Node.js + Python |
| [ADR-019](docs/adr/ADR-019-agent-ui.md) | Chat UI com Next.js |
| [ADR-020](docs/adr/ADR-020-docker-compose.md) | Docker Compose para infraestrutura local |
| [ADR-021](docs/adr/ADR-021-langsmith-observability.md) | LangSmith para observabilidade |
| [ADR-023](docs/adr/ADR-023-resend-email-api.md) | Resend HTTP API em vez de Gmail SMTP (bloqueado no Render free tier) |
| [ADR-024](docs/adr/ADR-024-retry-resilience-strategy.md) | Estratégia de retry e resiliência (tenacity + pybreaker) |

### Specs e planejamento

| Spec | Escopo | Status |
| --- | --- | --- |
| [001](specs/001-n8n-medical-scheduling/spec.md) | API REST + agendamento médico | ✅ Completo |
| [002](specs/002-langgraph-orchestration/spec.md) | Orquestração LangGraph + tools | ✅ Completo |
| [003](specs/003-professional-chat-ui/spec.md) | Chat UI profissional (Next.js + áudio) | ✅ Completo |
| [004](specs/004-fase-1-deploy/spec.md) | Deploy produção: Postgres, LangGraph Server, CI/CD, Render | ✅ Completo |
| [005](specs/005-agent-hardening/spec.md) | Agent Hardening: retry, guardrails, memória, HITL | 🔄 Em andamento |

### Checklist de testes e evidências

Ver [docs/CHECKLIST.md](docs/CHECKLIST.md) — cenários testados manualmente e via suite automatizada com referências a screenshots e gravações de tela.

---

## Troubleshooting

| Sintoma | Causa | Solução |
| --- | --- | --- |
| `connection refused` na porta 8080 | Container nginx não iniciou | `docker compose logs nginx` |
| `401 Unauthorized` ao chamar o agente | `LANGGRAPH_AUTH_TOKEN` ausente ou incorreto | Verificar `.env` e `NEXT_PUBLIC_LANGGRAPH_API_KEY` |
| Agente não responde | LangGraph Server falhou | `docker compose logs langgraph-server` |
| E-mails não chegam | `RESEND_API_KEY` não configurado | Adicionar no `.env` ou aceitar sem e-mail |
| Resposta de áudio retorna texto | TTS falhou | Verificar `OPENAI_API_KEY` e logs do agente |
| `409 Horário não disponível` | Horário já agendado | Usar ID de `GET /horarios/disponiveis` |
| `404 Paciente não encontrado` | E-mail não cadastrado | Usar e-mail da tabela seed acima |
| Serviço dorme no Render free | Cold start de 30–60s | Normal — primeira requisição acorda o serviço |
| `DATABASE_URL` inválida | Conexão Neon com SSL | Adicionar `?sslmode=require` na URL |
