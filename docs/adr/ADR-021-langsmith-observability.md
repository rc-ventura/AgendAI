# ADR-021: LangSmith como plataforma de observabilidade para tracing do agente

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `.env.example:16-19`, `agent/tests/test_graph.py:176-194`

---

## Contexto

O agente LangGraph executa um grafo com 7 nós, roteamento condicional, tool calls e múltiplas APIs externas (OpenAI, Gmail SMTP). Sem observabilidade, depurar falhas exigiria logs manuais em cada nó — frágil e não escalável.

A spec 002 define observabilidade como requisito explícito (FR-007, US5): *"Toda execução do grafo DEVE ser rastreada automaticamente no LangSmith"*.

## Decisão

Usar **LangSmith** como plataforma de tracing, ativada **100% por variáveis de ambiente**, sem código adicional no grafo. LangGraph integra nativamente com LangSmith — quando `LANGCHAIN_TRACING_V2=true`, cada execução gera uma trace automaticamente.

### Configuração (3 env vars)

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=AgendAI
```

### O que é rastreado automaticamente

| Elemento | Detalhe na trace |
|----------|-----------------|
| **Nós do grafo** | Cada nó como span com latência individual (ex: `chat_with_llm` 3.2s) |
| **Tool calls** | Nome da ferramenta, parâmetros (JSON) e resposta (ex: `buscar_horarios_disponiveis(data="2026-05-20")`) |
| **Decisões do LLM** | Conteúdo da resposta, tool_calls gerados, tokens consumidos |
| **Roteamento condicional** | Caminho percorrido no grafo (arestas condicionais) |
| **Metadados** | `run_name`, `tags`, `thread_id`, latência total, status (success/error) |
| **Erros** | Stack trace completa no nó que falhou, com contexto do estado |

### Metadados customizados via RunnableConfig

```python
from langchain_core.runnables.config import RunnableConfig

config = RunnableConfig(
    run_name="agendamento_paciente_joao",
    tags=["production", "agendamento"],
    metadata={"paciente_email": "joao@email.com"},
    configurable={"thread_id": "thread-123"},
)
result = await graph.ainvoke(state, config=config)
```

O Agent UI injeta `thread_id` automaticamente, correlacionando traces com conversas específicas.

### Teste de tracing

`agent/tests/test_graph.py:176-194` (`test_run_id_present_for_langsmith`) valida que o grafo aceita `RunnableConfig` com `run_name` e `tags`, confirmando que a infraestrutura de tracing funciona mesmo com LLM mockado.

## Alternativas consideradas

### Alternativa A: OpenTelemetry manual
**Por que não**: Exigiria spans manuais em cada nó. LangSmith captura tudo automaticamente. OTel não entende semântica LangChain (tool calls, message types).

### Alternativa B: Logs estruturados locais (JSON)
**Por que não**: Não atende FR-007. Logs não capturam hierarquia de spans nem oferecem visualização de grafo.

### Alternativa C: LangFuse (open-source)
**Por que não**: Alternativa válida, mas LangSmith é o produto oficial LangChain — integração nativa, zero configuração além de env vars.

### Alternativa D: Nenhuma observabilidade
**Por que não**: Violaria FR-007, US5 e o princípio IV da constituição do projeto (*Observability & Reliability*).

## Consequências

### Aceitas
- **Zero código de tracing**: 3 env vars ativam tracing completo.
- **Hierarquia de spans**: trace raiz → nó → tool call → resposta.
- **Correlação com threads**: `thread_id` vincula traces a conversas.
- **Debug visual**: grafo renderizado mostra caminho percorrido (verde = sucesso, vermelho = erro).
- **Comparação lado a lado**: duas execuções para identificar regressões.
- **Feedback humano**: anotações em traces alimentam datasets de fine-tuning.

### Trade-offs
- **Dependência SaaS**: LangSmith indisponível = traces perdidos (não bloqueia agente).
- **Custo**: tier gratuito para dev; produção com alto volume → avaliar custo.
- **Dados externos**: traces contêm mensagens de pacientes. Produção real → compliance LGPD.
- **Sem tracing na API REST**: apenas agente Python é rastreado. API Node.js usa logs JSON locais.

### Condições que invalidam
1. Soberania de dados → LangFuse self-hosted ou OTel + backend local.
2. LangSmith descontinuado → migrar para alternativa.
3. Custo proibitivo → self-hosted.
4. Necessidade de tracing跨 serviço → propagação de `trace_id` via header.

## Referências

- `.env.example:16-19` — env vars do LangSmith
- `agent/tests/test_graph.py:176-194` — teste de tracing
- Spec 002: `specs/002-langgraph-orchestration/spec.md:95-108` — US5
- Research 002: `specs/002-langgraph-orchestration/research.md:109-129` — Decision 4
- LangSmith docs: <https://docs.smith.langchain.com>
