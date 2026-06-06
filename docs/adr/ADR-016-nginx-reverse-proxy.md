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
4. **Streaming SSE**: `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 300s`, `chunked_transfer_encoding off`, `gzip off`, `proxy_max_temp_file_size 0` (ver Lessons Learned).
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

## Lessons Learned — SSE buffering em produção (2026-06-06)

### Problema observado

Em produção no Render, o stream LangGraph chegava ao browser em **blocos irregulares** ("trava, cospe texto, trava") — comportamento inexistente no Docker local. O nginx local já tinha `proxy_buffering off`, mas o problema persistia.

### Investigação

Análise da documentação oficial nginx.org e artigos de produção (OneUptime 2025, Medium/DSherwin) revelou **três defaults de proxy que quebram SSE**:

1. **`chunked_transfer_encoding on` (nosso caso)** — nginx pode agrupar múltiplos eventos SSE num único chunk HTTP antes de enviar ao cliente, causando o efeito "burst". O correto para SSE é `off`.
2. **`gzip` ativo** — compressão é incompatível com streaming de eventos; quebra a delimitação `data: ...\n\n`.
3. **`proxy_max_temp_file_size` não zerado** — nginx pode usar arquivo temporário em disco como buffer secundário mesmo com `proxy_buffering off`.

O Render LB (load balancer da plataforma) também foi investigado: confirmado como buffer adicional pela comunidade (threads desde 2022), **sem solução exposta ao usuário**. Remover o nginx não resolve — o Render LB permanece na frente de qualquer serviço público.

### Sobre `X-Accel-Buffering`

`X-Accel-Buffering: no` é um header que o **backend** envia para o nginx local desabilitar seu buffering. Não é um header que nginx deve adicionar para afetar proxies upstream — a direção é inversa. Como já temos `proxy_buffering off`, o header é redundante no nosso caso. Tentativa de adicioná-lo via `add_header` no nginx não teria efeito no Render LB.

### Correção aplicada

No `location` do agente adicionados três diretivas que sobrescrevem o global:

```nginx
chunked_transfer_encoding off;   # impede agrupamento de eventos SSE em chunks HTTP
gzip                      off;   # evita compressão incompatível com text/event-stream
proxy_max_temp_file_size  0;     # zera buffer secundário em disco
```

A diretiva `chunked_transfer_encoding on` permanece no contexto global para o `location /` (UI Next.js), onde chunked é desejável.

### Causa raiz remanescente

O Render LB bufferiza SSE independentemente de qualquer configuração nginx. O comportamento "não fluido" residual em produção é atribuído à **latência geográfica Brasil → Oregon (~160ms/RTT)**, não eliminável por configuração de proxy. Migrar para a região `ohio` ou `virginia` no Render reduziria ~30ms por RTT.

## Referências

- `nginx/nginx.conf.template` — configuração completa
- `nginx/Dockerfile` — imagem Alpine com template
- `docker-compose.yml:37-47` — serviço nginx
- ADR-013: `langgraph dev` como servidor
- ADR-017: segurança da API e token LangGraph
- [How to Configure SSE Through Nginx — OneUptime (2025)](https://oneuptime.com/blog/post/2025-12-16-server-sent-events-nginx/view)
- [Surviving SSE Behind Nginx Proxy Manager — Medium](https://medium.com/@dsherwin/surviving-sse-behind-nginx-proxy-manager-npm-a-real-world-deep-dive-69c5a6e8b8e5)
- [SSE continually buffering — Render Community](https://render.discourse.group/t/sse-continually-buffering/3840)
