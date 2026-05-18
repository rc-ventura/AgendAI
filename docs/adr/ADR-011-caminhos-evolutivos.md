# ADR-011: Caminhos evolutivos da arquitetura AgendAI (v2+)

**Status**: Proposed
**Data**: 2026-05-17
**Spec relacionada**: [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: —

---

## Contexto

O MVP atual do AgendAI entrega o ciclo completo de agendamento médico com IA (texto + áudio + e-mail), mas opera com diversas simplificações conscientes documentadas nos ADRs 012-021. Este ADR mapeia os **caminhos evolutivos naturais** para quando o projeto for promovido a produção real — cada item é uma decisão arquitetural futura, não um compromisso imediato.

## Decisão

Manter este ADR como **documento vivo de planejamento evolutivo**, revisado a cada nova spec. Cada caminho abaixo deve gerar seu próprio ADR quando for priorizado para implementação.

---

## Caminhos evolutivos

### 1. Human-in-the-loop — confirmação de ações críticas pelo usuário

**Problema atual**: o agente executa `criar_agendamento` e `cancelar_agendamento` sem confirmação explícita do paciente. O LLM decide sozinho quando agendar.

**Evolução proposta**: adicionar um nó `await_human_approval` no grafo que pausa a execução e exige clique de "Confirmar" do paciente no Agent UI antes de efetivar agendamentos e cancelamentos.

```python
# grafo evolutivo
builder.add_node("await_human_approval", human_approval_node)
builder.add_conditional_edges(
    "await_human_approval",
    lambda state: "execute_tools" if state["human_approved"] else END
)
```

**Benefícios**: segurança contra alucinações do LLM em ações destrutivas; compliance com regulação de saúde (LGPD exige consentimento explícito).

**Dependências**: `interrupt` API do LangGraph v1.0+; modificação no Agent UI para renderizar diálogo de confirmação.

---

### 2. Agente multimodal com real-time audio — substituir pipeline Whisper → TTS

**Problema atual**: o pipeline de áudio atual é sequencial e lento — Whisper transcreve (~2-5s) → LLM processa (~3-5s) → TTS sintetiza (~2-3s). Latência total típica: 10-15s para resposta de áudio. LangSmith já demonstrou esse gargalo nas traces.

**Evolução proposta**: substituir `transcriber.py` + `tts.py` por um modelo multimodal nativo (GPT-4o `gpt-4o-audio-preview` ou `gpt-4o-mini-audio-preview`) que aceita áudio como entrada e gera áudio como saída diretamente, sem transcrição intermediária.

```
MVP atual:
  áudio → Whisper (texto) → LLM (texto) → TTS (áudio)  [3 chamadas API, ~12s]

Evolução:
  áudio → GPT-4o multimodal → áudio                      [1 chamada API, ~3-5s]
```

**Benefícios**: latência reduzida em ~60%; preserva entonação e emoção do paciente; elimina erros de transcrição; simplifica o grafo (remove 2 nós).

**Trade-off**: modelos multimodais são mais caros por token que GPT-4o-mini texto. Avaliar custo-benefício com testes A/B.

**Alternativa intermediária**: manter Whisper + LLM texto, mas usar TTS com streaming (OpenAI `tts-1-hd` com chunked response) para o paciente ouvir o início da resposta enquanto o resto é gerado.

---

### 3. Tratamento avançado de áudio — noise reduction, VAD e streaming

**Problema atual**: o `AudioUploadButton` envia o arquivo inteiro de uma vez. Áudios longos ou com ruído degradam a qualidade da transcrição. Não há Voice Activity Detection (VAD).

**Evolução proposta**:
- **VAD no frontend**: `MediaRecorder` com detecção de silêncio para corte automático.
- **Noise reduction**: `rnnoise` (WASM) no browser antes do upload.
- **Streaming de áudio**: enviar chunks via WebSocket em vez de upload completo — o agente começa a processar antes do paciente terminar de falar.
- **Fallback inteligente**: se transcrição falhar, pedir para paciente repetir com sugestão de ambiente silencioso.

**Dependências**: WebSocket no Agent UI; endpoint de streaming no agente.

---

### 4. Gerenciamento de contexto — compactação de histórico e sliding window

**Problema atual**: o histórico de mensagens cresce indefinidamente dentro de uma thread. Conversas longas (>20 turnos) excedem a janela de contexto do GPT-4o-mini (128K tokens, mas custo e latência aumentam linearmente).

**Evolução proposta**:
- **Summarization**: nó `summarize_history` que condensa mensagens antigas em um resumo de 2-3 frases, mantendo apenas as últimas N mensagens completas.
- **Sliding window**: manter apenas os últimos 10 turnos + resumo do histórico anterior.
- **Memória seletiva**: preservar mensagens com tool calls bem-sucedidas (agendamentos/cancelamentos), descartar saudações e small talk.

```python
# Estado evolutivo
class AgendAIStateV2(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str                    # resumo do histórico antigo
    context_window: int             # 10 turnos
```

**Benefícios**: custo de token constante independente da duração da conversa; latência previsível; evita degradação de qualidade do LLM com contextos muito longos.

---

### 5. Persistência com checkpointer durável — SQLite ou PostgreSQL

**Problema atual**: checkpointer in-memory (ADR-014) perde todas as threads em restarts do container. Paciente não recupera histórico de conversas anteriores.

**Evolução proposta** (já mapeada no ADR-014):

| Fase | Solução | Complexidade |
|------|---------|-------------|
| 1. Imediata | `AsyncSqliteSaver` + volume bind mount (`./data/langgraph`) | Baixa (~10 linhas) |
| 2. Produção | `PostgresSaver` + serviço `postgres` no compose | Média (~30 linhas) |
| 3. Escala | `langgraph up` com Redis + Postgres gerenciados | Alta (migração de infra) |

**Recomendação**: fase 1 como próximo passo natural — SQLite com volume já resolve 90% dos casos sem adicionar serviço extra.

---

### 6. Wrapper do agente em FastAPI customizado

**Problema atual**: `langgraph dev` (ADR-013) é servidor de desenvolvimento — single-process, sem graceful shutdown, stack traces verbosos em erros.

**Evolução proposta**: substituir `langgraph dev` por servidor FastAPI próprio com:
- **Graceful shutdown**: aguardar execuções em voo terminarem.
- **Healthcheck**: endpoint `/health` com status do checkpointer e API REST.
- **Sanitização de erros**: nunca expor stack traces em respostas HTTP.
- **Múltiplos workers**: `uvicorn --workers 4` para paralelismo real.
- **Métricas Prometheus**: latência por nó, taxa de erro, tokens consumidos.

```python
# agent/agent/server.py (futuro)
from fastapi import FastAPI
from agent.graph import graph

app = FastAPI()

@app.post("/runs/stream")
async def stream_run(request: RunRequest):
    async for event in graph.astream_events(request.state, config=request.config):
        yield event
```

**Trade-off**: perde compatibilidade com LangGraph Studio e `langgraph-cli`. Exige reimplementar endpoints `/threads`, `/runs`, `/assistants` que o CLI fornece. Só justifica quando as limitações do `langgraph dev` forem bloqueantes.

---

### 7. MCP Server — API REST como ferramentas reutilizáveis

**Problema atual**: as tools do agente (`tools.py`) são hardcoded com `@tool` + `httpx`. Se outro sistema quiser consumir a API REST como ferramentas, precisa reescrever tudo.

**Evolução proposta** (já documentada na spec 002): expor a API REST como **MCP Server** (`@modelcontextprotocol/sdk` no Node.js), permitindo que qualquer cliente MCP (Claude Desktop, Cursor, outros agentes) descubra e use as ferramentas dinamicamente via `list_tools()`.

```
v1: tools.py hardcoded → httpx → API REST
v2: MCP Client (Python) → MCP Server (Node.js) → API REST
```

**Quando faz sentido**: múltiplos agentes consomem as mesmas ferramentas; API cresce para >10 endpoints; contrato precisa de versionamento.

---

### 8. Multi-agent — especialização por domínio

**Problema atual**: um único agente lida com agendamento, cancelamento, pagamentos e small talk. O system prompt cresce com regras de cada domínio.

**Evolução proposta**: arquitetura multi-agente com supervisor:
- **Supervisor Agent**: classifica intenção e delega.
- **Scheduling Agent**: especialista em agendamentos e cancelamentos.
- **Billing Agent**: especialista em pagamentos e valores.
- **Triage Agent**: saudação, FAQ, encaminhamento para humano.

**Benefícios**: system prompts menores e mais focados; cada agente pode usar modelo diferente (ex: GPT-4o para agendamento crítico, GPT-4o-mini para FAQ); falha de um agente não derruba os outros.

**Trade-off**: complexidade de coordenação; latência adicional do handoff entre agentes; custo de múltiplas chamadas LLM.

---

### 9. WebSocket — streaming bidirecional com menor latência

**Problema atual**: SSE é unidirecional (servidor → cliente). Upload de áudio é HTTP POST separado. Não há canal persistente.

**Evolução proposta**: WebSocket entre Agent UI e agente para:
- Upload de áudio em streaming (chunks).
- Recebimento de tokens do LLM.
- Eventos de tool call em tempo real.
- Human-in-the-loop (aprovação) no mesmo canal.

**Benefícios**: latência percebida menor; conexão única reutilizada; suporte nativo a bidirectional messaging.

---

### 10. Cache de respostas do LLM — redução de custos e latência

**Problema atual**: perguntas frequentes ("Quanto custa a consulta?", "Quais formas de pagamento?") disparam chamadas ao LLM + API REST todas as vezes.

**Evolução proposta**: cache em 2 níveis:
1. **Cache de ferramenta**: `node-cache` na API REST (já existe, TTL 60s para horários).
2. **Cache semântico de LLM**: embedding similarity — se pergunta nova for 95% similar a uma já respondida, retorna resposta cacheada sem chamar LLM.

**Ferramentas**: Redis com `redisvl` para semantic cache; ou `langchain.embeddings` + `FAISS` local.

---

### 11. Autenticação na API REST

**Problema atual**: API REST não exige autenticação (ADR-017). Aceitável para MVP com rede interna, mas bloqueante para qualquer exposição pública.

**Evolução proposta**: adicionar middleware de API key ou JWT no Express:
```javascript
app.use('/agendamentos', apiKeyAuth, agendamentosRouter(db));
```

**Quando**: API REST exposta publicamente; dados reais de pacientes; integração com sistemas externos.

---

### 12. CI/CD e testes end-to-end

**Problema atual**: testes unitários cobrem API e agente isoladamente. Não há testes de integração com containers reais nem pipeline de deploy.

**Evolução proposta**:
- **Testes E2E**: `docker compose up` → Playwright contra Agent UI → validar fluxo completo de agendamento.
- **CI/CD**: GitHub Actions com build, testes e push de imagens para registry.
- **Smoke tests**: healthcheck de todos serviços pós-deploy.

---

## Critérios de priorização

Cada caminho deve ser avaliado contra:

1. **Dor do usuário**: quantos pacientes são afetados? Qual a severidade?
2. **Custo de implementação**: esforço em dias de engenharia.
3. **Risco de não fazer**: o que quebra se adiarmos?
4. **Dependências**: requer outros caminhos antes? (ex: FastAPI antes de WebSocket)

**Sequência sugerida para próxima spec (004)**:
```
Persistência SQLite (5) → Human-in-the-loop (1) → Compactação de contexto (4) → Cache LLM (10)
```

## Referências

- ADR-013: `langgraph dev` como servidor — limitações atuais
- ADR-014: checkpointer in-memory — caminho de migração para persistência
- ADR-017: segurança atual — gaps para produção
- ADR-021: LangSmith — dados de latência que motivam evolução multimodal
- Spec 002: `specs/002-langgraph-orchestration/plan.md:123-144` — MCP Server como evolução
- LangGraph Human-in-the-loop: <https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/>
