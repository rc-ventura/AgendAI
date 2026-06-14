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

> ⚠️ **ATUALIZAÇÃO (2026-06-14)**: A solução `pcm16` + wrapper WAV descrita na Lição 5 foi
> **abandonada** em favor do B1 (Lição 9). O `gpt-audio` não consegue devolver áudio sob o
> streaming forçado do servidor (LangChain #29776). A Lição 5 fica como registro de por que o
> caminho single-call não funciona. **O código de saída atual é o nó TTS dedicado** (Lição 9).

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

---

## Lição 6 — Erros de áudio multimodal seguem uma cadeia causal (não são aleatórios)

Durante a validação de 2026-06-14, os erros apareceram em sequência:

1. `Invalid value: 'webm'. Supported values are: 'wav' and 'mp3'`
2. `unsupported_format` (mesmo com `format="wav"`)
3. `413 Request Entity Too Large` no nginx

Isso não são três bugs independentes. É a mesma cadeia:

```
MediaRecorder gera WEBM/Opus
   ↓
payload rotulado com format incompatível (ou rótulo != bytes reais)
   ↓
API recusa formato/container
   ↓
correção via conversão para WAV aumenta tamanho da request
   ↓
nginx default (~1MB) passa a barrar com 413
```

**Aprendizado**: em áudio multimodal, sempre validar em ordem:
1) codec/container real, 2) campo `input_audio.format`, 3) limites de proxy/body size.

---

## Lição 7 — Payload grande após WEBM→WAV é esperado (trade-off conhecido)

WAV PCM é essencialmente sem compressão, enquanto WEBM/Opus é comprimido.
Para voz, é normal WAV ficar **várias vezes maior** que WEBM para a mesma duração.

Consequências práticas:
- Mais bytes no upload (maior latência de rede em uplink ruim)
- Maior chance de 413 em proxies/gateways
- Mais pressão em memória/serialização quando o payload vai em JSON/lista de bytes

Isso explica o `client intended to send too large body` com ~1.1 MB no `/runs/stream`.

**Decisão de curto prazo**: aumentar `client_max_body_size` no nginx para destravar validação.
**Risco**: limite alto sem governança amplia superfície de abuso (DoS por corpo grande).

---

## Lição 8 — Latência vs robustez: caminhos recomendados

Há três estratégias viáveis, cada uma com trade-offs:

### A) Conversão no cliente (WEBM→WAV) e envio ao agente (atual hotfix)
- ✅ Corrige incompatibilidade de formato imediatamente
- ❌ Aumenta payload e latência de upload
- ❌ Exige ajuste de `client_max_body_size`

### B) Rota separada de voz (ingestão/STT) e agente recebe texto
- ✅ Remove blob de áudio do `/runs/stream` (menos 413 e menos acoplamento)
- ✅ Simplifica contexto/histórico do agente
- ❌ +1 chamada de rede (STT), pode aumentar latência ponta-a-ponta

### C) Capturar/comprimir melhor na origem (quando suportado)
- Ex.: mono, sample rate menor, limite de duração por turno
- ✅ Reduz payload sem mudar arquitetura inteira
- ⚠️ Depende do suporte real de browser/codec e da API alvo

**Recomendação operacional**:
1. manter hotfix para estabilizar;
2. adicionar limite de duração no cliente (ex.: 10–20s);
3. avaliar migração para rota separada se voz longa virar caso de uso frequente.

---

## Lição 9 — Decisão final: B1 (TTS dedicado), não single-call multimodal

Depois das Lições 5–8, ficou claro que o sonho do ADR-028 ("uma chamada multimodal substitui 3")
é **inviável dentro deste harness**: o LangGraph Server força streaming SSE, e o LangChain
descarta os chunks de áudio de saída (#29776). Mesmo com `pcm16` aceito, `final_response` voltava
`None` — confirmado nos logs: `extract_audio_response: no audio data found in N messages`.

**B1** desacopla as duas pontas:

```
voz → detect_input_type → audio_agent (gpt-audio, modalities=["text"])
    → process_audio_results → synthesize_audio_response → final_response (WAV)
```

- **Entrada**: `gpt-audio` continua entendendo a voz nativamente (STT + raciocínio numa chamada,
  sem Whisper). Só o output muda para texto.
- **Saída**: nó `synthesize_audio_response` chama `/audio/speech` (`gpt-4o-mini-tts`, não-streaming),
  que devolve WAV completo. Sem `pcm16`, sem wrapper manual, sem #29776.

### B1 ≠ pipeline antigo (Whisper + LLM + TTS)

| Pipeline | STT | Raciocínio | TTS | Chamadas |
|----------|-----|-----------|-----|----------|
| Antigo (removido) | Whisper | gpt-4o-mini | TTS | 3 |
| **B1** | gpt-audio (nativo) | mesma chamada | gpt-4o-mini-tts | **2** |

B1 reintroduz **só o TTS** — não o Whisper. Mantém tool-calling e middleware no turno de voz
(o que a alternativa "SDK cru com stream=False" perderia).

### Código removido (era over-engineering relativo ao B1)

`pcm16_to_wav`, a config de áudio-out do `audio_llm` (`modalities:["text","audio"]` + `format`),
e `extract_audio_response`. Não estavam *errados* — eram a correção do caminho single-call que o B1
abandona. Mantida a robustez de **entrada** (`normalize_input_audio_format`, `detect_audio_container`).

### Validação ao vivo (2026-06-14, via nginx)

6/6 runs de áudio retornaram WAV válido (19–339 KB, varia com tamanho da resposta).
P50 áudio ~4.6–5.0s (dominado pela síntese TTS). 107 testes pytest verdes.

> **Fonte do bug de saída**: [LangChain #29776](https://github.com/langchain-ai/langchain/issues/29776) —
> "streaming fails to populate additional_kwargs containing audio data" (fev/2025, fechado sem fix).

---

## Lição 10 — Desfecho: B1 também caiu; voltamos ao STT+TTS isolado (ADR-031)

A Lição 9 (B1) durou pouco. Com **fala real** (não a sine wave), o `gpt-audio` no loop do
agente lançou `The model produced invalid content` — o segundo bug do streaming, agora no
**tool-calling**, não no áudio-out. A sine wave passava porque não gerava tool calls; fala
real gera, e quebra.

**Conclusão definitiva**: o `gpt-audio` não sobrevive ao streaming forçado do servidor de
jeito nenhum dentro do loop do agente — nem áudio-out (#29776), nem texto-out com tools.

**Decisão (ADR-032)**: tirar o `gpt-audio` do loop e voltar ao **STT+TTS isolado**:

```
detect_input_type → transcribe_audio (gpt-audio, raw SDK, sem stream/tools)
                  → text_agent (gpt-4o-mini + middleware + tools)
                  → [send_email] → synthesize_tts (gpt-4o-mini-tts, WAV) → END
```

- STT e TTS são **chamadas diretas ao SDK OpenAI** em nós comuns — **não** são `create_agent`.
  É justamente por ficarem fora do LangChain que escapam do streaming.
- O agente de raciocínio (`gpt-4o-mini`) é o mesmo para texto e voz.
- Mantida toda a robustez de entrada (webm→wav no cliente, normalize/detect, nginx body size).

**Trade-off aceito**: SC-007 (≥50% redução) não é atingido por esta via — voltamos a 2–3
chamadas. Confiabilidade > latência por ora. Agente de voz performático → **spec dedicada**.

Validado ao vivo: 6/6 runs com WAV válido; 108 testes pytest verdes. Ver [ADR-031](../adr/ADR-032-audio-revert-stt-tts.md).
