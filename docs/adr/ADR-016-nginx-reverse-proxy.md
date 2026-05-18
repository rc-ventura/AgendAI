# ADR-016: Nginx como proxy reverso com autenticação, rate limiting e CORS

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/), [003-professional-chat-ui](../../specs/003-professional-chat-ui/)
**Código**: `nginx/nginx.conf.template`, `nginx/Dockerfile`, `docker-compose.yml:37-47`

---

## Contexto

O agente LangGraph expõe a LangGraph Platform API na porta `8123` internamente na rede Docker. Esta API **não possui autenticação nativa nem rate limiting** — o `langgraph dev` é um servidor de desenvolvimento. O sistema precisa proteger o agente contra acesso não autorizado, limitar taxa de requisições (cada chamada consome tokens OpenAI pagos) e gerenciar CORS para o frontend.

## Decisão

Inserir um **proxy reverso Nginx** (`nginx:1.27-alpine`) como único ponto de entrada público para o agente LangGraph, responsável por:

1. **Autenticação via `x-api-key`**: header validado contra `LANGGRAPH_AUTH_TOKEN`. Falha fechado — se token não configurado, retorna 500.
2. **Rate limiting**: 20 req/min por IP, burst de 10 sem delay (`limit_req zone=agent_limit burst=10 nodelay`).
3. **CORS restrito**: apenas `http://localhost:3002` (Agent UI) autorizado como origem.
4. **Streaming SSE**: `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 300s`, `chunked_transfer_encoding on`.
5. **Preflight OPTIONS**: responde 204 sem encaminhar ao agente.

### Portas expostas e não expostas

| Serviço | Porta container | Bind no host | Exposição | Motivo |
|---------|----------------|-------------|-----------|--------|
| `api` (Node.js) | `3000` | `0.0.0.0:3000` | ✅ Pública | API REST acessível para testes e Postman |
| `agent` (LangGraph) | `8123` | `127.0.0.1:8123` | ⚠️ Localhost | Acesso direto só para LangGraph Studio em dev |
| `nginx` | `8080` | `0.0.0.0:8080` | ✅ Pública | Único ponto de entrada autenticado para o agente |
| `agent-ui-pro` | `3002` | `0.0.0.0:3002` | ✅ Pública | Frontend do paciente |

**Princípio fundamental**: o agente LangGraph **nunca é exposto diretamente**. A porta `8123` no host é bindada em `127.0.0.1` — inacessível da rede externa. Todo tráfego externo passa pelo nginx na `8080`, que aplica autenticação e rate limiting antes de encaminhar ao `agent:8123` na rede Docker interna.

## Alternativas consideradas

### Alternativa A: Expor agente diretamente na 8123

**Por que não escolhido**: `langgraph dev` não tem autenticação. Qualquer pessoa na rede consumiria tokens OpenAI da conta do projeto. Risco financeiro e de segurança inaceitável.

### Alternativa B: Autenticação no código do agente (middleware Python)

**Por que não escolhido**: Exigiria modificar o `langgraph dev` ou escrever FastAPI customizado (descartado no ADR-013). Nginx resolve na camada de infraestrutura, sem alterar código do agente.

### Alternativa C: Traefik ou Caddy

**Por que não escolhido**: Nginx é mais maduro, melhor documentado e a imagem Alpine pesa ~10 MB. Traefik/Caddy adicionam complexidade de configuração desnecessária para um proxy simples de 1 upstream.

## Consequências

### Aceitas
- **Segurança em profundidade**: agente isolado na rede Docker interna; autenticação e rate limit na borda.
- **Proteção de custos**: rate limiting previne consumo descontrolado de tokens OpenAI.
- **CORS gerenciado centralizadamente**: sem duplicação de headers no agente ou no frontend.
- **Imagem leve**: `nginx:1.27-alpine` (~10 MB), inicialização sub-segundo.
- **Configuração como template**: `nginx.conf.template` usa substituição de env vars pelo entrypoint oficial do nginx — sem necessidade de `envsubst` manual.

### Trade-offs assumidos
- **Ponto único de falha**: se o nginx cair, o agente fica inacessível externamente. Aceitável para MVP single-node.
- **Autenticação por token estático**: `x-api-key` é um token compartilhado, não por usuário. Suficiente para demo; produção exigiria JWT ou OAuth2.
- **Rate limit por IP**:在同一 NAT 后多个用户共享限额。Para demo local, irrelevante.

### Condições que invalidam esta decisão
1. **Múltiplos frontends** com origens CORS diferentes — exigiria lógica mais complexa que `map $http_origin`.
2. **Autenticação por usuário** — `x-api-key` estático não escala para multi-tenancy.
3. **Escala horizontal do agente** — nginx precisaria de `upstream` com múltiplos `agent` containers e `ip_hash` para sticky sessions.

## Referências

- `nginx/nginx.conf.template` — configuração completa
- `nginx/Dockerfile` — imagem Alpine com template
- `docker-compose.yml:37-47` — serviço nginx
- ADR-013: `langgraph dev` como servidor
- ADR-017: segurança da API e token LangGraph
