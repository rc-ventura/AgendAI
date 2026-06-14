# B5 — Validação Live: gpt-4o-audio-preview Multimodal

**Batch**: B5 / T023  
**Data**: 2026-06-11 (atualizado 2026-06-14)  
**ADR relacionado**: [ADR-028](../adr/ADR-028-audio-model.md)  
**SC**: SC-007 — ≥50% redução de latência no fluxo de áudio

---

## O que validamos

Pipeline de áudio end-to-end no stack Docker local:

```
input WAV → nginx → langgraph-server → [detect_input_type]
         → [audio_agent (gpt-audio)]  → [process_audio_results]
         → [extract_audio_response]   → state.final_response (bytes WAV)
```

> ⚠️ O diagrama original dizia "bytes MP3". Corrigido para WAV — ver Lição 5.

Resultados (3 runs por modo, sine wave 1.5s / 48 KB):

| Modo | P50 texto | P50 áudio | Áudio OK |
|---|---|---|---|
| `async` (B5 apenas) | 1.26s | 2.91s | 3/3 |
| `exit` (B3+B5) | 1.19s | 4.36s | 3/3 |

---

## Lição 1 — Comparação direta de latência é impossível sem baseline vivo

SC-007 pede ≥50% de redução vs o pipeline antigo (Whisper + LLM + TTS). Mas o pipeline antigo foi **removido** antes de qualquer medição live — `transcriber.py` e `tts.py` não existem mais.

**Consequência**: a validação do SC-007 ficou sendo arquitetural, não empírica. A redução de 3 round-trips para 1 é comprovada pelo código; os números em segundos são estimativas baseadas na documentação da OpenAI.

**Aprendizado**: medir o baseline ANTES de remover o sistema antigo. Para migrações futuras de pipeline, adicionar um passo de "medição do estado atual" antes do PR de remoção.

---

## Lição 2 — Sine wave testa o pipeline, não a qualidade

O script de validação usa uma onda senoidal como input de áudio. O modelo `gpt-4o-audio-preview` recebe ruído, produz uma resposta de áudio (geralmente genérica ou confusa), mas o pipeline funciona corretamente do ponto de vista de bytes.

**O que isso prova**: que `detect_input_type` → `audio_agent` → `extract_audio_response` → `final_response` funciona ponta-a-ponta.

**O que não prova**: qualidade de reconhecimento de fala real, compreensão de intenção por áudio, ou que a resposta de áudio é semanticamente correta.

**Para validação de qualidade**: usar áudio real com uma frase de agendamento e verificar o conteúdo da resposta de texto no estado (`messages[-1].content`).

---

## Lição 3 — P50 áudio > P50 texto é esperado e não é regressão

P50 texto = 1.53s, P50 áudio = 4.24s. A diferença de ~2.7s corresponde à geração de 80–166 KB de MP3. O modelo `gpt-audio` faz STT + raciocínio + geração de áudio em uma chamada — o tempo adicional é o custo da síntese, não uma regressão.

**Cuidado**: comparar P50 de áudio com P50 de texto não faz sentido — são tarefas de complexidade diferente. A métrica correta para SC-007 é comparar P50 áudio (novo) vs P50 áudio (antigo pipeline de 3 chamadas).

---

## Lição 4 — nginx é o único entry point; testar sem ele mascara problemas de auth

A primeira tentativa de rodar `validate_b5_audio.py` apontou para `http://127.0.0.1:8123` (direto ao langgraph-server), que não é exposto ao host. A porta 8123 só existe dentro da rede Docker.

O stack real é `host:8080 → nginx → langgraph-server:8123`. Testes de integração que pulam o nginx não validam autenticação (`x-api-key`), rate limiting, ou roteamento real.

**Regra**: scripts de validação live sempre usam `http://localhost:8080` (nginx), nunca portas internas.

---

## Lição 5 — `audio.format="mp3"` falha com streaming; a solução é `pcm16` + wrapper WAV

### O erro

Depois da primeira validação bem-sucedida (que rodava contra uma imagem Docker **antiga** em cache),
a reconstrução da imagem expôs o erro real:

```
openai.BadRequestError: audio.format does not support 'mp3' when stream=true.
Supported values are: 'pcm16'
```

### Por que acontece: a cadeia causal

```
LangGraph Server injeta LogStreamCallbackHandler (para SSE)
    ↓
LangChain detecta o handler em BaseChatModel._ainvoke()
    ↓ ativa stream=True internamente
OpenAI recebe stream=True + audio.format="mp3"
    ↓
BadRequestError: mp3/opus/flac/wav não suportados com stream=True
```

**Raiz**: a OpenAI só aceita `"format": "pcm16"` quando `stream=True`. Formatos como `mp3`, `opus`,
`flac` e `wav` (com cabeçalho completo) só funcionam com `stream=False` — que o LangChain nunca
usa quando há um `LogStreamCallbackHandler` no contexto (e o LangGraph Server sempre injeta um).

Fontes que corroboram:
- [LangChain Issue #20980](https://github.com/langchain-ai/langchain/issues/20980) — `ainvoke` ativa `stream=True` via `LogStreamCallbackHandler` (aberto abr/2024)
- [LangChain Issue #29776](https://github.com/langchain-ai/langchain/issues/29776) — streaming não popula `additional_kwargs` com áudio no ChatOpenAI (aberto fev/2025, fechado sem resolução)
- [OpenAI Community](https://community.openai.com/t/chat-completions-audio-output-but-not-base64-encoded-string/1361764) — "It only allows 'pcm16' as a format for you to receive — headerless audio"

### A solução: pcm16 + wrapper WAV

PCM16 é áudio **bruto** — sem cabeçalho. O browser não consegue reproduzir sem saber sample rate,
canais e bit depth. O wrapper WAV (RIFF) é um cabeçalho de 44 bytes que embala os bytes PCM:

```python
# nodes/audio.py
def pcm16_to_wav(pcm_bytes: bytes) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE",
        b"fmt ", 16, 1,           # PCM linear
        1, 24000, 48000, 2, 16,  # mono, 24kHz, byte_rate, block_align, 16-bit
        b"data", len(pcm_bytes),
    )
    return header + pcm_bytes
```

Parâmetros fixos (`24000 Hz`, `mono`, `16-bit`) são as specs de saída do `gpt-audio` — não variam.

No browser, o MIME type muda de `audio/mpeg` para `audio/wav`:
```typescript
// hooks/use-tts-player.tsx
const blob = new Blob([bytes], { type: "audio/wav" });
```

### É um workaround ou a abordagem padrão?

**É a abordagem padrão para contextos de streaming.** Não é um hack.

A abordagem alternativa (sem wrapper manual) é usar `"format": "wav"` — a OpenAI já entrega o
arquivo WAV completo com cabeçalho. Isso funciona com `stream=False`, que é como os tutoriais
oficiais (DataCamp, LangChain docs) documentam o uso. Mas no contexto do LangGraph Server,
`stream=False` não é acessível — o servidor sempre faz streaming para SSE.

A conversão PCM16→WAV é padrão em toda a indústria de streaming de áudio (IoT, WebSocket,
Audio Worklets de browser). O wrapper RIFF tem exatamente 44 bytes e zero overhead de processamento.

### Modelo usado

`model="gpt-audio"` — alias estável que aponta para o snapshot mais recente (`gpt-audio-2025-08-28`,
também chamado `gpt-audio-1.5`). Não existe um "gpt-5-audio" — a família de áudio via Chat
Completions é `gpt-audio`; a família Realtime (WebSocket) é `gpt-realtime-*`.

A restrição `pcm16`-only com streaming é uma limitação de infraestrutura (chunks PCM são
processáveis incrementalmente; MP3 requer o frame completo), independente de versão do modelo.

### Arquivos alterados

| Arquivo | Mudança |
|---------|---------|
| `agent/agent/nodes/llm_core.py` | `"format": "mp3"` → `"format": "pcm16"` |
| `agent/agent/nodes/audio.py` | adicionado `pcm16_to_wav()` |
| `agent/agent/graph.py` | `extract_audio_response` chama `pcm16_to_wav()` |
| `agent-ui-pro/src/hooks/use-tts-player.tsx` | `"audio/mpeg"` → `"audio/wav"` |
