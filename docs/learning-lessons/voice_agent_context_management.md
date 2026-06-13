# Learning Lesson — Voice Agent Context Management & Summarization

**Origem:** B8 + pesquisa pós-implementação  
**Data:** 2026-06-12  
**Relevância futura:** qualquer batch que lide com conversas de áudio longas ou revisão do B5

---

## L1 — `SummarizationMiddleware` não deve ser usado com o audio_agent (bug #33856)

**O que**: a pesquisa revelou um bug crítico no LangChain:
`SummarizationMiddleware` usa `get_buffer_string()` para formatar mensagens antes de gerar o resumo.
Essa função **descarta `SystemMessage`** — após a primeira sumarização, o agente perde o system
prompt, as instruções de identidade e todas as regras de negócio.

**Impacto no AgendAI**: o `SYSTEM_PROMPT` de `llm_core.py` (que inclui proteções de injection,
regras de agendamento, etc.) desapareceria após o primeiro evento de sumarização.

**Fonte**: [GitHub issue #33856](https://github.com/langchain-ai/langchain/issues/33856) — não corrigido até a data desta pesquisa.

**Ação**: `SummarizationMiddleware` está no `LLM_MIDDLEWARE` para ambos os agentes (text + audio).
Para o `audio_agent`, isso é risco duplo: bytes de áudio na mensagem + system prompt apagado.
A solução correta está em L4.

---

## L2 — Padrão universal para agentes de voz: transcrição ANTES de entrar em `messages`

**O que a comunidade usa** (confirmado em dois projetos reais):

```
áudio bytes → STT (Whisper/Deepgram) → texto transcript → HumanMessage(text) → agent
```

Os bytes de áudio são efêmeros — usados para transcrição e descartados. **Apenas o transcript
de texto entra no estado.** Com isso, `SummarizationMiddleware` funciona corretamente, token
counting é preciso e resumos têm qualidade.

**Exemplo 1 — rosiefaulkner/langgraph-voice-agent**
([github.com/rosiefaulkner/langgraph-voice-agent](https://github.com/rosiefaulkner/langgraph-voice-agent)):
Usa Whisper via `voice_utils.py` para STT antes do grafo. `messages` recebe apenas texto.
Bytes nunca chegam ao estado do LangGraph.

**Exemplo 2 — aiechoes: Building Conversational Audio Agents**
([aiechoes.substack.com/p/building-conversational-audio-agents](https://aiechoes.substack.com/p/building-conversational-audio-agents)):
Mesmo padrão + implementa sumarização explícita quando a conversa cresce:
- Threshold: **> 5 trocas OU > 10.000 tokens** (OR logic, igual ao B8)
- Ação: sumariza tudo antes dos últimos 5 turnos
- Resumo vai como **`SystemMessage`** (não `HumanMessage`)
- Áudio TTS é gerado on-demand para playback, nunca persiste em `messages`

**Relação com AgendAI**: o fluxo anterior (B4) seguia este padrão (`transcriber.py` com Whisper).
O B5 (ADR-028) eliminou essa etapa em favor do `gpt-audio` (single-call), que é mais rápido
mas rompe com o padrão de segurança de contexto. Para conversas curtas (caso atual) não importa.
Para conversas longas, precisa revisão via Whisper paralelo (ver L5).

---

## L3 — Padrão OpenAI Realtime API para sessões de voz longas

O [OpenAI cookbook](https://cookbook.openai.com/examples/context_summarization_with_realtime_api)
documenta o algoritmo de referência para compressão de contexto em agentes de voz:

1. Monitorar tokens via evento `response.done`
2. Quando threshold atingido: comprimir tudo exceto os últimos N turnos
3. Inserir resumo como **`SystemMessage`** (não `AIMessage` — usar assistant role faz o modelo
   mudar de output de áudio para texto)
4. Deletar os turnos antigos individualmente via `conversation.item.delete`

**Por que SystemMessage para o resumo**: preserva a "memória" sem afetar a distribuição de
roles esperada pelo modelo de áudio. Uma `AIMessage` com resumo confunde o modelo sobre
quem está falando.

**Escala**: o `gpt-realtime-2` tem 128k tokens — cobre ~1-2 horas de áudio denso antes de
precisar compressão.

**Fonte**: [OpenAI cookbook — context_summarization_with_realtime_api](https://cookbook.openai.com/examples/context_summarization_with_realtime_api)

---

## L4 — Padrão recomendado para AgendAI (implementação futura)

Se conversas de áudio longas se tornarem um caso de uso real, o caminho correto é um
**custom trim node** no grafo, não `SummarizationMiddleware`:

```python
# agent/agent/nodes/context_trimmer.py  (a criar no futuro)

async def trim_context(state: AgendAIState) -> dict:
    """Comprime contexto quando necessário. Roda como nó antes do audio_agent."""
    messages = state["messages"]
    
    # 1. Separar system messages (nunca sumarizar)
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    other_msgs  = [m for m in messages if not isinstance(m, SystemMessage)]
    
    # 2. Verificar threshold (tokens ou contagem)
    if len(other_msgs) <= KEEP_LAST_N_TURNS * 2:
        return {}  # nada a fazer
    
    # 3. Sumarizar turnos antigos (texto puro — nunca áudio)
    to_summarize = [m for m in other_msgs[:-KEEP_LAST_N_TURNS*2]
                    if not _has_audio_content(m)]
    summary_text = await _summarize(to_summarize)
    
    # 4. Reconstruir: [system] + [SystemMessage(summary)] + [últimos N turnos]
    new_messages = [
        RemoveMessage(id=REMOVE_ALL_MESSAGES),
        *system_msgs,
        SystemMessage(content=f"Resumo da conversa anterior:\n{summary_text}"),
        *other_msgs[-KEEP_LAST_N_TURNS*2:],
    ]
    return {"messages": new_messages}
```

**Diferenças do `SummarizationMiddleware`**:
- Protege `SystemMessage` explicitamente
- Pula mensagens com bytes de áudio (em vez de corromper)
- Resumo vai em `SystemMessage`, não `HumanMessage` (padrão OpenAI)
- Roda como nó do grafo, não como hook de middleware — posicionamento controlável

---

## L5 — O dilema B5 × contexto longo e a solução: Whisper paralelo

| Abordagem | Latência | Contexto longo | Qualidade áudio |
|-----------|----------|----------------|-----------------|
| B4: Whisper → LLM → TTS (3 calls sequenciais) | Alta (+~1s) | ✅ Texto em messages | ✅ Transcrição em messages |
| B5: gpt-audio (1 call) | Baixa | ⚠️ Bytes em messages | ✅ Entendimento nativo |
| **Híbrido: Whisper paralelo + gpt-audio** | **Zero overhead (async)** | **✅** | **✅** |

### Como implementar o Whisper paralelo (direção recomendada)

O ponto-chave: Whisper e `gpt-audio` podem rodar **ao mesmo tempo**. O transcript do Whisper
não é necessário para a resposta — apenas para o histórico de contexto. Isso elimina o
trade-off de latência do B4.

```
input_detector ──┬──→ audio_agent (gpt-audio)     ← responde imediatamente
                 └──→ transcribe_async (Whisper)   ← em paralelo, salva transcript
```

**Implementação no LangGraph** (nós a criar):

```python
# 1. input_detector.py — disparar Whisper como task paralela (não bloquear)
async def detect_input_type(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if raw:
        # Dispara Whisper em background — não await aqui
        asyncio.create_task(_transcribe_to_state(raw, state["session_id"]))
        # Continua passando bytes para audio_agent (comportamento B5 preservado)
        b64 = base64.b64encode(raw).decode()
        msg = HumanMessage(content=[{"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}}])
        return {"input_type": "audio", "messages": [msg]}
    return {"input_type": "text"}

# 2. context_trimmer.py — nó externo ao audio_agent, lê transcript do estado
async def trim_context(state: AgendAIState) -> dict:
    messages = state["messages"]
    transcript = state.get("context_summary")  # campo já existe (B8)

    # Substituir HumanMessage com bytes pelo transcript (se disponível)
    if transcript:
        clean_messages = _replace_audio_with_transcript(messages, transcript)
    else:
        clean_messages = messages  # Whisper ainda não terminou — skip trim

    # Verificar threshold e sumarizar se necessário (igual ao padrão aiechoes)
    if len(clean_messages) <= KEEP_LAST_N * 2:
        return {}

    system_msgs = [m for m in clean_messages if isinstance(m, SystemMessage)]
    other_msgs  = [m for m in clean_messages if not isinstance(m, SystemMessage)]
    summary = await _summarize(other_msgs[:-KEEP_LAST_N * 2])

    return {"messages": [
        RemoveMessage(id=REMOVE_ALL_MESSAGES),
        *system_msgs,
        SystemMessage(content=f"Resumo da conversa anterior:\n{summary}"),  # padrão aiechoes
        *other_msgs[-KEEP_LAST_N * 2:],
    ]}
```

**Por que `SystemMessage` para o resumo** (confirmado por aiechoes + cookbook OpenAI):
- Preserva a "memória" sem afetar a distribuição de roles
- `AIMessage` com resumo confunde o modelo sobre quem está falando
- `HumanMessage` (atual do `SummarizationMiddleware`) não é semanticamente correto para um resumo

**Bloqueio atual resolvido**: `SummarizationMiddleware` roda dentro do `audio_agent` (middleware).
O `context_trimmer` como nó externo no grafo roda **antes** do `audio_agent`, com acesso ao
transcript já salvo pelo Whisper paralelo.

---

## L6 — Mitigação implementada: strip do blob de áudio após consumo (B10-D)

**Problema concreto observado**: o B10-A limpou `audio_data`/`audio_format` do estado em
`agent/agent/nodes/input_detector.py:24-25`, mas os mesmos bytes são re-introduzidos como string
base64 dentro de uma `HumanMessage` com content part `input_audio`
(`agent/agent/nodes/input_detector.py:17-20`). Essa mensagem entra em `messages` via o reducer
`add_messages` e **persiste em todos os checkpoints seguintes** e é **re-enviada ao LLM a cada
turno**. Um clipe de 1.5s ≈ 64KB base64. Isso anula parcialmente o ganho do B3 (`durability: "exit"`)
e infla custo/latência por turno — exatamente o que a Constitution VII proíbe (dado transiente não
deve persistir além do nó que o consome).

**Mitigação (implementada, não é a solução completa)**: o nó `extract_audio_response`
(`agent/agent/graph.py`) já roda depois do `audio_agent` ter consumido o áudio. Adicionamos
`_strip_consumed_audio` que substitui cada `HumanMessage` com `input_audio` por um placeholder de
texto `"[mensagem de voz]"` **reusando o mesmo `id`** — o `add_messages` faz update in-place
(confirmado: re-emitir com mesmo `id` sobrescreve, sem precisar de `RemoveMessage`). Resultado: o
blob sai do histórico assim que cumpre sua função.

```python
# agent/agent/graph.py
def _strip_consumed_audio(state: AgendAIState) -> list:
    replacements = []
    for msg in state["messages"]:
        if _is_input_audio_message(msg) and getattr(msg, "id", None):
            replacements.append(HumanMessage(id=msg.id, content="[mensagem de voz]"))
    return replacements
```

**Trade-off aceito**: o **transcript real (as palavras) NÃO é preservado** — o modelo perde o
conteúdo de turnos de voz passados. Aceitável para o fluxo atual (agendamento curto, single-turn).
Para conversas multi-turn de voz, o contexto degrada — é exatamente o gap que o Whisper paralelo
(L5) resolve preservando o transcript. Esta mitigação é o passo barato que **para o sangramento de
checkpoint hoje sem reintroduzir o Whisper** (que desfaria o ganho de latência do B5/ADR-028).

**Por que placeholder de texto e não remoção total**: remover a `HumanMessage` deixaria o turno
sem o lado "human", confundindo a distribuição de roles e quebrando a sequência conversacional.
O placeholder mantém a estrutura ("paciente enviou um áudio") com custo de bytes ~zero.

---

## Resumo das ações futuras

| Prioridade | Ação | Trigger |
|------------|------|---------|
| ✅ Feito | Strip do blob de áudio em `extract_audio_response` (placeholder de texto, mesmo `id`) — para o checkpoint bloat hoje | Implementado (B10-D) |
| Alta | Remover `SummarizationMiddleware` do stack do `audio_agent` (bug #33856) | Antes de go-live em produção |
| Média | Implementar Whisper paralelo em `input_detector.py` salvando transcript — **preserva o conteúdo** que o strip (L6) descarta | Monitoramento mostrar conversas de áudio > 10 turnos |
| Média | Implementar `context_trimmer` como nó do grafo seguindo padrão aiechoes (SystemMessage, threshold OR) | Junto com Whisper paralelo |
| Baixa | Migrar resumo de `HumanMessage` → `SystemMessage` no `SummarizationMiddleware` (text-only) | Se upstream corrigir bug #33856 |

**Referências desta pesquisa:**
- [rosiefaulkner/langgraph-voice-agent](https://github.com/rosiefaulkner/langgraph-voice-agent) — padrão Whisper-first
- [aiechoes — Building Conversational Audio Agents](https://aiechoes.substack.com/p/building-conversational-audio-agents) — threshold OR + resumo como SystemMessage
- [OpenAI cookbook — context_summarization_with_realtime_api](https://cookbook.openai.com/examples/context_summarization_with_realtime_api) — algoritmo de referência (Realtime API)
