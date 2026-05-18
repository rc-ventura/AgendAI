# ADR-017: Segurança da API REST e token de credencial do LangGraph

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `api/src/app.js`, `nginx/nginx.conf.template`, `.env.example`

---

## Contexto

O sistema AgendAI possui duas superfícies de ataque distintas que exigem estratégias de segurança diferentes:

1. **API REST** (`api/`, porta 3000): backend de dados com endpoints de agendamento, pacientes, horários e pagamentos. Consumida pelo agente LangGraph (rede interna) e potencialmente por clientes externos.
2. **LangGraph Platform API** (`agent/`, porta 8123): API de execução do grafo de IA. Consumida pelo Agent UI (porta 3002) e pelo LangGraph Studio (dev).

Ambas precisam de proteção, mas com mecanismos adequados a cada perfil de ameaça.

## Decisão

### API REST (Node.js/Express)

Proteção em duas camadas:

1. **Rate limiting no Express** (`express-rate-limit`): 100 req / 15 min por IP. Resposta 429 com mensagem em português. Desabilitado em ambiente de teste para evitar vazamento de contadores entre test suites.
2. **Request timeout**: 30 segundos — conexões que excederem recebem 503.
3. **Timeout HTTP no ApiClient** (`httpx`): 10 segundos por chamada do agente à API.

A API REST **não exige autenticação por token** no MVP porque:
- Roda em rede Docker interna (consumida apenas pelo agente).
- Dados são fictícios de demonstração (seed com 3 médicos, 5 pacientes).
- Adicionar auth agora seria overengineering para o escopo do desafio.

### LangGraph Agent (Python/LangGraph)

Autenticação **delegada ao nginx** (ADR-016):

1. **`LANGGRAPH_AUTH_TOKEN`**: token secreto definido no `.env`, injetado no nginx e no `agent-ui-pro`.
2. **Header `x-api-key`**: exigido em toda requisição ao nginx na porta `8080`. Validado contra `LANGGRAPH_AUTH_TOKEN`.
3. **Falha fechado (fail-closed)**: se `LANGGRAPH_AUTH_TOKEN` não estiver definido, nginx retorna 500 em vez de aceitar requisições sem header.
4. **Sem fallback**: se `x-api-key` ausente ou incorreto → 401 Unauthorized.

Fluxo de autenticação:

```
agent-ui-pro (3002)                nginx (8080)                   agent (8123)
      │                                │                               │
      │ POST /runs/stream              │                               │
      │ x-api-key: <token>             │                               │
      │──────────────────────────────►│                               │
      │                                │ valida x-api-key              │
      │                                │ aplica rate limit (20r/m)     │
      │                                │──────────────────────────────►│
      │                                │                               │ executa grafo
      │                                │◄──────────────────────────────│
      │◄──────────────────────────────│                               │
      │ SSE stream de tokens           │                               │
```

### Segredos e configuração

| Variável | Escopo | Onde usada | Proteção |
|----------|--------|-----------|----------|
| `OPENAI_API_KEY` | `agent` | LLM, Whisper, TTS | `.env` (gitignored) |
| `LANGGRAPH_AUTH_TOKEN` | `nginx`, `agent-ui-pro` | Auth do proxy | `.env` (gitignored) |
| `LANGCHAIN_API_KEY` | `agent` | LangSmith tracing | `.env` (gitignored) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | `agent` | SMTP e-mail | `.env` (gitignored) |

Todas as credenciais seguem o princípio de **nunca hardcoded, nunca commitadas**. O `.env.example` documenta todas as variáveis necessárias sem valores reais.

## Alternativas consideradas

### Alternativa A: JWT ou OAuth2 na API REST

**Por que não escolhido**: Adicionaria complexidade de auth server, refresh tokens e gerenciamento de sessão. Desproporcional para um MVP com dados fictícios.

### Alternativa B: mTLS entre serviços

**Por que não escolhido**: Exigiria PKI (gerar/rotacionar certificados), adicionando complexidade operacional sem ganho de segurança real em single-host Docker.

### Alternativa C: API key no próprio agente (sem nginx)

**Por que não escolhido**: `langgraph dev` não suporta middleware de auth nativo. Implementar exigiria FastAPI customizado (descartado no ADR-013).

## Consequências

### Aceitas
- **Defesa em profundidade**: rate limit na API + auth no proxy + timeout em todas as camadas.
- **Configuração centralizada**: todos os segredos no `.env`, consumidos pelos serviços que precisam.
- **Fail-closed por padrão**: token ausente = serviço recusa, nunca aceita silenciosamente.
- **Baixo acoplamento**: segurança na infraestrutura (nginx), não no código do agente.

### Trade-offs assumidos
- **API REST sem autenticação**: aceitável para MVP com dados fictícios e rede interna. Em produção, adicionar API key ou JWT.
- **Token compartilhado**: mesmo `LANGGRAPH_AUTH_TOKEN` para todos os clientes. Em produção, usar tokens por cliente ou OAuth2.
- **Sem HTTPS**: `docker compose` local não exige TLS. Em deploy público, adicionar certificado no nginx ou usar Cloudflare.

### Condições que invalidam esta decisão
1. **API REST exposta publicamente** — exigiria autenticação imediata.
2. **Dados reais de pacientes** — exigiria criptografia em trânsito (TLS) e em repouso, + auth.
3. **Múltiplos clientes do agente** — token compartilhado não escala; migrar para API keys por cliente.

## Referências

- `api/src/app.js:11-18` — rate limiter do Express
- `nginx/nginx.conf.template:31-44` — validação do `x-api-key`
- `.env.example` — documentação de todas as credenciais
- ADR-016: nginx como proxy reverso
