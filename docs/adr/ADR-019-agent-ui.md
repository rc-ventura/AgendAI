# ADR-019: Agent UI open-source da LangChain como interface de chat

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/), [003-professional-chat-ui](../../specs/003-professional-chat-ui/)
**Código**: `agent-ui-pro/`

---

## Contexto

O agente LangGraph precisa de uma interface de chat para o paciente interagir. A spec 002 decidiu usar o **Agent UI open-source da LangChain** (`langchain-ai/agent-ui`, Next.js). Na spec 003, o projeto evoluiu para um fork profissional (`agent-ui-pro/`) baseado no `agent-chat-ui` com branding AgendAI, textos em português e suporte a áudio.

## Decisão

Usar o **Agent UI open-source da LangChain** como shell de chat, conectado ao agente LangGraph via `@langchain/langgraph-sdk`. Na spec 003, migrar do `agent-ui` básico para o `agent-chat-ui` (UI mais moderna, shadcn/ui) como `agent-ui-pro/`, portando os componentes de áudio existentes.

## Alternativas consideradas

### Alternativa A: Construir UI do zero (React/Vue/Svelte)

**Por que não escolhido**:
- Exigiria implementar: streaming SSE, gerenciamento de threads, exibição de tool calls intermediárias, histórico de conversa, sidebar de threads — tudo funcionalidade padrão do Agent UI.
- O `@langchain/langgraph-sdk` é o cliente oficial para a LangGraph Platform API — reimplementar sua integração seria redundante.
- Tempo de desenvolvimento estimado: 2-3 semanas vs 1-2 dias usando Agent UI.

### Alternativa B: Chainlit

**Por que não escolhido**: Exige código Python adicional para servir o frontend. Agent UI é Next.js puro — deploy independente, sem acoplar frontend ao backend Python.

### Alternativa C: LangGraph Studio como interface do paciente

**Por que não escolhido**: Ferramenta de desenvolvimento — expõe detalhes internos do grafo, requer LangSmith login, não tem branding customizável. Inadequado para usuário final.

### Alternativa D: Streamlit ou Gradio

**Por que não escolhido**: Frameworks Python para dashboards científicos, não para chat UI profissional. Look & feel inadequado para produto de saúde.

## Consequências

### Aceitas
- **Streaming nativo**: tokens do LLM aparecem progressiveamente, tool calls são exibidas como cards intermediários com input/output.
- **Gerenciamento de threads**: sidebar com histórico de conversas, cada thread com ID persistido na URL (`?threadId=...`).
- **Zero código de integração**: `NEXT_PUBLIC_API_URL` e `NEXT_PUBLIC_ASSISTANT_ID` configuram a conexão com o agente.
- **UI profissional**: shadcn/ui (Radix + Tailwind) — acessível, responsivo, dark mode.
- **Suporte a áudio**: componentes `AudioUploadButton` (gravação + upload) portados do `agent-ui` original.
- **Customização de branding**: textos em português, cores AgendAI (indigo-500), logo e favicon próprios.

### Trade-offs assumidos
- **Dependência de repositório externo**: `agent-chat-ui` é mantido pela LangChain. Updates upstream precisam ser mergeados manualmente. O fork foi desacoplado (`rm -rf .git`) para evitar dependência acidental.
- **Build-time env vars**: `NEXT_PUBLIC_*` são baked no bundle. Mudar URL do agente exige rebuild da imagem.
- **Estado efêmero no cliente**: conversas vivem na memória React (tab-scoped). Fechar a aba = perde o histórico local (o servidor mantém via checkpointer, mas ver ADR-014 sobre perda em restarts).

### Condições que invalidam esta decisão
1. **Requisitos de UI muito específicos** que o Agent UI não comporta — exigiria UI customizada.
2. **LangChain descontinuar o Agent UI** — migrar para Chainlit ou UI própria.
3. **Necessidade de SSR/SEO** — Agent UI é client-side apenas.

## Referências

- `agent-ui-pro/` — fork do `langchain-ai/agent-chat-ui`
- Spec 002: `specs/002-langgraph-orchestration/spec.md:15` — decisão pelo Agent UI
- Spec 003: `specs/003-professional-chat-ui/plan.md` — migração para agent-chat-ui
- `agent-ui-pro/src/components/AudioUploadButton.tsx` — componente de áudio portado
- ADR-016: nginx como proxy (CORS para `localhost:3002`)
