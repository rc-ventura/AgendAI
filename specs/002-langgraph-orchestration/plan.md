# Implementation Plan: LangGraph Medical Scheduling Orchestration

**Branch**: `002-langgraph-orchestration` | **Date**: 2026-05-14 | **Spec**: [spec.md](./spec.md)

---

## Summary

Substituir a orquestração N8N por um `StateGraph` LangGraph v1.0+ em Python, exposto via servidor LangGraph Platform (`langgraph-cli`) e acessível ao paciente pelo Agent UI open-source da LangChain (Next.js). A API REST existente (Node.js + SQLite) permanece inalterada — o grafo a consome como cliente HTTP. LangSmith rastreia automaticamente 100% das execuções. Gmail SMTP substitui o node Gmail do N8N.

---

## Technical Context

**Language/Version**: Python 3.11+ (serviço LangGraph) / Node.js 20 (API REST — inalterada) / Next.js 14+ (Agent UI)

**Primary Dependencies**:
- `langgraph>=1.0` — StateGraph, ToolNode, add_messages
- `langchain-openai` — ChatOpenAI (GPT-4o-mini), OpenAI Whisper, TTS
- `langsmith` — tracing automático (via env vars)
- `langgraph-cli` — servidor LangGraph Platform
- `httpx` — cliente HTTP async para API REST
- `tenacity` — retry para Gmail e TTS
- `pytest`, `pytest-asyncio` — testes

**Storage**: SQLite existente via API REST (sem acesso direto); histórico de conversa em memória por thread (LangGraph checkpointer SQLite local para dev)

**Testing**: `pytest` + `pytest-asyncio`; testes unitários por nó; testes de integração do grafo completo com API REST mockada via `respx`

**Target Platform**: Linux (Docker), macOS (dev local)

**Project Type**: AI agent service (Python) + chat UI (Next.js) + docker-compose

**Performance Goals**: Resposta texto ≤ 10s; resposta áudio (end-to-end) ≤ 30s

**Constraints**: LangGraph ≥ v1.0; Python ≥ 3.11; sem alteração na API REST; sem banco de dados novo

**Scale/Scope**: Demo — 1 container por serviço, sessões independentes por thread

---

## Constitution Check

| Princípio | Status | Nota |
|-----------|--------|------|
| I. AI-Assisted | ✅ Pass | GPT-4o-mini com function calling; LangSmith observa cada decisão |
| I. Claude API | ⚠️ Exceção | Desafio técnico exige OpenAI explicitamente — registrado em Complexity Tracking |
| II. User-Centric | ✅ Pass | Agent UI acessível via browser; 1 ação para enviar mensagem |
| II. WCAG 2.1 AA | ⚠️ Assumido | Agent UI mantido pela LangChain — acessibilidade assumida para demo |
| III. Test-First | ✅ Pass | pytest obrigatório; testes escritos antes da implementação de cada nó |
| IV. P95 < 2s | ⚠️ Exceção | LLM calls network-bound; target ajustado para <10s texto / <30s áudio — registrado |
| IV. Observabilidade | ✅ Pass | LangSmith traça cada nó, tool call e latência |
| V. Simplicidade | ✅ Pass | YAGNI; 1 responsabilidade por nó; sem abstrações antecipadas |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-langgraph-orchestration/
├── plan.md              # Este arquivo
├── research.md          # Phase 0 — decisões técnicas
├── data-model.md        # Phase 1 — entidades e fluxo de dados
├── quickstart.md        # Phase 1 — guia de início rápido
├── contracts/
│   └── langgraph-platform-api.md   # Contrato da LangGraph Platform API
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 — gerado por /speckit-tasks
```

### Source Code

```text
agent/                          # Serviço Python — LangGraph
├── agent/
│   ├── __init__.py
│   ├── graph.py               # StateGraph compilado (entry point para langgraph.json)
│   ├── state.py               # AgendAIState TypedDict
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── input_detector.py  # Nó: detect_input_type
│   │   ├── transcriber.py     # Nó: transcribe_audio (Whisper)
│   │   ├── llm_core.py        # Nó: chat_with_llm (GPT-4o-mini + tools)
│   │   ├── tools.py           # 5 @tool definitions + ToolNode
│   │   ├── email_sender.py    # Nó: send_email (Gmail SMTP + tenacity)
│   │   └── tts.py             # Nó: synthesize_tts (OpenAI TTS)
│   └── api_client.py          # httpx AsyncClient para API REST
├── tests/
│   ├── conftest.py            # fixtures: mock API REST, mock OpenAI
│   ├── test_state.py          # testes do AgendAIState
│   ├── test_nodes.py          # testes unitários por nó
│   └── test_graph.py          # testes de integração do grafo completo
├── langgraph.json             # Configuração LangGraph Platform
├── pyproject.toml             # Dependências + scripts
└── Dockerfile

agent-ui/                       # Fork customizado do langchain-ai/agent-ui (Next.js)
├── components/
│   └── AudioUploadButton.tsx  # Botão de upload + gravação de áudio adicionado
├── .env.local                 # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_GRAPH_ID
└── Dockerfile

docker-compose.yml              # Atualizado: + agent, + agent-ui services
.env.example                    # Atualizado: + LangSmith, + Gmail vars
```

**Structure Decision**: Serviço Python separado em `agent/` para não contaminar a API REST Node.js existente. Agent UI em `agent-ui/` como clone/submodule do repositório oficial LangChain. Docker Compose orquestra ambos.

---

## Complexity Tracking

| Violação | Por que necessário | Alternativa mais simples rejeitada porque |
|----------|-------------------|-------------------------------------------|
| OpenAI em vez de Claude API | Desafio técnico especifica GPT-4o-mini, Whisper, TTS explicitamente | Não é uma escolha — é um requisito do avaliador |
| P95 > 2s para respostas de chat | LLM calls são network-bound por natureza; GPT-4o-mini típico 2-5s | Streaming mitiga UX; não há alternativa para calls de IA |

---

## Caminho Evolutivo — MCP Server (v2)

> Não implementado nesta versão. Documentado como evolução natural pós-entrega.

A API REST (`api/`) pode ser exposta como um **MCP Server** (Model Context Protocol) em uma v2, tornando as ferramentas reutilizáveis por qualquer cliente MCP — não apenas este agente.

**O que mudaria**:

| Componente | v1 (atual) | v2 (MCP) |
|-----------|-----------|---------|
| `api/` Node.js | Apenas REST | REST + MCP Server (`@modelcontextprotocol/sdk`) |
| `agent/` Python | `@tool` + `httpx` | `langchain-mcp-adapters` → MCP Client |
| Tool discovery | Hardcoded em `tools.py` | Dinâmico via `list_tools()` do MCP |
| Novos clientes | Requer reescrever tools | Zero esforço — qualquer MCP client usa |

**Por que não agora**: atrito desproporcionalmente alto para o escopo do desafio — duas camadas extras (MCP transport + adapter), mais pontos de falha, sem ganho funcional visível no demo. O `ToolNode` do LangGraph já exibe cada chamada de ferramenta com input/output completo no LangSmith e Agent UI.

**Quando faz sentido migrar para MCP**:
- Múltiplos agentes precisam consumir as mesmas ferramentas
- Outros sistemas (Claude Desktop, Cursor, etc.) precisam acessar a API diretamente como ferramentas
- A API cresce para >10 endpoints e o contrato precisa de versionamento de tools

---

## Grafo LangGraph — Definição de Nós e Arestas

```
START
  └─► detect_input_type
        ├─ (audio) ──► transcribe_audio ──► chat_with_llm
        └─ (text) ───────────────────────► chat_with_llm
                                                │
                              ┌─────────────────┤
                              │ (tool_call)      │ (resposta direta)
                              ▼                  ▼
                         execute_tools      router_email
                              │               ├─ (email_pending=True) ──► send_email ──► router_audio
                              └──────────────► router_email              └─────────────► router_audio
                                                                   (email_pending=False) ──► router_audio
                                                                                                │
                                                                              ┌─────────────────┤
                                                                              │ (input=audio)    │ (input=text)
                                                                              ▼                  ▼
                                                                        synthesize_tts          END
                                                                              └──────────────► END
```

**Nós com loop**: `chat_with_llm → execute_tools → chat_with_llm` (multi-step tool use até resposta final)

---

## Sequência de Implementação (para /speckit-tasks)

1. **Setup do projeto Python** — `pyproject.toml`, `Dockerfile`, `langgraph.json`
2. **`state.py`** — `AgendAIState` TypedDict com todos os campos
3. **`api_client.py`** — `httpx.AsyncClient` com os 5 métodos (um por tool)
4. **`nodes/tools.py`** — 5 `@tool` decoradas + `ToolNode`
5. **`nodes/input_detector.py`** — detecta `text` vs `audio`
6. **`nodes/transcriber.py`** — Whisper STT
7. **`nodes/llm_core.py`** — `ChatOpenAI` GPT-4o-mini com tools bound
8. **`nodes/email_sender.py`** — Gmail SMTP + tenacity retry
9. **`nodes/tts.py`** — OpenAI TTS
10. **`graph.py`** — `StateGraph` compilado com todos os nós e arestas
11. **Testes** — unitários por nó + integração do grafo
12. **`docker-compose.yml`** — adicionar serviços `agent` e `agent-ui`
13. **Agent UI** — fork + adicionar `AudioUploadButton.tsx` (encode base64 → envia como mensagem com `input_type: "audio"`); reproduzir resposta de áudio recebida (`audio/mpeg`)
14. **`.env.example`** — atualizar com novas variáveis
