# ADR-018: Arquitetura polyglot — API REST em Node.js + Agente de IA em Python

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `api/` (Node.js), `agent/` (Python)

---

## Contexto

O AgendAI é composto por dois serviços com responsabilidades radicalmente diferentes:

1. **API REST** (`api/`): CRUD de médicos, pacientes, horários, agendamentos e pagamentos. Operações síncronas, transacionais, com SQLite.
2. **Agente de IA** (`agent/`): grafo LangGraph com LLM (GPT-4o-mini), Whisper (STT), TTS, tool calling e envio de e-mail. Operações assíncronas, streaming, com múltiplas chamadas a APIs externas.

Cada domínio tem um ecossistema de bibliotecas e convenções radicalmente diferente. A questão é: unificar em uma linguagem ou manter duas?

## Decisão

Manter **duas linguagens**, cada uma no seu ecossistema natural:

- **Node.js 20 + Express 4** para a API REST.
- **Python 3.11 + LangGraph v1.0+** para o agente de IA.

Comunicação entre serviços via **HTTP REST** (rede Docker interna `agendai-network`), usando `httpx.AsyncClient` no lado Python.

## Alternativas consideradas

### Alternativa A: Unificar tudo em Python (FastAPI + LangGraph)

**Por que não escolhido**:
- O ecossistema Python para APIs REST (FastAPI, SQLAlchemy, Pydantic) é maduro, mas exigiria reescrever toda a API existente.
- A API já estava implementada e testada em Node.js quando o agente foi introduzido na spec 002.
- `better-sqlite3` (síncrono, sem driver externo) é uma biblioteca Node.js sem equivalente direto em Python com a mesma simplicidade.
- Migrar a API para Python atrasaria a entrega sem ganho funcional — o agente consome a API como cliente HTTP, independente da linguagem.

### Alternativa B: Unificar tudo em Node.js (Express + langgraph-js)

**Por que não escolhido**:
- `langgraph-js` (JavaScript/TypeScript) existe, mas é menos maduro que o Python.
- O ecossistema de IA em Python (LangChain, LangGraph, LangSmith, OpenAI SDK) é o "first-class citizen" — documentação, exemplos e suporte da comunidade são superiores.
- A spec 002 explicitamente decidiu Python para o agente: *"Qual linguagem para o serviço LangGraph? → Python (LangGraph Python v1.0+)"*.
- Ferramentas como Whisper e TTS têm SDKs Python oficiais da OpenAI; os wrappers Node.js são comunitários.

### Alternativa C: TypeScript no backend com Bun

**Por que não escolhido**: Adicionaria uma terceira linguagem/runtime sem benefício claro. Node.js 20 LTS já cobre a API REST adequadamente.

## Consequências

### Aceitas
- **Cada domínio na sua linguagem ótima**: Node.js/Express para APIs REST (event loop, I/O não-bloqueante, ecossistema npm maduro para web). Python para IA/ML (LangChain, LangGraph, OpenAI SDK, LangSmith).
- **Desacoplamento forte**: serviços comunicam-se via HTTP REST — contrato bem definido, independente de linguagem.
- **Evolução independente**: API REST pode migrar para TypeScript, Bun ou Deno sem afetar o agente. Agente pode migrar para `langgraph-js` ou outro runtime sem afetar a API.
- **Testabilidade isolada**: testes da API (`jest` + `supertest`) e do agente (`pytest` + `pytest-asyncio`) rodam em processos separados, sem interferência.

### Trade-offs assumidos
- **Duas linguagens para manter**: o time precisa de proficiência em Node.js e Python. Custo real, mas cada linguagem é usada no seu domínio natural — não há sobreposição de responsabilidades.
- **Duas Dockerfiles**: `api/Dockerfile` (Node.js) e `agent/Dockerfile` (Python). Builds sequenciais no `docker compose up --build`.
- **Sem type-safety跨服务**: o contrato HTTP não é tipado. Mitigado por testes de integração que validam o formato das respostas.
- **Latência de rede**: chamadas HTTP entre containers adicionam ~1-2ms. Irrelevante comparado à latência do LLM (2-5s).

### Condições que invalidam esta decisão
1. **Time exclusivamente Node.js** — considerar `langgraph-js` para o agente.
2. **Time exclusivamente Python** — migrar API para FastAPI.
3. **Requisitos de latência ultra-baixa** entre serviços — considerar gRPC ou IPC.
4. **Necessidade de type-safety跨服务** — adicionar contrato OpenAPI + geração de tipos.

## Referências

- `api/src/app.js` — factory `createApp(db)` com Express
- `agent/agent/api_client.py` — `httpx.AsyncClient` consumindo API REST
- `agent/agent/graph.py` — StateGraph com nós Python
- `docker-compose.yml:4-35` — serviços `api` e `agent` na rede `agendai-network`
- Spec 002 clarifications: decisão explícita por Python para o agente
