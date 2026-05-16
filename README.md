# AgendAI — Automação de Atendimento Médico com LangGraph e IA

Sistema de agendamento médico automatizado com LangGraph v1.0+, GPT-4o-mini, API REST e suporte a texto e áudio.

## Visão Geral

| Componente | Tecnologia | Porta |
|---|---|---|
| API REST | Node.js 20 + Express 4 + SQLite | 3000 |
| Agente LangGraph | Python 3.11 + LangGraph v1.0+ | 8123 |
| Chat UI | Next.js 14 + @langchain/langgraph-sdk | 3001 |
| LLM | GPT-4o-mini (tool calling) | — |
| STT | OpenAI Whisper (whisper-1) | — |
| TTS | OpenAI TTS (tts-1, voz alloy) | — |
| E-mail | Gmail SMTP via Python + tenacity | — |
| Observabilidade | LangSmith | — |

## Pré-requisitos

| Ferramenta | Versão |
|---|---|
| Docker | ≥ 24 |
| Docker Compose | v2 |
| Conta OpenAI | Chave de API com créditos (GPT-4o-mini, Whisper, TTS) |
| Python 3.11+ | Apenas para rodar testes do agente localmente |
| Node.js 20 LTS | Apenas para rodar testes da UI/API localmente |

## Instalação e Execução

### 1. Clonar e Configurar

```bash
git clone <url-do-repositorio>
cd AgendAI
cp .env.example .env
```

Editar `.env` — variáveis obrigatórias:
```env
# Obrigatório
OPENAI_API_KEY=sk-...

# Opcional — notificações por e-mail
GMAIL_USER=clinica@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # App Password (não a senha normal)

# Opcional — observabilidade LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
```

> `PORT`, `DB_PATH` e `API_BASE_URL` já têm valores padrão corretos no `docker-compose.yml`.

### 2. Subir os Serviços

```bash
docker compose up --build -d
```

Verificar se está no ar:
```bash
docker compose ps
curl http://localhost:3000/horarios/disponiveis
```

Esperado: array JSON com horários disponíveis.

Após o build completo, acesse o chat em **http://localhost:3001**.

### 3. Testar os fluxos principais

| Fluxo | O que enviar no chat | Esperado |
|---|---|---|
| Horários disponíveis | "Quais horários vocês têm?" | Lista com médico, data e hora |
| Agendar consulta | "Agendar para joao@email.com horário 3" | Confirmação + e-mail (se Gmail configurado) |
| Cancelar consulta | "Cancelar minha consulta 1" | Confirmação de cancelamento |
| Valores/pagamento | "Quanto custa a consulta?" | Preço em R$ + formas aceitas |
| Áudio | Clique 🎙 ou 📎 e envie um `.mp3` | Resposta do agente em texto |

### 4. Rodar Testes

**Agente Python** (28 testes — nodes, tools, grafo):
```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

**API REST** (34 testes Jest):
```bash
cd api
npm install
npm test
```

**Chat UI** (Vitest + MSW — sem Docker):
```bash
cd agent-ui
npm install
npm test
```

## Uso

### Chat via UI

Acesse `http://localhost:3001` — a UI conecta diretamente ao LangGraph server (via proxy nginx em `:8080`). Para chamadas programáticas use o SDK `@langchain/langgraph-sdk` (ver `agent-ui/src/lib/langgraph.ts`).

### API direta

```bash
# Horários disponíveis
curl http://localhost:3000/horarios/disponiveis

# Buscar paciente
curl http://localhost:3000/pacientes/joao@email.com

# Criar agendamento
curl -X POST http://localhost:3000/agendamentos \
  -H "Content-Type: application/json" \
  -d '{"paciente_email":"pedro@email.com","horario_id":3}'

# Buscar agendamento
curl http://localhost:3000/agendamentos/1

# Cancelar agendamento
curl -X PATCH http://localhost:3000/agendamentos/1/cancelar

# Pagamentos
curl http://localhost:3000/pagamentos

# Painel HTML
open http://localhost:3000/painel
```

## Nós do Grafo LangGraph

| Nó | Arquivo | Função |
|---|---|---|
| `detect_input_type` | `agent/agent/nodes/input_detector.py` | Roteia texto vs. áudio |
| `transcribe_audio` | `agent/agent/nodes/transcriber.py` | Whisper STT |
| `chat_with_llm` + `execute_tools` | `agent/agent/nodes/llm_core.py` + `tools.py` | GPT-4o-mini + tool calling + HTTP para API |
| `process_tool_results` | `agent/agent/nodes/tool_result_processor.py` | Detecta sucesso de criar/cancelar agendamento e prepara payload de e-mail |
| `send_email` | `agent/agent/nodes/email_sender.py` | Gmail SMTP (retry via tenacity) |
| `synthesize_tts` | `agent/agent/nodes/tts.py` | OpenAI TTS (voz alloy) |

## Banco de Dados

SQLite com 5 tabelas: `medicos`, `pacientes`, `horarios`, `agendamentos`, `pagamentos`.

**Seed inicial**: 3 médicos, 5 pacientes, 10 horários (próximos 7 dias), 2 agendamentos pré-confirmados.

**Resetar banco**:
```bash
docker compose down -v
docker compose up --build -d
```

## Entidades do Seed

| Paciente | E-mail | Telefone |
|---|---|---|
| João Silva | joao@email.com | 11999990001 |
| Maria Santos | maria@email.com | 11999990002 |
| Pedro Oliveira | pedro@email.com | 11999990003 |
| Ana Ferreira | ana@email.com | 11999990004 |
| Lucas Pereira | lucas@email.com | 11999990005 |

## Diferenciais Implementados

- **Testes unitários** — Jest + Supertest (34 testes, 7 suites: rotas, cache, concorrência, validação)
- **Arquitetura em camadas** — `routes → controllers → services → repositories` com injeção de dependência
- **Function calling** — GPT-4o-mini com 5 funções mapeadas para endpoints REST
- **Retry** — Gmail SMTP (3x, backoff exponencial) e OpenAI TTS (3x) via `tenacity` no agente LangGraph
- **Cache de disponibilidade** — TTL 60s com `node-cache`, invalidado em cada escrita
- **Rate limiting** — 100 req/15 min por IP via `express-rate-limit`
- **Painel HTML** — `GET /painel` com tabela colorida de agendamentos

## Agente LangGraph

### Arquitetura do Grafo

```
START → detect_input_type → (text) → chat_with_llm ⇄ execute_tools → process_tool_results
                          → (audio) → transcribe_audio → chat_with_llm
                                                       → send_email → (audio) → synthesize_tts → END
                                                       → synthesize_tts → END
                                                       → END
```

### Chat UI (Agent UI)

Interface web em Next.js conectada via `@langchain/langgraph-sdk`:

```bash
# Acesso após docker compose up
open http://localhost:3001
```

Funcionalidades:
- Chat em texto (streaming de tokens)
- Gravação de áudio direta pelo microfone (botão 🎙)
- Upload de arquivo de áudio (botão 📎)
- Nova conversa (cria novo thread no LangGraph Platform)

### LangGraph Studio (debug local)

Para inspecionar o grafo visualmente durante o desenvolvimento:

```bash
cd agent
# Instalar dependências
pip install -e ".[dev]"

# Iniciar servidor de desenvolvimento
langgraph dev --host 0.0.0.0 --port 8123

# Abrir Studio no navegador
open https://smith.langchain.com/studio/?baseUrl=http://localhost:8123
```

O Studio mostra o estado completo de cada node, mensagens, tool calls e permite replay de execuções com LangSmith.

### Testes do Agente

```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

Esperado: 28 testes passando (state, api_client, nodes, graph).

### Variáveis de Ambiente do Agente

| Variável | Obrigatório | Descrição |
|---|---|---|
| `OPENAI_API_KEY` | Sim | GPT-4o-mini, Whisper, TTS |
| `API_BASE_URL` | Sim | URL da API REST (default: `http://api:3000`) |
| `LANGCHAIN_TRACING_V2` | Não | `true` para habilitar LangSmith |
| `LANGCHAIN_API_KEY` | Se tracing | Chave da API LangSmith |
| `LANGCHAIN_PROJECT` | Não | Nome do projeto (default: `AgendAI`) |
| `GMAIL_USER` | Não | E-mail remetente (ex: `clinica@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Não | App Password do Gmail (16 caracteres) |

### Configurar Gmail para notificações

1. Conta Google → **Segurança → Verificação em duas etapas** (ativar)
2. **Segurança → Senhas de app → Selecionar app: Outro → "AgendAI"**
3. Copiar a senha de 16 caracteres gerada
4. No `.env`: `GMAIL_USER=clinica@gmail.com` e `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| `connection refused` em `/horarios` | Container API não iniciou | `docker compose logs api` |
| Agente não responde em :8123 | Container agent falhou | `docker compose logs agent` |
| E-mails não chegam (agente) | GMAIL_USER/APP_PASSWORD não configurados | Ver seção Gmail acima |
| Resposta de áudio é texto | TTS falhou | Verificar `OPENAI_API_KEY` e logs do agente |
| `409 Horário não disponível` | Horário já agendado | Usar ID de `GET /horarios/disponiveis` |
| `404 Paciente não encontrado` | E-mail não cadastrado | Usar e-mail da tabela de seed acima |
| UI não conecta ao agente | CORS ou URL errada | Verificar `NEXT_PUBLIC_API_URL=http://localhost:8123` |
