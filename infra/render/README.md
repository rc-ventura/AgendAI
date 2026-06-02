# Render Deploy — AgendAI Fase 1

## Pré-requisitos externos (criar ANTES do primeiro deploy)

Todos os serviços abaixo têm free tier suficiente para portfólio.

### 1. Neon Postgres (neon.tech)

Crie **um projeto** com **dois bancos de dados**:

| Banco | Para quê | Env var |
|---|---|---|
| `agendai_app` | Dados da API (médicos, pacientes, agendamentos) | `DATABASE_URL` |
| `agendai_lg` | Estado do agente (checkpoints/threads) | `DATABASE_URI` |

Connection string no formato:
```
postgres://user:pass@ep-xxx.us-east-2.aws.neon.tech/agendai_app?sslmode=require
```

### 2. Upstash Redis (upstash.com)

Crie um banco Redis (free: 10k cmd/dia). Copie a URL no formato:
```
rediss://default:xxx@xxx.upstash.io:6379
```
→ `REDIS_URI`

### 3. LangSmith (smith.langchain.com)

Crie uma conta no plano **Developer** (free: 5k traces/mês).

No menu Settings → API Keys, gere:
- **License key** (começa com `lsv2_sk_`) → `LANGSMITH_API_KEY` (obrigatório para o langgraph-server)
- **Tracing key** (começa com `lsv2_pt_`) → `LANGCHAIN_API_KEY`

### 4. GitHub Container Registry (GHCR)

O `deploy.yml` usa `GITHUB_TOKEN` (built-in) para publicar as imagens.
Adicione apenas:
- `RENDER_DEPLOY_HOOK` — webhook do Render (próximo passo)

---

## Deploy no Render

### Passo 1 — Conectar o repositório

1. Render Dashboard → **New Blueprint Instance**
2. Selecione o repositório GitHub e o arquivo `infra/render/render.yaml`
3. Render criará os 4 serviços automaticamente

### Passo 2 — Definir as env vars secretas (sync: false)

No Render Dashboard, para cada serviço, configure:

**agendai-nginx:**
```
LANGGRAPH_AUTH_TOKEN = <token que você gerou — mesma string que o NEXT_PUBLIC_LANGGRAPH_API_KEY>
```

**agendai-api:**
```
DATABASE_URL = postgres://...@.../agendai_app?sslmode=require
```

**agendai-langgraph:**
```
DATABASE_URI          = postgres://...@.../agendai_lg?sslmode=require
REDIS_URI             = rediss://...
LANGSMITH_API_KEY     = lsv2_sk_...
LANGCHAIN_API_KEY     = lsv2_pt_...
OPENAI_API_KEY        = sk-...
GMAIL_USER            = (opcional)
GMAIL_APP_PASSWORD    = (opcional)
```

**agendai-ui** (Build Args no Render — seção "Environment" → "Build Args"):
```
NEXT_PUBLIC_API_URL              = https://agendai-nginx.onrender.com
NEXT_PUBLIC_ASSISTANT_ID         = agendai_agent
NEXT_PUBLIC_LANGGRAPH_API_KEY    = <mesmo valor do LANGGRAPH_AUTH_TOKEN>
```

> **Atenção**: `NEXT_PUBLIC_*` são baked no build time.
> Se você mudar a URL do nginx, precisará fazer rebuild da UI.

### Passo 3 — Deploy hook para o CI/CD

1. No serviço `agendai-nginx` (ou em qualquer dos 4), vá em Settings → Deploy Hook
2. Copie a URL do webhook
3. No repositório GitHub → Settings → Secrets → New repository secret:
   - Nome: `RENDER_DEPLOY_HOOK`
   - Valor: a URL copiada

### Passo 4 — Primeiro deploy

O `deploy.yml` roda automaticamente no merge para `main`.
Para o primeiro deploy manual:

```bash
# Na raiz do repositório:
# 1. Build da imagem do agente
cd agent
pip install -U "langgraph-cli"
langgraph build -t ghcr.io/SEU_USUARIO/agendai-agent:latest --no-pull
docker push ghcr.io/SEU_USUARIO/agendai-agent:latest

# 2. Atualizar render.yaml com o seu usuário GitHub
# (substituir GITHUB_OWNER na linha image.url)

# 3. Disparar o deploy
curl -fsSL -X POST "$RENDER_DEPLOY_HOOK"
```

---

## Verificação pós-deploy

Consulte `specs/004-fase-1-deploy/quickstart.md` §5 para os 7 checks de verificação.

Checklist rápido:
- [ ] `https://agendai-nginx.onrender.com` carrega a chat UI
- [ ] Conversa de texto funciona end to end
- [ ] Áudio (mic ou upload) funciona
- [ ] Streaming não trava (resposta chega token a token)
- [ ] Reiniciar `agendai-langgraph` → threads persistem
- [ ] `agendai-api` e `agendai-langgraph` não têm URL pública
- [ ] Trace aparece no LangSmith dashboard
