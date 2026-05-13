# AgendAI — Automação de Atendimento Médico com N8N e IA

Sistema de agendamento médico automatizado com N8N, GPT-4o-mini, API REST e suporte a texto e áudio.

## Visão Geral

| Componente | Tecnologia | Porta |
|---|---|---|
| API REST | Node.js 20 + Express 4 + SQLite | 3000 |
| Orquestração | N8N self-hosted (Docker) | 5678 |
| LLM | GPT-4o-mini (function calling) | — |
| STT | OpenAI Whisper (whisper-1) | — |
| TTS | OpenAI TTS (tts-1, voz alloy) | — |
| E-mail | Gmail API via N8N OAuth2 | — |

## Pré-requisitos

| Ferramenta | Versão |
|---|---|
| Docker | ≥ 24 |
| Docker Compose | v2 |
| Node.js | 20 LTS (para testes unitários locais) |
| Conta OpenAI | Chave de API com créditos |
| Conta Google | Gmail API habilitada (OAuth2) |

## Instalação e Execução

### 1. Clonar e Configurar

```bash
git clone <url-do-repositorio>
cd AgendAI
cp .env.example .env
```

Editar `.env` com sua chave OpenAI:
```env
OPENAI_API_KEY=sk-...
PORT=3000
DB_PATH=/app/data/clinica.db
```

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

### 3. Configurar Credenciais no N8N

1. Acessar `http://localhost:5678` — criar conta admin/admin
2. **Settings → Credentials → New → OpenAI API**
   - Inserir `OPENAI_API_KEY`
3. **Settings → Credentials → New → Gmail OAuth2 API**
   - Seguir fluxo OAuth2 (ver `docs/prints/gmail-setup/`)
   - Escopo necessário: `https://www.googleapis.com/auth/gmail.send`

### 4. Importar os Fluxos N8N

Importar **nesta ordem** (Menu → Import from file):

1. `n8n/flow-d-email.json`
2. `n8n/flow-b-ai-core.json`
3. `n8n/flow-a-entrada.json`
4. `n8n/flow-c-audio.json`

Após importar cada flow:
- Associar as credenciais OpenAI e Gmail nos nodes correspondentes
- Verificar que `API_BASE_URL` nos nodes HTTP Request aponta para `http://api:3000`
- No flow-a: atualizar os IDs dos workflows de flow-b e flow-c nos nodes "Execute Workflow"
- No flow-b: atualizar o ID do flow-d no node "Execute Workflow"
- **Ativar** cada workflow (toggle no canto superior direito)

### 5. Rodar Testes Unitários

```bash
cd api
npm install
npm test
```

Esperado: 19 testes passando em 4 arquivos.

## Uso

### Chat via curl

**Texto**:
```bash
curl -X POST http://localhost:5678/webhook/chat \
  -H "Content-Type: application/json" \
  -d '{"type":"text","text":"Quais horários disponíveis para amanhã?"}'
```

**Áudio**:
```bash
curl -X POST http://localhost:5678/webhook/chat \
  -F "type=audio" \
  -F "file=@sample.ogg"
```

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

# Cancelar agendamento
curl -X PATCH http://localhost:3000/agendamentos/1/cancelar

# Pagamentos
curl http://localhost:3000/pagamentos

# Painel HTML
open http://localhost:3000/painel
```

## Fluxos N8N

| Flow | Arquivo | Função |
|---|---|---|
| A — Entrada | `flow-a-entrada.json` | Webhook `/chat`, detecta texto ou áudio e roteia |
| B — IA Core | `flow-b-ai-core.json` | GPT-4o-mini + function calling + HTTP para API |
| C — Áudio | `flow-c-audio.json` | Whisper → Flow B → TTS (voz alloy) |
| D — E-mail | `flow-d-email.json` | Sub-workflow Gmail (reutilizado por B e C) |

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

- **Testes unitários** — Jest + Supertest (19 testes, 4 suites)
- **Function calling** — GPT-4o-mini com 5 funções mapeadas para endpoints REST
- **Retry** — Gmail node (3x, 5s) e TTS HTTP Request (3x, 3s) no N8N
- **Cache de disponibilidade** — TTL 60s com `node-cache`, invalidado em cada escrita
- **Painel HTML** — `GET /painel` com tabela colorida de agendamentos

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| `connection refused` em `/horarios` | Container API não iniciou | `docker compose logs api` |
| Flow N8N não responde | Workflow não ativado | Ativar toggle no N8N UI |
| E-mails não chegam | Token Gmail expirado | Reconfigurar credencial Gmail no N8N |
| Resposta de áudio é texto | TTS falhou | Verificar `OPENAI_API_KEY` e logs do N8N |
| `409 Horário não disponível` | Horário já agendado | Usar ID de `GET /horarios/disponiveis` |
| `404 Paciente não encontrado` | E-mail não cadastrado | Usar e-mail da tabela de seed acima |
