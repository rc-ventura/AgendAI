# AgendAI — Automação de Atendimento Médico com IA

Sistema de agendamento médico automatizado com agente LangGraph, GPT-4o-mini, API REST Node.js e suporte a texto e áudio.

---

## Quickstart

> Única variável obrigatória: `OPENAI_API_KEY`. Todas as outras já estão preenchidas no `.env.example` (Gmail e LangSmith são opcionais).

```bash
git clone <url-do-repositorio>
cd AgendAI
cp .env.example .env
# Edite .env e preencha: OPENAI_API_KEY=sk-...
docker compose up --build -d
```

Aguarde o build (~2 min na primeira vez) e acesse:

| Serviço               | URL                                 |
| ---------------------- | ----------------------------------- |
| Chat UI                | http://localhost:3002               |
| API REST               | http://localhost:3000               |
| Painel de agendamentos | http://localhost:3000/painel        |
| Agente LangGraph       | http://localhost:8080 (proxy nginx) |

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

| Fluxo                                | Arquivo                                                           |
| ------------------------------------ | ----------------------------------------------------------------- |
| Consulta de horários disponíveis   | [demo-consulta-horarios.mov](docs/prints/demo-consulta-horarios.mov) |
| Fluxo de áudio (upload + resposta)  | [demo-fluxo-audio.mov](docs/prints/demo-fluxo-audio.mov)             |
| Agendamento via chat                 | [demo-agendamento-chat.mov](docs/prints/demo-agendamento-chat.mov)   |
| Cancelamento via chat                | [demo-cancelamento-chat.mov](docs/prints/demo-cancelamento-chat.mov) |

---

## Stack

| Componente      | Tecnologia                            | Porta |
| --------------- | ------------------------------------- | ----- |
| API REST        | Node.js 20 + Express 4 + SQLite       | 3000  |
| Agente          | Python 3.11 + LangGraph v1.0+         | 8123  |
| Chat UI         | Next.js 14 + @langchain/langgraph-sdk | 3002  |
| Proxy           | nginx                                 | 8080  |
| LLM             | GPT-4o-mini (tool calling)            | —    |
| STT             | OpenAI Whisper (whisper-1)            | —    |
| TTS             | OpenAI TTS (tts-1, voz alloy)         | —    |
| E-mail          | Gmail SMTP + tenacity (retry 3x)      | —    |
| Observabilidade | LangSmith (opcional)                  | —    |

---

## Fluxos suportados

| Fluxo                  | O que enviar no chat                            | Resultado                              |
| ---------------------- | ----------------------------------------------- | -------------------------------------- |
| Horários disponíveis | `"Quais horários vocês têm?"`              | Lista com médico, data e hora         |
| Agendar consulta       | `"Agendar para joao@email.com no horário 3"` | Confirmação + e-mail ao paciente     |
| Cancelar consulta      | `"Cancelar minha consulta 1"`                 | Confirmação de cancelamento + e-mail |
| Valores e pagamento    | `"Quanto custa a consulta?"`                  | Preço em R$ + formas aceitas          |
| Entrada por áudio     | Clique 🎙 ou 📎 e envie um `.mp3`             | Whisper transcreve → agente responde  |

---

## Variáveis de ambiente

Todas as variáveis estão documentadas no `.env.example`. Apenas uma é obrigatória para o sistema funcionar:

| Variável                | Obrigatório  | Descrição                            |
| ------------------------ | ------------- | -------------------------------------- |
| `OPENAI_API_KEY`       | **Sim** | GPT-4o-mini, Whisper e TTS             |
| `GMAIL_USER`           | Não          | Remetente dos e-mails de confirmação |
| `GMAIL_APP_PASSWORD`   | Não          | App Password do Gmail (16 chars)       |
| `LANGCHAIN_TRACING_V2` | Não          | `true` para habilitar LangSmith      |
| `LANGCHAIN_API_KEY`    | Não          | Chave do LangSmith                     |
| `LANGGRAPH_AUTH_TOKEN` | Não          | Token de autenticação do proxy nginx |

> `PORT`, `DB_PATH` e `API_BASE_URL` já têm valores padrão corretos para Docker Compose.

### Configurar Gmail (opcional)

1. Conta Google → **Segurança → Verificação em duas etapas** (ativar)
2. **Segurança → Senhas de app → Outro → "AgendAI"**
3. Copiar a senha gerada (16 caracteres)
4. No `.env`: `GMAIL_USER=seu@gmail.com` e `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`

---

## Testes

**API REST** (39 testes Jest — banco `:memory:`, sem Docker):

```bash
cd api && npm install && npm test
```

**Agente Python** (70 testes — nodes, tools, grafo, roteamento, estado):

```bash
cd agent
uv run pytest
```

---

## API REST — Endpoints

| Método | Rota                                      | Descrição                                          |
| ------- | ----------------------------------------- | ---------------------------------------------------- |
| GET     | `/horarios/disponiveis`                 | Lista horários com dados do médico (cache TTL 60s) |
| GET     | `/horarios/disponiveis?data=YYYY-MM-DD` | Filtra por data                                      |
| POST    | `/agendamentos`                         | Cria agendamento e invalida cache                    |
| PATCH   | `/agendamentos/:id/cancelar`            | Cancela agendamento e invalida cache                 |
| GET     | `/agendamentos/:id`                     | Detalhe de um agendamento                            |
| GET     | `/pacientes/:email`                     | Busca paciente por e-mail                            |
| GET     | `/pagamentos`                           | Valores e formas de pagamento                        |
| GET     | `/painel`                               | Painel HTML com todos os agendamentos                |

Importe a coleção Postman em `postman/clinica.collection.json` e configure `BASE_URL=http://localhost:3000`.

---

## Banco de dados (seed inicial)

SQLite em `data/clinica.db`. Seed executado automaticamente no boot:

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
| `detect_input_type`    | `agent/nodes/input_detector.py`        | Roteia texto vs. áudio                           |
| `transcribe_audio`     | `agent/nodes/transcriber.py`           | Whisper STT                                       |
| `chat_with_llm`        | `agent/nodes/llm_core.py`              | GPT-4o-mini com 5 tools                           |
| `execute_tools`        | `agent/nodes/tools.py`                 | Chama endpoints da API REST                       |
| `process_tool_results` | `agent/nodes/tool_result_processor.py` | Detecta agendamento/cancelamento e prepara e-mail |
| `send_email`           | `agent/nodes/email_sender.py`          | Gmail SMTP (retry 3x via tenacity)                |
| `synthesize_tts`       | `agent/nodes/tts.py`                   | OpenAI TTS voz alloy (retry 3x)                   |

---

## Diferenciais implementados

| Diferencial              | Detalhe                                                                         |
| ------------------------ | ------------------------------------------------------------------------------- |
| Testes API (39)          | Jest + Supertest — 7 suites: rotas, cache, concorrência, validação          |
| Testes agente (70)       | pytest — nodes, grafo, roteamento, estado, tool result processor               |
| Function calling         | GPT-4o-mini com 5 funções: horários, agendar, cancelar, pagamentos, paciente |
| Retry e-mail             | `tenacity` — 3 tentativas com backoff exponencial                            |
| Retry TTS                | `tenacity` — 3 tentativas em `tts.py`                                      |
| Cache de disponibilidade | `node-cache` TTL 60s, invalidado em cada escrita                              |
| Painel de consultas      | `GET /painel` — tabela HTML colorida por status                              |
| Arquitetura em camadas   | `routes → controllers → services → repositories` com injeção de DB       |
| Rate limiting            | 100 req/15 min por IP via `express-rate-limit`                                |

---

## Documentação técnica

### Decisões de arquitetura (ADRs)

| ADR                                                   | Decisão                                     |
| ----------------------------------------------------- | -------------------------------------------- |
| [ADR-001](docs/adr/ADR-001-node-express.md)              | Node.js + Express para a API REST            |
| [ADR-002](docs/adr/ADR-002-sqlite-better-sqlite3.md)     | SQLite com better-sqlite3                    |
| [ADR-003](docs/adr/ADR-003-stateless-conversation.md)    | Conversa stateless no agente                 |
| [ADR-004](docs/adr/ADR-004-gpt-4o-mini.md)               | GPT-4o-mini como LLM principal               |
| [ADR-006](docs/adr/ADR-006-openai-whisper.md)            | Whisper para transcrição de áudio         |
| [ADR-007](docs/adr/ADR-007-openai-tts.md)                | OpenAI TTS para síntese de voz              |
| [ADR-012](docs/adr/ADR-012-apiclient-singleton-async.md) | API client singleton assíncrono             |
| [ADR-013](docs/adr/ADR-013-langgraph-dev-server.md)      | LangGraph dev server                         |
| [ADR-014](docs/adr/ADR-014-checkpointer-inmem.md)        | Checkpointer in-memory                       |
| [ADR-015](docs/adr/ADR-015-langgraph-vs-n8n.md)          | LangGraph vs N8N — justificativa da escolha |
| [ADR-016](docs/adr/ADR-016-nginx-reverse-proxy.md)       | nginx como reverse proxy                     |
| [ADR-017](docs/adr/ADR-017-api-security-tokens.md)       | Segurança por tokens na API                 |
| [ADR-018](docs/adr/ADR-018-polyglot-node-python.md)      | Stack poliglota Node.js + Python             |
| [ADR-019](docs/adr/ADR-019-agent-ui.md)                  | Chat UI com Next.js                          |
| [ADR-020](docs/adr/ADR-020-docker-compose.md)            | Docker Compose para infraestrutura local     |
| [ADR-021](docs/adr/ADR-021-langsmith-observability.md)   | LangSmith para observabilidade               |

> O ADR-015 explica em detalhe por que LangGraph foi escolhido no lugar de N8N para este projeto.

### Specs e planejamento

| Artefato                      | Arquivo                                                                                   |
| ----------------------------- | ----------------------------------------------------------------------------------------- |
| Especificação da UI de chat | [specs/003-professional-chat-ui/spec.md](specs/003-professional-chat-ui/spec.md)             |
| Plano de implementação      | [specs/003-professional-chat-ui/plan.md](specs/003-professional-chat-ui/plan.md)             |
| Quickstart detalhado          | [specs/003-professional-chat-ui/quickstart.md](specs/003-professional-chat-ui/quickstart.md) |
| Modelo de dados               | [specs/003-professional-chat-ui/data-model.md](specs/003-professional-chat-ui/data-model.md) |
| Tasks de implementação      | [specs/003-professional-chat-ui/tasks.md](specs/003-professional-chat-ui/tasks.md)           |

### Checklist de testes e evidências

Ver [docs/CHECKLIST.md](docs/CHECKLIST.md) — cenários testados manualmente e via suite automatizada com referências a screenshots e gravações de tela.

---

## Troubleshooting

| Sintoma                                 | Causa                                             | Solução                                               |
| --------------------------------------- | ------------------------------------------------- | ------------------------------------------------------- |
| `connection refused` em `/horarios` | Container API não iniciou                        | `docker compose logs api`                             |
| Agente não responde em :8080           | Container agent falhou                            | `docker compose logs agent`                           |
| E-mails não chegam                     | `GMAIL_USER`/`APP_PASSWORD` não configurados | Ver seção Gmail acima                                 |
| Resposta de áudio retorna texto        | TTS falhou                                        | Verificar `OPENAI_API_KEY` e logs do agente           |
| `409 Horário não disponível`       | Horário já agendado                             | Usar ID de `GET /horarios/disponiveis`                |
| `404 Paciente não encontrado`        | E-mail não cadastrado                            | Usar e-mail da tabela seed acima                        |
| UI não conecta ao agente               | CORS ou URL errada                                | Verificar `NEXT_PUBLIC_LANGGRAPH_API_URL` no `.env` |
