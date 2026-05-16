# Quickstart: AgendAI — LangGraph Orchestration

**Pré-requisitos**: Docker 24+, Docker Compose v2, Python 3.11+ (testes locais), Node.js 20+ (testes UI)

---

## 1. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Editar `.env` com suas credenciais:

```env
# Obrigatório — LLM, Whisper, TTS
OPENAI_API_KEY=sk-...

# Opcional — observabilidade no LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=AgendAI

# Opcional — notificações por e-mail
# Gerar em: myaccount.google.com → Segurança → Senhas de app
GMAIL_USER=clinica@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

> `API_BASE_URL` não precisa ser editada — já está configurada como `http://api:3000` dentro do Docker Compose.

---

## 2. Subir todos os serviços

```bash
docker compose up --build -d
```

Verificar status:
```bash
docker compose ps
```

Serviços disponíveis:

| Serviço | URL | Descrição |
|---------|-----|-----------|
| API REST | http://localhost:3000 | Backend médico (Node.js + SQLite) |
| Chat UI | http://localhost:3001 | Interface de chat do paciente |
| LangGraph Server | http://localhost:8080 | API do agente (via proxy nginx) |
| Painel | http://localhost:3000/painel | Dashboard HTML de agendamentos |

---

## 3. Testar os 5 fluxos do desafio

### Fluxo 1 — Consultar horários
Acesse http://localhost:3001 e envie:
```
Quais horários disponíveis para esta semana?
```
Esperado: lista com médico, data e hora.

### Fluxo 2 — Agendar consulta
```
Quero agendar uma consulta para joao@email.com no horário 3
```
Esperado: confirmação + e-mail enviado (se GMAIL configurado).

### Fluxo 3 — Cancelar agendamento
```
Cancelar minha consulta 1
```
Esperado: confirmação de cancelamento + e-mail.

### Fluxo 4 — Valores e formas de pagamento
```
Quanto custa a consulta e quais formas de pagamento vocês aceitam?
```
Esperado: valor em R$ + formas (PIX, Cartão, Dinheiro).

### Fluxo 5 — Mensagem de áudio
1. Clique no botão 🎙 e grave uma pergunta, ou clique em 📎 e envie um `.mp3`
2. Esperado: resposta em texto com o conteúdo da resposta do agente

---

## 4. Verificar agendamentos no painel

```bash
open http://localhost:3000/painel
```

Mostra tabela HTML com todos os agendamentos e status (ativo/cancelado).

---

## 5. Rodar testes automatizados

### Agente Python (28 testes)
```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

### UI Frontend (Vitest + MSW)
```bash
cd agent-ui
npm install
npm test
```

### API REST (34 testes Jest)
```bash
cd api
npm install
npm test
```

---

## 6. Observabilidade com LangSmith

Com `LANGCHAIN_TRACING_V2=true` e `LANGCHAIN_API_KEY` configurados:

1. Acesse [smith.langchain.com](https://smith.langchain.com)
2. Abra o projeto **AgendAI**
3. Cada mensagem aparece como uma trace com todos os nós: `detect_input_type → chat_with_llm → execute_tools → ...`

---

## 7. LangGraph Studio (debug do grafo)

Para inspecionar o grafo visualmente em desenvolvimento:

```bash
cd agent
source .venv/bin/activate
langgraph dev --port 8123

# Abrir no navegador:
# https://smith.langchain.com/studio/?baseUrl=http://localhost:8123
```

---

## 8. Desenvolvimento local sem Docker

```bash
# Terminal 1 — API REST
cd api && npm run dev          # http://localhost:3000

# Terminal 2 — Agente LangGraph
cd agent
source .venv/bin/activate
API_BASE_URL=http://localhost:3000 langgraph dev --port 8123

# Terminal 3 — Chat UI
cd agent-ui
cp .env.local.example .env.local
npm install && npm run dev     # http://localhost:3001
```

---

## Estrutura do projeto

```
AgendAI/
├── api/                        # API REST Node.js + SQLite
├── agent/                      # Agente LangGraph Python
│   ├── agent/
│   │   ├── graph.py            # StateGraph compilado
│   │   ├── state.py            # AgendAIState TypedDict
│   │   ├── api_client.py       # httpx client → API REST
│   │   └── nodes/
│   │       ├── input_detector.py
│   │       ├── transcriber.py  # Whisper STT
│   │       ├── llm_core.py     # GPT-4o-mini + tools
│   │       ├── tools.py        # 5 @tool functions
│   │       ├── tool_result_processor.py
│   │       ├── email_sender.py # Gmail SMTP + tenacity
│   │       └── tts.py          # OpenAI TTS + tenacity
│   ├── tests/                  # 28 testes (pytest)
│   ├── langgraph.json
│   └── pyproject.toml
├── agent-ui/                   # Chat UI Next.js 14
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx
│   │   │   └── AudioUploadButton.tsx
│   │   ├── lib/langgraph.ts    # SDK wrapper
│   │   └── tests/              # Vitest + MSW
│   └── Dockerfile
├── nginx/                      # Reverse proxy + auth para o LangGraph server
├── docker-compose.yml          # api + agent + agent-ui + nginx
├── .env.example
└── README.md
```
