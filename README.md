# AgendAI — Automação de Atendimento Médico com IA

Sistema de agendamento médico automatizado com agente LangGraph, GPT-4o-mini, API REST Node.js, suporte a texto e áudio, e roadmap de deploy em 3 fases até cloud production-grade.

---

## Quickstart

> Variáveis obrigatórias: `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `DATABASE_URL`, `DATABASE_URI` e `REDIS_URI`. Todas as outras já estão preenchidas no `.env.example` (Gmail é opcional).

```bash
git clone <url-do-repositorio>
cd AgendAI
cp .env.example .env
# Edite .env e preencha as variáveis obrigatórias
docker compose up --build -d
```

Aguarde o build (~2 min na primeira vez) e acesse:

| Serviço                | URL                          |
| ---------------------- | ---------------------------- |
| Chat UI                | http://localhost:8080        |
| Agente LangGraph       | http://localhost:8080/runs   |
| Painel de agendamentos | http://localhost:3000/painel |

Verifique se está no ar:

```bash
docker compose ps
curl http://localhost:3000/horarios/disponiveis
```

---

## Demonstração

### Tela inicial do chat

![Tela inicial](docs/prints/chat-ui-tela-inicial.png)

### Consulta de formas de pagamento

![Formas de pagamento](docs/prints/chat-formas-pagamento.png)

### E-mail de confirmação de agendamento (Gmail)

![Email de confirmação](docs/prints/email-confirmacao-agendamento.png)

### E-mail de cancelamento (Gmail)

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

| Fluxo                                | Arquivo                                                              |
| ------------------------------------ | -------------------------------------------------------------------- |
| Consulta de horários disponíveis    | [demo-consulta-horarios.mov](docs/prints/demo-consulta-horarios.mov) |
| Fluxo de áudio (upload + resposta)  | [demo-fluxo-audio.mov](docs/prints/demo-fluxo-audio.mov)             |
| Agendamento via chat                 | [demo-agendamento-chat.mov](docs/prints/demo-agendamento-chat.mov)   |
| Cancelamento via chat                | [demo-cancelamento-chat.mov](docs/prints/demo-cancelamento-chat.mov) |

---

## Stack

| Componente      | Tecnologia                            | Porta         |
| --------------- | ------------------------------------- | ------------- |
| API REST        | Node.js 20 + Express 4 + Postgres     | 3000 (intern) |
| Agente          | Python 3.11 + LangGraph v1.0+         | 8123 (intern) |
| LangGraph Server| langchain/langgraph-server (Docker)   | 8123 (intern) |
| Chat UI         | Next.js 14 + @langchain/langgraph-sdk | via nginx     |
| Proxy           | nginx (único ponto público)           | 8080          |
| Banco de dados  | PostgreSQL — Neon (prod) / pg:16 (dev)| —             |
| Cache / Stream  | Redis — Upstash (prod) / Redis (dev)  | —             |
| LLM             | GPT-4o-mini (tool calling)            | —             |
| STT             | OpenAI Whisper (whisper-1)            | —             |
| TTS             | OpenAI TTS (tts-1, voz alloy)         | —             |
| E-mail          | Gmail SMTP + tenacity (retry 3x)      | —             |
| Observabilidade | LangSmith (Developer plan)            | —             |

---

## Roadmap de Deploy

O projeto evolui em 3 fases — da prototipagem local até cloud production-grade com serviços gerenciados.

### Fase 1 — Render + GitHub Actions · semanas 1-2 · ~$7-15/mês

> Status atual

1. Migrar SQLite → Neon PostgreSQL (free tier)
2. Publicar 4 serviços: nginx público, api + agent como Private Services, agent-ui-pro público
3. GitHub Actions: tests gate → build → deploy
4. Mover secrets para GitHub Secrets + Render env vars
5. Badge CI verde no README + URL de produção
6. LangSmith já integrado — screenshot do dashboard de traces

### Fase 2 — Terraform + Cloud IaC · semanas 3-5

> Para portfólio: `terraform apply → screenshot → terraform destroy`

1. Criar `/infra/terraform` no repositório
2. GCP: Cloud Run × 3 + Cloud LB + URL Map + Cloud SQL + Memorystore Redis
3. AWS: ECS Fargate + ALB + RDS PostgreSQL + ElastiCache
4. Secret Manager / Secrets Manager (substituir `.env`)
5. Cloud Armor / AWS WAF para rate limiting gerenciado
6. `terraform apply → screenshot → terraform destroy`

### Fase 3 — Serviços Gerenciados (AWS + GCP)

> Substitui código manual por infraestrutura especializada sem trocar o LLM

| Componente     | Solução Gerenciada                       | Benefício                        |
| -------------- | ---------------------------------------- | -------------------------------- |
| Guardrails     | AWS Bedrock Guardrails (via ApplyGuardrail API) | Funciona com GPT-4o-mini    |
| Sessão         | Vertex AI Agent Engine Sessions (GA)     | HIPAA compliant, managed         |
| Memória longa  | Vertex AI Memory Bank (GA)               | Extração semântica via Gemini    |
| Rate limiting  | Cloud Armor / AWS WAF                    | Sem alterar código do app        |
| Autenticação   | Amazon Cognito / Firebase Auth           | Free tier até 50k MAU            |
| Observabilidade| LangSmith + Vertex AI Evaluation         | Quality gate automático no CI/CD |

**Custo estimado Fase 3:** GCP ~$58-80/mês + AWS ~$5-15/mês adicionais.

---

## Pipeline CI/CD

Nenhum código chega em produção sem os 109 testes passarem. Dois workflows separados:

```
ci.yml (pull request)
  push/PR → npm test (39 Jest) → uv run pytest (70 pytest) → ✓ PR liberado

deploy.yml (merge para main)
  merge → main → run tests → evaluate agent quality → build Docker → deploy Render → produção atualizada
```

```yaml
# .github/workflows/ci.yml (esqueleto)
name: CI
on: [push, pull_request]
jobs:
  test-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd api && npm ci && npm test
  test-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: cd agent && uv run pytest --tb=short
```

---

## Arquitetura em 8 Camadas

Cada camada mapeia a tecnologia atual → Render → Cloud (GCP/AWS) → Fase 3 (managed).

| Camada             | Local + Render                | Cloud (GCP/AWS)                     | Fase 3 (Managed)                  |
| ------------------ | ----------------------------- | ----------------------------------- | --------------------------------- |
| 01 Presentation    | Next.js 14 · porta 3002       | Cloud Run / ECS Fargate · HTTPS     | Firebase Auth · user_id no JWT    |
| 02 Gateway         | nginx Web Service público     | Cloud LB + URL Map / ALB · SSE      | Cloud Armor / AWS WAF gerenciado  |
| 03 Orchestration   | LangGraph v1.0+ Python 3.11   | Cloud Run / ECS Fargate             | Agent Engine Sessions (GA)        |
| 04 REST API        | Node.js 20 + Express 4        | Cloud Run / ECS Fargate             | Bedrock Guardrails (input/output) |
| 05 Data            | Neon PostgreSQL (migrado)     | Cloud SQL / RDS PostgreSQL managed  | Cloud SQL / RDS sem mudança       |
| 06 Cache           | node-cache in-memory TTL 60s  | Memorystore / ElastiCache Redis     | + semantic cache se RAG           |
| 07 Observability   | LangSmith (já existe)         | LangSmith + Cloud Monitoring        | + Vertex AI Evaluation no CI/CD   |
| 08 Infrastructure  | render.yaml declarativo       | Terraform `/infra/terraform/`       | Terraform + managed services      |

---

## 7 Padrões de Produção

| #  | Padrão           | Status no Codebase                              | Cloud Gerenciado                        | Prioridade  |
| -- | ---------------- | ----------------------------------------------- | --------------------------------------- | ----------- |
| 01 | API Gateway      | ✓ nginx + LANGGRAPH_AUTH_TOKEN                  | Cloud LB + URL Map (GCP) / ALB (AWS)    | Fase 2      |
| 02 | Rate Limiting    | ✓ express-rate-limit 100/15min por IP           | Cloud Armor / AWS WAF                   | Fase 2      |
| 03 | Caching          | parcial node-cache in-memory TTL 60s            | Memorystore Redis ~$35/mês              | Fase 2      |
| 04 | Message Queues   | não necessário — fluxo síncrono por design      | Pub/Sub / SQS se async necessário       | pular       |
| 05 | Circuit Breaker  | parcial tenacity email + TTS; gap: llm_core.py  | **pybreaker + Bedrock Guardrails**      | P1 urgente  |
| 06 | Load Balancing   | ✓ nginx proxy local                             | Cloud Run / ECS Fargate (automático)    | grátis      |
| 07 | Auto Scaling     | ✓ healthchecks no docker-compose                | Cloud Run escala 0→N / ECS min/max      | grátis      |

---

## Análise de Gaps Agênticos

O que falta para ser production-grade (baseado em *Prototype to Production* — Google, 2025):

**O que o AgendAI já tem:**
- LangGraph com grafo de 6 nós e roteamento condicional
- Function calling com 5 tools (GPT-4o-mini)
- LangSmith — traces, latência por nó, tool calls
- Rate limiting por IP (express-rate-limit)
- Caching com TTL + invalidação em escrita
- Retry com tenacity (email + TTS)
- STT (Whisper) + TTS (OpenAI) — entrada multimodal
- nginx como gateway com token de auth de serviço
- 109 testes automatizados (39 Jest + 70 pytest)
- 17 ADRs documentando decisões arquiteturais

**O que está faltando (por prioridade):**

| Prioridade | Gap                        | Descrição                                                              |
| ---------- | -------------------------- | ---------------------------------------------------------------------- |
| P1 urgente | Circuit Breaker no LLM     | `llm_core.py` sem retry/CB para RateLimitError, APITimeoutError        |
| P2 alta    | Sessão persistente         | InMemoryCheckpointer reseta em restart — substituir por PostgresSaver  |
| P3 alta    | Autenticação de usuário   | Só token de serviço; sem user_id, JWT ou sessão individual             |
| P4 média   | Guardrails de input        | Sem validação contra prompt injection, PII, tópicos off-scope          |
| P5 baixa   | Logs estruturados          | Sem correlation IDs, JSON logging, request tracing end-to-end          |
| —          | Cache distribuído          | node-cache não sincroniza entre múltiplas instâncias                   |

---

## Redis: dois papéis distintos

O AgendAI usa Redis em dois contextos completamente diferentes:

| Aspecto           | Redis de Cache — API Node.js                        | Redis de Streaming — LangGraph Server           |
| ----------------- | ---------------------------------------------------- | ----------------------------------------------- |
| Para quê          | Cache de respostas HTTP (horários). TTL 60s          | Pub-sub broker para SSE de background runs      |
| Quem usa          | API Node.js (`node-cache` → Memorystore na Fase 2)   | `langchain/langgraph-server` internamente        |
| Variável          | `REDIS_CACHE_URI`                                    | `REDIS_URI`                                     |
| Free tier         | Upstash: 10k cmd/dia gratuito                        | Upstash: mesma instância ou separada            |
| Fase              | Fase 2: Memorystore (GCP) / ElastiCache (AWS)        | Fase 1: obrigatório para LangGraph Server       |

> Para portfólio, uma única instância Upstash serve os dois propósitos (LangGraph usa prefixo `langgraph:`). Em produção real, separe por segurança operacional.

---

## Fluxos suportados

| Fluxo                  | O que enviar no chat                            | Resultado                              |
| ---------------------- | ----------------------------------------------- | -------------------------------------- |
| Horários disponíveis  | `"Quais horários vocês têm?"`              | Lista com médico, data e hora          |
| Agendar consulta       | `"Agendar para joao@email.com no horário 3"` | Confirmação + e-mail ao paciente      |
| Cancelar consulta      | `"Cancelar minha consulta 1"`                 | Confirmação de cancelamento + e-mail  |
| Valores e pagamento    | `"Quanto custa a consulta?"`                  | Preço em R$ + formas aceitas           |
| Entrada por áudio     | Clique 🎙 ou 📎 e envie um `.mp3`             | Whisper transcreve → agente responde   |

---

## Variáveis de ambiente

Todas as variáveis estão documentadas no `.env.example`.

| Variável                | Obrigatório | Descrição                                              |
| ------------------------ | ----------- | ------------------------------------------------------- |
| `OPENAI_API_KEY`        | **Sim**     | GPT-4o-mini, Whisper e TTS                              |
| `LANGSMITH_API_KEY`     | **Sim**     | LangGraph Server license + tracing (Developer plan)     |
| `DATABASE_URL`          | **Sim**     | Postgres para a API (`agendai` — Neon free tier)        |
| `DATABASE_URI`          | **Sim**     | Postgres para o LangGraph Server (`agendai_lg`)         |
| `REDIS_URI`             | **Sim**     | Redis para SSE streaming do LangGraph Server (Upstash)  |
| `LANGGRAPH_AUTH_TOKEN`  | **Sim**     | Token compartilhado: nginx ↔ UI ↔ agente               |
| `GMAIL_USER`            | Não         | Remetente dos e-mails de confirmação                   |
| `GMAIL_APP_PASSWORD`    | Não         | App Password do Gmail (16 chars)                        |
| `LANGSMITH_TRACING`     | Não         | `true` para habilitar traces no LangSmith              |
| `LANGSMITH_PROJECT`     | Não         | Nome do projeto no LangSmith (default: `AgendAI`)       |
| `API_BASE_URL`          | Não         | URL interna da API (default: `http://api:3000`)         |

> `PORT` já tem valor padrão `3000`. `LANGSMITH_API_KEY` serve tanto como licença do servidor quanto para tracing — um único campo para ambos os papéis.

### Configurar Gmail (opcional)

1. Conta Google → **Segurança → Verificação em duas etapas** (ativar)
2. **Segurança → Senhas de app → Outro → "AgendAI"**
3. Copiar a senha gerada (16 caracteres)
4. No `.env`: `GMAIL_USER=seu@gmail.com` e `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`

---

## Testes

**API REST** (39 testes Jest — requer Postgres local ou container):

```bash
export DATABASE_URL=postgres://agendai:agendai@localhost:5433/agendai_test
cd api && npm install && npm test
```

**Agente Python** (70 testes — nodes, tools, grafo, roteamento, estado):

```bash
cd agent
uv run pytest --tb=short
```

**Total: 109 testes automatizados** — gate obrigatório no CI antes de qualquer deploy.

---

## API REST — Endpoints

| Método | Rota                                      | Descrição                                          |
| ------- | ----------------------------------------- | ---------------------------------------------------- |
| GET     | `/horarios/disponiveis`                  | Lista horários com dados do médico (cache TTL 60s) |
| GET     | `/horarios/disponiveis?data=YYYY-MM-DD`  | Filtra por data                                      |
| POST    | `/agendamentos`                          | Cria agendamento e invalida cache                    |
| PATCH   | `/agendamentos/:id/cancelar`             | Cancela agendamento e invalida cache                 |
| GET     | `/agendamentos/:id`                      | Detalhe de um agendamento                            |
| GET     | `/pacientes/:email`                      | Busca paciente por e-mail                            |
| GET     | `/pagamentos`                            | Valores e formas de pagamento                        |
| GET     | `/painel`                                | Painel HTML com todos os agendamentos                |

Importe a coleção Postman em `postman/clinica.collection.json` e configure `BASE_URL=http://localhost:3000`.

---

## Banco de dados

**PostgreSQL** (Neon em produção; container `postgres:16` em dev). Dois bancos lógicos:

| Banco        | Usado por           | Env var        |
| ------------ | ------------------- | -------------- |
| `agendai`    | REST API            | `DATABASE_URL` |
| `agendai_lg` | LangGraph Server    | `DATABASE_URI` |

Seed executado automaticamente no boot (guard de contagem — idempotente):

| Paciente       | E-mail          | Telefone    |
| -------------- | --------------- | ----------- |
| João Silva    | joao@email.com  | 11999990001 |
| Maria Santos   | maria@email.com | 11999990002 |
| Pedro Oliveira | pedro@email.com | 11999990003 |
| Ana Ferreira   | ana@email.com   | 11999990004 |
| Lucas Pereira  | lucas@email.com | 11999990005 |

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

| Nó                      | Arquivo                                  | Função                                          |
| ------------------------ | ---------------------------------------- | ------------------------------------------------- |
| `detect_input_type`     | `agent/nodes/input_detector.py`        | Roteia texto vs. áudio                           |
| `transcribe_audio`      | `agent/nodes/transcriber.py`           | Whisper STT                                       |
| `chat_with_llm`         | `agent/nodes/llm_core.py`              | GPT-4o-mini com 5 tools                           |
| `execute_tools`         | `agent/nodes/tools.py`                 | Chama endpoints da API REST                       |
| `process_tool_results`  | `agent/nodes/tool_result_processor.py` | Detecta agendamento/cancelamento e prepara e-mail |
| `send_email`            | `agent/nodes/email_sender.py`          | Gmail SMTP (retry 3x via tenacity)                |
| `synthesize_tts`        | `agent/nodes/tts.py`                   | OpenAI TTS voz alloy (retry 3x)                   |

O grafo é compilado **sem checkpointer** em `agent/agent/graph.py` — o LangGraph Server injeta seu próprio checkpointer Postgres em runtime.

---

## Diferenciais implementados

| Diferencial              | Detalhe                                                                         |
| ------------------------ | ------------------------------------------------------------------------------- |
| Testes API (39)          | Jest + Supertest — 7 suites: rotas, cache, concorrência, validação          |
| Testes agente (70)       | pytest — nodes, grafo, roteamento, estado, tool result processor               |
| Function calling         | GPT-4o-mini com 5 funções: horários, agendar, cancelar, pagamentos, paciente |
| Retry e-mail             | `tenacity` — 3 tentativas com backoff exponencial                            |
| Retry TTS                | `tenacity` — 3 tentativas em `tts.py`                                       |
| Cache de disponibilidade | `node-cache` TTL 60s, invalidado em cada escrita                              |
| Painel de consultas      | `GET /painel` — tabela HTML colorida por status                              |
| Arquitetura em camadas   | `routes → controllers → services → repositories` com injeção de DB        |
| Rate limiting            | 100 req/15 min por IP via `express-rate-limit`                                |
| LangGraph Server         | `langchain/langgraph-server` com persistência Postgres e SSE via Redis       |
| Roadmap de 3 fases       | Local → Render → Cloud IaC (Terraform GCP/AWS) → Managed (Bedrock + Vertex)  |

---

## Documentação técnica

### Decisões de arquitetura (ADRs)

| ADR                                                   | Decisão                                     |
| ----------------------------------------------------- | -------------------------------------------- |
| [ADR-001](docs/adr/ADR-001-node-express.md)              | Node.js + Express para a API REST            |
| [ADR-002](docs/adr/ADR-002-sqlite-better-sqlite3.md)     | SQLite com better-sqlite3 (fase local)       |
| [ADR-003](docs/adr/ADR-003-stateless-conversation.md)    | Conversa stateless no agente                 |
| [ADR-004](docs/adr/ADR-004-gpt-4o-mini.md)               | GPT-4o-mini como LLM principal               |
| [ADR-006](docs/adr/ADR-006-openai-whisper.md)            | Whisper para transcrição de áudio          |
| [ADR-007](docs/adr/ADR-007-openai-tts.md)                | OpenAI TTS para síntese de voz             |
| [ADR-012](docs/adr/ADR-012-apiclient-singleton-async.md) | API client singleton assíncrono            |
| [ADR-013](docs/adr/ADR-013-langgraph-dev-server.md)      | LangGraph dev server                         |
| [ADR-014](docs/adr/ADR-014-checkpointer-inmem.md)        | Checkpointer in-memory (gap P2 — migrar para PostgresSaver) |
| [ADR-015](docs/adr/ADR-015-langgraph-vs-n8n.md)          | LangGraph vs N8N — justificativa da escolha |
| [ADR-016](docs/adr/ADR-016-nginx-reverse-proxy.md)       | nginx como reverse proxy                     |
| [ADR-017](docs/adr/ADR-017-api-security-tokens.md)       | Segurança por tokens na API                |
| [ADR-018](docs/adr/ADR-018-polyglot-node-python.md)      | Stack poliglota Node.js + Python             |
| [ADR-019](docs/adr/ADR-019-agent-ui.md)                  | Chat UI com Next.js                          |
| [ADR-020](docs/adr/ADR-020-docker-compose.md)            | Docker Compose para infraestrutura local     |
| [ADR-021](docs/adr/ADR-021-langsmith-observability.md)   | LangSmith para observabilidade               |

> O ADR-015 explica em detalhe por que LangGraph foi escolhido no lugar de N8N para este projeto.

### Specs e planejamento

| Artefato                      | Arquivo                                                                                   |
| ----------------------------- | ----------------------------------------------------------------------------------------- |
| Especificação da UI de chat  | [specs/003-professional-chat-ui/spec.md](specs/003-professional-chat-ui/spec.md)             |
| Plano de implementação       | [specs/003-professional-chat-ui/plan.md](specs/003-professional-chat-ui/plan.md)             |
| Quickstart detalhado          | [specs/003-professional-chat-ui/quickstart.md](specs/003-professional-chat-ui/quickstart.md) |
| Modelo de dados               | [specs/003-professional-chat-ui/data-model.md](specs/003-professional-chat-ui/data-model.md) |
| Tasks de implementação       | [specs/003-professional-chat-ui/tasks.md](specs/003-professional-chat-ui/tasks.md)           |
| Plano de deploy Fase 1       | [specs/004-fase-1-deploy/plan.md](specs/004-fase-1-deploy/plan.md)                           |
| Roadmap de arquitetura        | [docs/AgendAI_Architecture_Roadmap.pdf](docs/AgendAI_Architecture_Roadmap.pdf)               |

### Checklist de testes e evidências

Ver [docs/CHECKLIST.md](docs/CHECKLIST.md) — cenários testados manualmente e via suite automatizada com referências a screenshots e gravações de tela.

---

## Troubleshooting

| Sintoma                                    | Causa                                              | Solução                                                |
| ------------------------------------------ | -------------------------------------------------- | ------------------------------------------------------ |
| `connection refused` em `/horarios`      | Container API não iniciou                          | `docker compose logs api`                              |
| Agente não responde em :8080              | Container langgraph-server falhou                  | `docker compose logs langgraph-server`                 |
| `DATABASE_URL` connection error           | Neon PostgreSQL não configurado                    | Verificar `DATABASE_URL` no `.env`                    |
| `REDIS_URI` connection error              | Upstash Redis não configurado                      | Verificar `REDIS_URI` no `.env`                       |
| LangGraph Server não sobe                 | `LANGSMITH_API_KEY` ausente ou inválida            | Developer plan obrigatório para licença do servidor    |
| E-mails não chegam                        | `GMAIL_USER`/`APP_PASSWORD` não configurados       | Ver seção Gmail acima                                  |
| Resposta de áudio retorna texto           | TTS falhou                                         | Verificar `OPENAI_API_KEY` e logs do agente            |
| `409 Horário não disponível`          | Horário já agendado                               | Usar ID de `GET /horarios/disponiveis`                 |
| `404 Paciente não encontrado`           | E-mail não cadastrado                             | Usar e-mail da tabela seed acima                       |
| UI não conecta ao agente                  | CORS ou URL errada                                 | Verificar `NEXT_PUBLIC_LANGGRAPH_API_URL` no `.env`  |
