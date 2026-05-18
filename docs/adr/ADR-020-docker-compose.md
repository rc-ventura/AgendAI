# ADR-020: Docker Compose como plataforma de orquestração de containers

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `docker-compose.yml`

---

## Contexto

O AgendAI é composto por 4 serviços independentes (API, agente LangGraph, nginx, Agent UI) que precisam ser orquestrados como uma aplicação coesa. Cada serviço tem sua própria Dockerfile, dependências e variáveis de ambiente. O sistema precisa subir com **um único comando** e funcionar em qualquer máquina com Docker.

## Decisão

Usar **Docker Compose v2** com 4 serviços em rede bridge interna (`agendai-network`), volumes para persistência de dados e healthchecks para ordem de inicialização.

### Serviços e topologia

```
                   ┌──────────────────────────────────────┐
                   │        agendai-network (bridge)       │
                   │                                       │
  host:3000 ───────┤  api:3000          (Node.js/Express)  │
                   │    │ healthcheck                       │
                   │    │ volume: ./data → /app/data        │
                   │    │                                   │
  host:8123 ───────┤  agent:8123        (LangGraph/Python)  │
  (127.0.0.1 only) │    │ env_file: .env                    │
                   │    │ depends_on: api                   │
                   │    │                                   │
  host:8080 ───────┤  nginx:8080        (proxy reverso)     │
                   │    │ depends_on: agent                 │
                   │    │ env: LANGGRAPH_AUTH_TOKEN         │
                   │    │                                   │
  host:3002 ───────┤  agent-ui-pro:3002 (Next.js frontend)  │
                   │      depends_on: nginx                 │
                   │      build args: NEXT_PUBLIC_*         │
                   └──────────────────────────────────────┘
```

### Decisões-chave no compose

1. **Rede bridge dedicada** (`agendai-network`): isola os serviços do host e de outros projetos Docker. Comunicação interna via DNS do Docker (`api`, `agent`, `nginx`).
2. **Volume bind mount** (`./data:/app/data`): SQLite persistido no host. Sobrevive a `docker compose down` (sem `-v`).
3. **Healthcheck na API**: `wget http://localhost:3000/horarios/disponiveis` a cada 30s. Garante que o banco está pronto antes do agente iniciar.
4. **`depends_on`**: ordem de startup — api → agent → nginx → agent-ui-pro. Sem `condition: service_healthy` para manter compatibilidade com Compose v2.
5. **`restart: unless-stopped`**: todos os serviços reiniciam automaticamente em caso de crash, exceto se parados manualmente.
6. **`env_file: .env`** no agente: centraliza todas as credenciais em um arquivo.
7. **Build args no agent-ui-pro**: `NEXT_PUBLIC_*` são injetadas no build do Next.js, baked no bundle.

## Alternativas consideradas

### Alternativa A: Kubernetes (minikube/k3s)

**Por que não escolhido**: Overkill absoluto para 4 containers em single-host. Adiciona complexidade de manifests, ingress, persistent volumes — sem benefício para MVP/demo.

### Alternativa B: Docker Swarm

**Por que não escolhido**: Modo swarm exige `docker stack deploy` e redes overlay. Compose v2 cobre o caso de uso single-host com sintaxe mais simples.

### Alternativa C: Scripts shell + docker run manual

**Por que não escolhido**: Frágil — ordem de startup, redes, volumes e variáveis de ambiente teriam que ser gerenciados manualmente. Compose declara tudo em um arquivo versionado.

### Alternativa D: Podman Compose

**Por que não escolhido**: Docker é o requisito explícito do desafio técnico. Podman seria uma alternativa válida para ambientes sem Docker daemon, mas não é o target.

## Consequências

### Aceitas
- **Single command startup**: `docker compose up --build -d` sobe tudo.
- **Isolamento de rede**: serviços comunicam-se via DNS interno, não por IPs hardcoded.
- **Persistência simples**: volume bind mount — sem necessidade de volumes nomeados ou plugins de storage.
- **Configuração declarativa**: `docker-compose.yml` versionado no git — qualquer dev replica o ambiente.
- **Portas bem definidas**: 3000 (API), 8080 (nginx/agente), 3002 (UI), 8123 (agente localhost).

### Trade-offs
- **Single-host**: sem escala horizontal. Adicionar mais instâncias exigiria orquestrador (K8s/Swarm).
- **Bind mount em vez de volume nomeado**: `./data` é relativo ao diretório do compose. Funciona bem localmente, mas em CI/CD pode exigir paths absolutos.
- **`depends_on` sem health condition**: agente pode iniciar antes da API estar healthy. Mitigado pelo retry no `ApiClient` e healthcheck informativo.
- **Build args baked no frontend**: mudar `NEXT_PUBLIC_API_URL` exige rebuild da imagem `agent-ui-pro`.

### Condições que invalidam
1. **Necessidade de escala horizontal** → migrar para Kubernetes ou Docker Swarm.
2. **Múltiplos hosts** → rede overlay (Swarm) ou K8s com CNI.
3. **Ambiente de produção com SLA** → adicionar `condition: service_healthy` nos `depends_on` e volumes nomeados com backups.

## Referências

- `docker-compose.yml` — definição completa dos 4 serviços
- `api/Dockerfile`, `agent/Dockerfile`, `nginx/Dockerfile` — Dockerfiles por serviço
- `CLAUDE.md:19` — "Everything starts with a single `docker compose up --build -d`"
- ADR-013: `langgraph dev` como servidor
- ADR-016: nginx como proxy reverso
