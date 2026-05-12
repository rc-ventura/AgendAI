# SPEC — Automação de Atendimento Médico com N8N + IA

> Versão 1.0 | Desafio Técnico — Especialista em Automações com IA e N8N

---

## 1. Visão geral

Sistema de atendimento médico automatizado que recebe mensagens de pacientes via N8N Chat (texto ou áudio), processa com IA usando function calling, consulta uma API REST local com banco SQLite, e responde ao paciente — enviando confirmações por email via Gmail e devolvendo áudio via OpenAI TTS quando a entrada for áudio.

---

## 2. Stack de tecnologia

| Camada | Tecnologia | Justificativa (ADR) |
|---|---|---|
| API REST | Node.js + Express | Sem boilerplate, fácil integração com N8N via HTTP Request node (ADR-01) |
| Banco de dados | SQLite + better-sqlite3 | Sem servidor externo, operações síncronas, seed trivial (ADR-02) |
| Orquestrador | N8N (self-hosted via Docker) | Requisito do desafio |
| LLM | GPT-4o-mini | Function calling nativo, custo baixo para testes (ADR-04) |
| STT | OpenAI Whisper | Mesmo vendor do LLM e TTS, uma só chave de API (ADR-06) |
| TTS | OpenAI TTS (tts-1) | Mesmo vendor, latência aceitável para demonstração (ADR-07) |
| Email | Gmail API via N8N node | OAuth2 nativo no N8N, sem código extra na API (ADR-08) |
| Cache | node-cache na API | Cache pertence a quem possui os dados, testável, invalidação por evento (ADR-10) |
| Infra local | Docker Compose | Um comando sobe tudo, elimina "funciona na minha máquina" (ADR-09) |

---

## 3. Banco de dados

### 3.1 Schema

```sql
-- Médicos disponíveis
CREATE TABLE medicos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  nome      TEXT NOT NULL,
  especialidade TEXT NOT NULL
);

-- Pacientes cadastrados
CREATE TABLE pacientes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  nome      TEXT NOT NULL,
  email     TEXT NOT NULL UNIQUE,
  telefone  TEXT
);

-- Slots de horário por médico
CREATE TABLE horarios (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  medico_id   INTEGER NOT NULL REFERENCES medicos(id),
  data_hora   TEXT NOT NULL,       -- ISO 8601: "2025-06-10T09:00:00"
  disponivel  INTEGER DEFAULT 1    -- 1 = disponível, 0 = ocupado
);

-- Agendamentos realizados
CREATE TABLE agendamentos (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  paciente_id  INTEGER NOT NULL REFERENCES pacientes(id),
  horario_id   INTEGER NOT NULL REFERENCES horarios(id),
  status       TEXT DEFAULT 'ativo',  -- 'ativo' | 'cancelado'
  criado_em    TEXT DEFAULT (datetime('now'))
);

-- Tabela de valores e formas de pagamento
CREATE TABLE pagamentos (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  descricao     TEXT NOT NULL,
  valor         REAL NOT NULL,
  formas        TEXT NOT NULL   -- JSON array: ["PIX","Cartão","Dinheiro"]
);
```

### 3.2 Seed (dados iniciais)

Populados automaticamente na primeira inicialização da API:

- 3 médicos (clínico geral, cardiologista, dermatologista)
- 5 pacientes com email e telefone fictícios
- 10 horários distribuídos nos próximos 7 dias, todos disponíveis
- 1 registro de pagamento com valor de consulta e formas aceitas

### 3.3 Decisões de modelagem

- `data_hora` armazenado como TEXT ISO 8601 — SQLite não tem tipo DATETIME nativo, string ISO é ordenável e legível
- `status` como TEXT em vez de booleano — permite estados futuros (ex: `remarcado`) sem migração
- `formas` como JSON serializado — evita tabela extra para um dado simples e estático
- Chave única em `pacientes.email` — email é o identificador natural usado pelo LLM para buscar paciente

---

## 4. API REST

### 4.1 Endpoints

| Método | Rota | Descrição | Cache |
|---|---|---|---|
| GET | `/horarios/disponiveis` | Lista horários disponíveis com dados do médico | TTL 60s, invalida no POST /agendamentos |
| GET | `/horarios/disponiveis?data=2025-06-10` | Filtra por data | mesmo cache com chave por data |
| POST | `/agendamentos` | Cria agendamento, marca horário como indisponível | invalida cache |
| PATCH | `/agendamentos/:id/cancelar` | Cancela agendamento, libera horário | invalida cache |
| GET | `/agendamentos/:id` | Detalhe de um agendamento | sem cache |
| GET | `/pacientes/:email` | Busca paciente por email | sem cache |
| GET | `/pagamentos` | Valores e formas de pagamento | sem cache (dado estático) |
| GET | `/painel` | HTML com tabela de todos agendamentos (diferencial) | sem cache |

### 4.2 Contratos de resposta

**GET /horarios/disponiveis**
```json
[
  {
    "id": 3,
    "data_hora": "2025-06-10T09:00:00",
    "disponivel": 1,
    "medico": {
      "id": 1,
      "nome": "Dr. Carlos Lima",
      "especialidade": "Clínico Geral"
    }
  }
]
```

**POST /agendamentos** — body
```json
{
  "paciente_email": "joao@email.com",
  "horario_id": 3
}
```
Resposta `201`:
```json
{
  "id": 12,
  "paciente": { "id": 2, "nome": "João Silva", "email": "joao@email.com" },
  "horario": { "id": 3, "data_hora": "2025-06-10T09:00:00" },
  "medico": { "nome": "Dr. Carlos Lima" },
  "status": "ativo",
  "criado_em": "2025-06-09T14:32:00"
}
```

**PATCH /agendamentos/:id/cancelar** — sem body
Resposta `200`:
```json
{
  "id": 12,
  "status": "cancelado"
}
```

### 4.3 Erros semânticos

| Situação | Status | Mensagem |
|---|---|---|
| Horário não encontrado | 404 | `"Horário não encontrado"` |
| Horário já ocupado | 409 | `"Horário não está mais disponível"` |
| Paciente não encontrado | 404 | `"Paciente não encontrado"` |
| Agendamento não encontrado | 404 | `"Agendamento não encontrado"` |
| Agendamento já cancelado | 400 | `"Agendamento já está cancelado"` |

### 4.4 Cache

Implementado com `node-cache` na camada de rota:

```
GET /horarios/disponiveis
  → chave: "horarios" (ou "horarios:2025-06-10" se filtrado por data)
  → TTL: 60 segundos
  → invalidação: POST /agendamentos e PATCH /agendamentos/:id/cancelar
```

### 4.5 Estrutura de pastas da API

```
api/
├── src/
│   ├── app.js                  # Express setup, middlewares
│   ├── server.js               # Inicialização, seed condicional
│   ├── db/
│   │   ├── connection.js       # Singleton better-sqlite3
│   │   ├── schema.sql
│   │   └── seed.js             # Roda só se banco estiver vazio
│   ├── routes/
│   │   ├── horarios.js
│   │   ├── agendamentos.js
│   │   ├── pacientes.js
│   │   ├── pagamentos.js
│   │   └── painel.js
│   ├── cache/
│   │   └── index.js            # Instância node-cache + helpers get/set/del
│   └── middlewares/
│       └── errorHandler.js
├── tests/
│   ├── horarios.test.js
│   ├── agendamentos.test.js
│   └── pagamentos.test.js
├── package.json
└── Dockerfile
```

---

## 5. Fluxos N8N

### 5.1 Visão dos 4 fluxos

```
flow-a-entrada     →  detecta tipo (texto|áudio), normaliza para texto
flow-b-ai-core     →  LLM + function calling + chamadas à API REST
flow-c-audio       →  Whisper (STT) + chama flow-b + TTS na resposta
flow-d-email       →  sub-workflow de envio de confirmação por Gmail
```

### 5.2 Flow A — Detecção de entrada

```
[Chat Trigger]
    ↓
[IF: type === "audio"]
    → SIM → [Flow C]
    → NÃO → [Flow B] com mensagem de texto diretamente
```

Node `Chat Trigger` configurado com:
- Modo: webhook público
- Aceitar: texto e binário (áudio)

### 5.3 Flow B — Core de IA (function calling)

```
[Set: monta histórico de mensagens]
    ↓
[OpenAI Chat: gpt-4o-mini com functions declaradas]
    ↓
[Switch: qual função foi chamada?]
    ├── buscar_horarios     → [HTTP GET /horarios/disponiveis]
    ├── criar_agendamento   → [HTTP POST /agendamentos] → [Flow D]
    ├── cancelar_agendamento → [HTTP PATCH /agendamentos/:id/cancelar] → [Flow D]
    ├── buscar_pagamentos   → [HTTP GET /pagamentos]
    ├── buscar_paciente     → [HTTP GET /pacientes/:email]
    └── nenhuma função      → resposta direta de saudação/encerramento
         ↓
[Set: formata resposta final]
    ↓
[Respond to Webhook]
```

### 5.4 Functions declaradas ao LLM

```json
[
  {
    "name": "buscar_horarios_disponiveis",
    "description": "Busca horários médicos disponíveis para agendamento",
    "parameters": {
      "type": "object",
      "properties": {
        "data": {
          "type": "string",
          "description": "Data no formato YYYY-MM-DD. Opcional — sem data retorna todos os disponíveis."
        }
      }
    }
  },
  {
    "name": "criar_agendamento",
    "description": "Agenda uma consulta para o paciente em um horário disponível",
    "parameters": {
      "type": "object",
      "properties": {
        "paciente_email": { "type": "string" },
        "horario_id": { "type": "number" }
      },
      "required": ["paciente_email", "horario_id"]
    }
  },
  {
    "name": "cancelar_agendamento",
    "description": "Cancela um agendamento existente",
    "parameters": {
      "type": "object",
      "properties": {
        "agendamento_id": { "type": "number" }
      },
      "required": ["agendamento_id"]
    }
  },
  {
    "name": "buscar_pagamentos",
    "description": "Retorna valores de consulta e formas de pagamento aceitas",
    "parameters": { "type": "object", "properties": {} }
  },
  {
    "name": "buscar_paciente",
    "description": "Busca dados de um paciente pelo email",
    "parameters": {
      "type": "object",
      "properties": {
        "email": { "type": "string" }
      },
      "required": ["email"]
    }
  }
]
```

### 5.5 Flow C — Áudio

```
[Recebe binário do Chat Trigger]
    ↓
[HTTP POST OpenAI /audio/transcriptions (Whisper)]
    ↓
[Set: injeta transcrição como texto]
    ↓
[Chama Flow B com o texto transcrito]
    ↓
[HTTP POST OpenAI /audio/speech (TTS tts-1)]
    ↓
[Respond: retorna arquivo de áudio mp3]
```

Formato de retorno ao Chat: arquivo `.mp3` como attachment ou URL temporária dependendo da configuração do Chat Trigger.

### 5.6 Flow D — Email (sub-workflow)

```
[Execute Workflow Trigger]
    ↓
[Set: monta template por tipo (agendamento|cancelamento)]
    ↓
[Gmail node: envia para paciente.email]
```

Templates:

- **Agendamento:** `Confirmação de consulta — {data_hora} com {medico} | Valor: R$ {valor} | Pagamento: {formas}`
- **Cancelamento:** `Consulta cancelada — {data_hora} com {medico} foi cancelada com sucesso.`

Retry: configurado no node Gmail — 3 tentativas com intervalo de 5s.

### 5.7 Boas práticas nos fluxos

- Todos os nodes com nomes descritivos em português (sem "HTTP Request1")
- Nodes de erro (`Error Trigger`) em cada fluxo para capturar falhas
- Variáveis de ambiente para URLs da API e credenciais (não hardcoded)

---

## 6. Integrações externas

### 6.1 Gmail

- Autenticação: OAuth2 configurado nas credenciais do N8N
- Node: Gmail (nativo N8N)
- Retry: 3 tentativas, intervalo 5s
- Documentação: README com passo a passo do OAuth2 + prints

### 6.2 OpenAI

- LLM: `gpt-4o-mini` via OpenAI Chat node
- STT: `whisper-1` via HTTP Request node (POST /audio/transcriptions)
- TTS: `tts-1` via HTTP Request node (POST /audio/speech), voz `alloy`
- Uma única credencial OpenAI reutilizada nos três nodes
- Retry no TTS: 3 tentativas, intervalo 3s

---

## 7. Diferenciais

| Diferencial | Implementação | Onde |
|---|---|---|
| Testes unitários | Jest — testa cada rota com banco em memória (`:memory:`) | `api/tests/` |
| Function calling | LLM decide qual função chamar com parâmetros corretos | Flow B |
| Retry email | Node Gmail com 3 tentativas + backoff | Flow D |
| Retry TTS | HTTP Request com retry nativo do N8N | Flow C |
| Cache disponibilidade | `node-cache` TTL 60s, invalidação por evento de escrita | `api/src/cache/` |
| Painel de consultas | `GET /painel` → HTML com tabela de agendamentos por status | `api/src/routes/painel.js` |

---

## 8. Infraestrutura local

### 8.1 docker-compose.yml

```yaml
version: '3.8'
services:
  api:
    build: ./api
    ports:
      - "3000:3000"
    volumes:
      - ./api/data:/app/data    # persiste o SQLite
    environment:
      - PORT=3000
      - DB_PATH=/app/data/clinica.db

  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    volumes:
      - ./n8n/data:/home/node/.n8n
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=admin
      - WEBHOOK_URL=http://localhost:5678
```

### 8.2 Variáveis de ambiente da API

```env
PORT=3000
DB_PATH=./data/clinica.db
```

---

## 9. Repositório e entregáveis

### 9.1 Estrutura de pastas

```
/
├── api/
│   ├── src/
│   ├── tests/
│   ├── Dockerfile
│   └── package.json
├── n8n/
│   ├── flow-a-entrada.json
│   ├── flow-b-ai-core.json
│   ├── flow-c-audio.json
│   └── flow-d-email.json
├── postman/
│   └── clinica.collection.json
├── docs/
│   ├── prints/               # evidências de teste
│   └── demo.gif
├── CHECKLIST.md
├── docker-compose.yml
└── README.md
```

### 9.2 Checklist de entregáveis

- [ ] Código da API com seed e testes
- [ ] Banco SQLite com dados iniciais (via seed no boot)
- [ ] 4 fluxos N8N exportados como JSON
- [ ] README com instalação, execução e testes
- [ ] Coleção Postman cobrindo todos os endpoints
- [ ] GIF ou vídeo demonstrando os 4 fluxos principais
- [ ] CHECKLIST.md com cenários testados e evidências

### 9.3 Commits (Conventional Commits)

```
feat: add database schema and seed
feat: add horarios and agendamentos routes
feat: add cache with node-cache (TTL 60s)
feat: add painel route (HTML dashboard)
test: add jest tests for all routes
feat: n8n flow-b ai core with function calling
feat: n8n flow-a entrada detection (text|audio)
feat: n8n flow-c audio pipeline (whisper + tts)
feat: n8n flow-d email confirmation sub-workflow
docs: add README with full setup instructions
docs: add CHECKLIST with test evidence
chore: add docker-compose for local setup
```

---

## 10. README — estrutura mínima

```
## Pré-requisitos
- Docker e Docker Compose
- Conta OpenAI (chave de API)
- Conta Google com Gmail API habilitada

## Instalação
1. Clone o repositório
2. Configure variáveis de ambiente
3. docker-compose up --build

## Configurando credenciais no N8N
- OpenAI: Settings → Credentials → New → OpenAI API
- Gmail: Settings → Credentials → New → Gmail OAuth2
  (passo a passo com prints em /docs/prints/)

## Importando os fluxos N8N
1. Acesse http://localhost:5678
2. Menu → Import from file
3. Importe cada JSON da pasta /n8n/ em ordem (A→B→C→D)

## Testando com Postman
- Importe /postman/clinica.collection.json
- Configure variável BASE_URL=http://localhost:3000

## Rodando os testes
cd api && npm test

## Exemplos de uso
- Chat: http://localhost:5678/webhook/chat
- Painel: http://localhost:3000/painel
```

---

## 11. CHECKLIST.md — estrutura mínima

| # | Cenário | Input | Esperado | Resultado | Status |
|---|---|---|---|---|---|
| 1 | Consultar horários disponíveis | "Quais horários vocês têm?" | Lista com médico, data e hora | ... | ✅ |
| 2 | Agendar consulta | "Quero agendar para João no horário 3" | Confirmação + email enviado | ... | ✅ |
| 3 | Cancelar agendamento | "Cancelar minha consulta 12" | Cancelamento + email enviado | ... | ✅ |
| 4 | Consultar pagamentos | "Quanto custa a consulta?" | Valor e formas de pagamento | ... | ✅ |
| 5 | Entrada por áudio | Áudio com pergunta sobre horários | Resposta em áudio (.mp3) | ... | ✅ |
| 6 | Horário já ocupado | POST /agendamentos com horario ocupado | 409 Conflict | ... | ✅ |
| 7 | Paciente não encontrado | POST /agendamentos com email inválido | 404 Not Found | ... | ✅ |

---

*Spec finalizada — pronta para implementação por fases.*
