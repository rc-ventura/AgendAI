# ADR-015: LangGraph como orquestrador de IA em substituição ao n8n

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/graph.py`, `agent/agent/nodes/`

---

## Contexto

A versão inicial do AgendAI (spec 001) usava **n8n self-hosted** como orquestrador dos fluxos de atendimento médico. Quatro workflows JSON (`flow-a-entrada.json`, `flow-b-ai-core.json`, `flow-c-audio.json`, `flow-d-email.json`) implementavam: detecção de modalidade (texto/áudio), classificação de intenção via GPT-4o-mini com function calling, chamadas à API REST, pipeline de áudio (Whisper + TTS) e envio de e-mail transacional via Gmail.

Durante a evolução para a spec 002, o n8n foi **totalmente substituído** por um agente LangGraph em Python. Os workflows JSON antigos permanecem apenas como referência histórica.

## Decisão

Substituir o n8n por um **StateGraph LangGraph v1.0+ em Python**, exposto via LangGraph Platform (`langgraph dev`), mantendo a API REST Node.js inalterada como backend de dados.

## Alternativas consideradas

### Alternativa A: Manter n8n (status quo da spec 001)

**Por que não escolhido**:
- **Observabilidade limitada**: n8n não oferece tracing nativo de decisões do LLM. LangSmith integra-se automaticamente com LangGraph, rastreando cada nó, tool call e latência sem código adicional.
- **Testabilidade**: workflows n8n são arquivos JSON — não há como escrever testes unitários para nós individuais. LangGraph permite `pytest` por nó e testes de integração do grafo completo com API mockada via `respx`.
- **Versionamento**: JSON de workflow do n8n é opaco a diffs — alterar um nó gera mudanças em UUIDs e posições de canvas. Código Python em `nodes/` é limpo, revisável em PR e semanticamente versionável.
- **Flexibilidade de roteamento**: n8n usa switch nodes manuais para branching. LangGraph oferece `add_conditional_edges` com funções Python puras — lógica de roteamento é código testável, não configuração visual.
- **Loop de tool calling**: n8n exige HTTP Request nodes encadeados manualmente para multi-step tool use. LangGraph implementa `chat_with_llm → execute_tools → chat_with_llm` como loop nativo do grafo, com `ToolNode` despachando automaticamente.
- **Custo operacional**: n8n self-hosted adiciona ~500 MB à imagem Docker (Node.js runtime completo + dependências). O serviço Python do LangGraph é significativamente mais leve (~200 MB com `python:3.11-slim`).
- **Ecossistema**: LangGraph é o runtime nativo para agentes LangChain. Usar n8n como intermediário introduz uma camada de tradução desnecessária entre o LLM e as ferramentas.

### Alternativa B: CrewAI ou AutoGen

**Por que não escolhido**: Frameworks multi-agente são overkill para um assistente único de agendamento. LangGraph com `StateGraph` oferece o nível exato de controle necessário — nem menos (n8n), nem mais (multi-agente).

### Alternativa C: FastAPI customizado sem LangGraph

**Por que não escolhido**: Reimplementaria `StateGraph`, `ToolNode`, checkpointer e streaming do zero. LangGraph já fornece essas primitivas como biblioteca madura e testada.

## Consequências

### Aceitas

- **Observabilidade completa**: LangSmith rastreia 100% das execuções automaticamente — cada nó, tool call, decisão de roteamento e latência.
- **Testabilidade**: `pytest` + `pytest-asyncio` permitem testes unitários por nó e testes de integração do grafo completo.
- **Streaming nativo**: tokens do LLM e resultados de tools são streamed para o Agent UI via SSE, sem configuração adicional.
- **Código versionável**: lógica de negócio em Python puro — diffs limpos, revisão de PR semanticamente significativa.
- **Manutenção simplificada**: 1 linguagem para IA (Python) + 1 para API (Node.js), cada uma no seu ecossistema natural.

### Trade-offs assumidos

- **Perda do editor visual**: n8n oferece canvas drag-and-drop para não-desenvolvedores. LangGraph exige proficiência em Python. Aceitável para um time de engenharia.
- **Reimplementação de 4 workflows**: os fluxos A (entrada), B (IA core), C (áudio) e D (e-mail) foram reescritos como nós Python. Custo único de migração, amortizado pela melhor manutenibilidade.
- **Perda de conectores nativos do n8n**: Gmail, HTTP Request e outros nodes do n8n tinham UI de configuração. Substituídos por `smtplib` + `httpx` + `tenacity` — mais código, mas mais controle.

### Condições que invalidam esta decisão

1. **Time sem proficiência em Python** — se a equipe for exclusivamente Node.js, voltar ao n8n ou usar `langgraph-js` (JavaScript) pode ser mais adequado.
2. **Requisito de low-code** — se usuários de negócio precisarem modificar fluxos sem envolver engenharia, n8n volta a ser relevante.
3. **LangGraph deprecado ou descontinuado** — migrar para o próximo runtime de agentes do ecossistema LangChain.

## Referências

- Spec 001: `specs/001-n8n-medical-scheduling/plan.md` — arquitetura original com n8n
- Spec 002: `specs/002-langgraph-orchestration/plan.md` — decisão de migração
- Research 002: `specs/002-langgraph-orchestration/research.md` — análise detalhada das alternativas
- ADR-013: `langgraph dev` como servidor do agente
- ADR-014: checkpointer in-memory para MVP
