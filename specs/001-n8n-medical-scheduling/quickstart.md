# Quickstart: N8N Medical Scheduling Automation

**Público-alvo**: Avaliador técnico executando o projeto pela primeira vez.
**Tempo estimado de setup**: ~15 minutos.

---

## Pré-requisitos

| Ferramenta    | Versão  | Verificação                  |
|---------------|---------|------------------------------|
| Docker        | ≥ 24    | `docker --version`           |
| Docker Compose| v2      | `docker compose version`     |
| Node.js       | 20 LTS  | Apenas para rodar testes unitários localmente |
| Conta OpenAI  | —       | Chave de API necessária (LLM + Whisper + TTS) |
| Conta Google  | —       | Gmail API habilitada (OAuth2) |

---

## Passo 1 — Clonar e Configurar Variáveis

```bash
git clone <url-do-repositorio>
cd AgendAI
cp .env.example .env
```

Editar `.env`:

```env
# OpenAI (LLM, Whisper, TTS)
OPENAI_API_KEY=sk-...

# API
PORT=3000
DB_PATH=/app/data/clinica.db
```

> As credenciais do Gmail são configuradas **diretamente no N8N** (passo 3) — não
> precisam estar no `.env` da API.

---

## Passo 2 — Subir os Serviços

```bash
docker compose up --build -d
```

Isso inicia:
- `api` — Express na porta `3000`; seed automático na primeira execução.
- `n8n` — N8N na porta `5678` (admin/admin por padrão).

Verificar:
```bash
docker compose ps
curl http://localhost:3000/horarios/disponiveis
```

Esperado: array JSON com 10 horários disponíveis.

---

## Passo 3 — Configurar Credenciais no N8N

1. Acessar `http://localhost:5678` e criar conta.
2. **Settings → Credentials → New → OpenAI API**
   - Inserir `OPENAI_API_KEY`.
3. **Settings → Credentials → New → Gmail OAuth2 API**
   - Seguir o passo a passo OAuth2 com prints em `docs/prints/gmail-setup/`.
   - Escopos necessários: `https://www.googleapis.com/auth/gmail.send`

---

## Passo 4 — Importar os Fluxos N8N

1. No N8N: **Menu → Import from file**.
2. Importar na ordem:
   1. `n8n/flow-a-entrada.json`
   2. `n8n/flow-b-ai-core.json`
   3. `n8n/flow-c-audio.json`
   4. `n8n/flow-d-email.json`
3. Abrir cada flow e associar as credenciais OpenAI e Gmail cadastradas no passo 3.
4. Verificar que `API_BASE_URL` nos nodes HTTP Request aponta para `http://api:3000`.
5. **Ativar** cada workflow (toggle no canto superior direito).
6. Anotar a URL do webhook: `http://localhost:5678/webhook/chat`

---

## Passo 5 — Verificar com Postman

1. Importar `postman/clinica.collection.json`.
2. Definir variável de coleção `BASE_URL = http://localhost:3000`.
3. Executar **GET /horarios/disponiveis** → esperar `200 OK` com lista.
4. Executar **POST /agendamentos** com body da coleção → esperar `201 Created`.
5. Verificar e-mail de confirmação na caixa do paciente.
6. Executar **PATCH /agendamentos/:id/cancelar** → esperar `200` com `status: cancelado`.
7. Verificar que **GET /horarios/disponiveis** volta a listar o horário liberado.

---

## Passo 6 — Testar o Chat (Texto)

```bash
curl -X POST http://localhost:5678/webhook/chat \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text",
    "text": "Quais os horários disponíveis para amanhã?"
  }'
```

Esperado: resposta JSON com lista de horários em linguagem natural.

---

## Passo 7 — Testar o Chat (Áudio)

```bash
# Converter arquivo de áudio para base64 (ou enviar binário direto via Chat Trigger)
curl -X POST http://localhost:5678/webhook/chat \
  -F "type=audio" \
  -F "file=@sample-audio/pergunta.ogg"
```

Esperado: arquivo `.mp3` de resposta ou fallback em texto se TTS indisponível.

---

## Passo 8 — Rodar Testes Unitários

```bash
cd api
npm install
npm test
```

Esperado: todos os testes passam (horarios, agendamentos, pagamentos).

---

## Painel de Visualização (Diferencial)

Acessar no navegador: `http://localhost:3000/painel`

Exibe tabela HTML com todos os agendamentos ordenados por data, com status
colorido (ativo / cancelado).

---

## Resetar o Banco

```bash
docker compose down -v
docker compose up --build -d
```

O volume `data/` é removido e o seed reexecutado na próxima inicialização.

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
|---------|---------------|---------|
| `curl /horarios` retorna connection refused | Container da API não iniciou | `docker compose logs api` |
| Fluxo N8N não responde | Workflow não ativado | Ativar toggle no N8N UI |
| E-mails não chegam | Token Gmail expirado ou escopo incorreto | Reconfigurar credencial Gmail no N8N (passo 3) |
| Resposta de áudio é texto | TTS falhou ou `OPENAI_API_KEY` inválida | Verificar chave no `.env` e logs do N8N |
| `409 Horário não disponível` no POST | Horário já agendado no seed | Usar `horario_id` de `GET /horarios/disponiveis` |
| `404 Paciente não encontrado` | E-mail não existe no seed | Usar e-mail da lista em `GET /pacientes` (via Postman) |
