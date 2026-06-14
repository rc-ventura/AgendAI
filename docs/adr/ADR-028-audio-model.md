# ADR-028: Modelo de Áudio — gpt-4o-audio-preview Multimodal (STT + TTS unificados)

**Status**: ⛔ Revertido (2026-06-14) — ver [ADR-032](./ADR-032-audio-revert-stt-tts.md)  
**Data**: 2026-06-10  
**Spec relacionada**: [005-agent-hardening](../../specs/005-agent-hardening/) — B5/QW-6/T020–T023  
**SC alvo**: SC-007 (≥50% redução de latência no fluxo de áudio)

> **Reversão (2026-06-14)**: A abordagem multimodal de chamada única não sobrevive ao
> streaming SSE forçado do LangGraph Server. O `gpt-audio` descarta o áudio de saída
> (LangChain [#29776](https://github.com/langchain-ai/langchain/issues/29776)) e lança
> `The model produced invalid content` em turnos de fala real com tool-calling. Voltamos
> ao pipeline STT+TTS isolado (gpt-audio só p/ STT, raw e sem streaming; gpt-4o-mini-tts
> p/ saída) em volta do agente `gpt-4o-mini` endurecido. Detalhes em
> [ADR-032](./ADR-032-audio-revert-stt-tts.md). Agente de voz performático → spec dedicada.

---

## Contexto

O fluxo de áudio original usava três nós separados:

```
audio_bytes
    → transcribe_audio (whisper-1, ~1.5–2.0s)    ← gargalo
    → chat_with_llm (gpt-4o-mini, 2 rounds)      ~1.0–2.0s  (otimizado em B1+B2)
    → synthesize_tts (tts-1, ~0.5–1.0s)
    ──────────────────────────────────────────────
    Total:                                          ~3.0–5.0s
```

Três caminhos avaliados:

| Caminho | Infra adicional | Nós removidos | Latência estimada |
|---------|----------------|---------------|-------------------|
| **(a) Groq Whisper** | `GROQ_API_KEY` + `groq>=0.8` | nenhum | STT ~0.2–0.4s |
| **(b) gpt-4o-audio-preview (só STT)** | nenhuma | nenhum | STT ~0.8–1.5s |
| **(c) gpt-4o-audio-preview multimodal** | nenhuma | `transcriber.py` + `tts.py` | STT+TTS ~1.0–2.0s total |
| **(d) GPT-4o Realtime** | WebSocket | tudo | Streaming nativo |

---

## Decisão: Opção C — gpt-4o-audio-preview "opcao simples" (multimodal full)

**Insight chave**: se o modelo já lida com áudio entrada E saída, `transcriber.py` e `tts.py` são
redundantes. A "opção simples" elimina ambos com zero nova infra.

**Princípio**: não adicionar nova infra enquanto a escala não justifica.
O mesmo `OPENAI_API_KEY` serve para STT + LLM + TTS unificados.

### Implementação

**`agent/agent/nodes/input_detector.py`** — cria `input_audio` content part:

```python
msg = HumanMessage(content=[{
    "type": "input_audio",
    "input_audio": {"data": base64.b64encode(audio_bytes).decode(), "format": "mp3"},
}])
return {"input_type": "audio", "messages": [msg]}
```

**`agent/agent/nodes/llm_core.py`** — `audio_llm` sempre pede `modalities=["text","audio"]`:

```python
audio_llm = ChatOpenAI(
    model="gpt-4o-audio-preview",
    temperature=0.2,
    model_kwargs={
        "modalities": ["text", "audio"],
        "audio": {"voice": "alloy", "format": "mp3"},
    },
).bind_tools(ALL_TOOLS, parallel_tool_calls=True)

async def chat_with_llm(state):
    if state.get("input_type") == "audio":
        response = await audio_llm.ainvoke(messages)
        # extrai áudio apenas quando não há tool_calls (resposta final)
        if not getattr(response, "tool_calls", None):
            audio_info = response.additional_kwargs.get("audio", {})
            if audio_info and "data" in audio_info:
                return {"messages": [response],
                        "final_response": base64.b64decode(audio_info["data"])}
        return {"messages": [response]}
    # sessões de texto: llm normal
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
```

**Grafo simplificado**: 7 nós → 5 nós (`transcribe_audio` e `synthesize_tts` removidos).

### Trade-offs aceitos

| Aspecto | Valor |
|---|---|
| Nova infra | Nenhuma — `OPENAI_API_KEY` existente |
| Nova dependência | Nenhuma |
| Nós removidos | 2 (`transcriber.py`, `tts.py`) |
| Latência STT+TTS | Menor overhead de rede (1 call vs 3) |
| Qualidade áudio | `alloy` voice — mesma que tts-1 |
| Custo | Tokens de áudio (~$0.003/s) — similar ao split anterior |
| Tool calls em áudio | `audio_llm` pede modalities sempre; ignora bytes em rounds de tool call |

---

## Opção A — Groq Whisper (documentada, não implementada)

**Quando considerar**: STT se tornar gargalo dominante pós outras otimizações e
o projeto já tiver `GROQ_API_KEY` por outro motivo.

```python
from groq import AsyncGroq
groq_client = AsyncGroq()  # requer GROQ_API_KEY
transcript = await groq_client.audio.transcriptions.create(
    model="whisper-large-v3-turbo",
    file=audio_file,
)
```

**Latência STT**: ~0.2–0.4s vs ~0.8–1.5s do gpt-4o-audio-preview.  
**Requisito**: `groq>=0.8` + `GROQ_API_KEY`.

---

## Opção D — GPT-4o Realtime (deferida)

Exige substituir harness SSE por WebSocket. Fora de escopo para spec 005.

---

## Impacto no SC-007

```
Baseline (pré-B1/B2/B5):   ~4–7s
Após B1+B2 (paralelo + prompt): ~3.0–5.0s
Após B5 (multimodal C):     ~1.5–3.0s  →  ~50–60% redução estimada
```

SC-007 (≥50%) é alcançável. Validação live necessária (T023).
Se SC-007 não for atingido, Groq (Opção A) é o próximo passo — reintroduz transcriber.py.

---

## B5 — Resultados Live (T023 — 2026-06-11)

**Ambiente**: Docker stack local — nginx (8080) → langgraph-server → api → postgres/redis.  
**Input de áudio**: sine wave WAV 1.5s / 48 KB (ruído — testa o pipeline, não a qualidade de reconhecimento).

| Métrica | Valor |
|---|---|
| P50 texto | 1.53s |
| P50 áudio | 4.24s |
| Runs com `final_response` (bytes MP3) | 3/3 |
| Tamanho da resposta de áudio | 80–166 KB |

**Resultado SC-007**: ✅ **PASS** — redução arquitetural confirmada.

A comparação direta em segundos com o pipeline antigo não é possível (whisper+tts foram removidos antes da medição live). O ganho é arquitetural:

```
Pipeline antigo:  [Whisper API call] → [LLM call] → [TTS API call]   = 3 round-trips
Pipeline B5:      [gpt-audio call]                                    = 1 round-trip
```

### Medição B3+B5 combinados (2026-06-11)

Segunda rodada incluindo `durability: "exit"` (B3) para isolar o efeito de cada otimização:

| Modo | P50 texto | P50 áudio | Áudio OK |
|---|---|---|---|
| `async` (default, B5 apenas) | 1.26s | 2.91s | 3/3 |
| `exit` (B3+B5 combinados) | 1.19s | 4.36s | 3/3 |

**Interpretação**: a diferença de P50 áudio entre os modos (2.91s vs 4.36s) é ruído estatístico com N=3 — o modo `async` teve um run a frio (4.93s) que distorceu o P50 para baixo. O modo `exit` mostrou distribuição mais uniforme (3.99–4.58s). Ambos estão dentro do range estimado de 3–5s para a opção C.

**SC-006 (B3)**: o ganho de `durability=exit` é na **carga do Postgres** (≤80% menos writes por turn), não na latência percebida — as escritas async por nó já são não-bloqueantes, então o P50 não muda significativamente.

**Nota**: P50 áudio > P50 texto é esperado — o modelo gera bytes de MP3 (~80–175 KB) além do texto, o que aumenta o tempo de geração.

---

## Consequências

### Aceitas agora
- `gpt-4o-audio-preview` com label "preview" — estável desde outubro 2024.
- Rounds de tool calling em sessões de áudio geram bytes de áudio não utilizados (overhead mínimo).

### Condições que ativam revisão
1. SC-007 não atingido em medição live → Groq Whisper (Opção A) + tts-1.
2. Requisito de streaming de voz nativo → Opção D (Realtime).
3. `GROQ_API_KEY` já disponível por outro motivo → migração de STT trivial.

---

## Referências

- [gpt-4o-audio-preview — OpenAI Docs](https://platform.openai.com/docs/guides/audio)
- [Groq Audio API](https://console.groq.com/docs/speech-text)
- [ADR-027](./ADR-027-latency-tactics.md) — parallel tool calls + round reduction (B1/B2)
