# ADR-028: Modelo de Áudio — Groq Whisper vs gpt-4o-audio-preview

**Status**: Accepted  
**Data**: 2026-06-10  
**Spec relacionada**: [005-agent-hardening](../../specs/005-agent-hardening/) — B5/QW-6/T020–T023  
**SC alvo**: SC-007 (≥50% redução de latência no fluxo de áudio)

---

## Contexto

O fluxo de áudio atual do AgendAI usa três chamadas de API separadas:

```
audio_bytes
    → transcribe_audio (OpenAI whisper-1)      ~1.5–2.0s  ← gargalo
    → chat_with_llm (gpt-4o-mini, 2 rounds)    ~1.0–2.0s  (otimizado em B1+B2)
    → synthesize_tts (OpenAI tts-1)            ~0.5–1.0s
    ─────────────────────────────────────────────────────
    Total fluxo de voz:                         ~3.0–5.0s  (com B1+B2)
```

SC-007 exige ≥50% de redução em relação ao baseline pré-B1/B2 (~4–7s total).

A investigação R8 identificou três caminhos:

| Caminho | Transporte | Elimina nós | Esforço |
|---------|-----------|-------------|---------|
| **(a) Groq Whisper** | REST | nenhum | 5 linhas |
| **(b) gpt-4o-audio-preview** | REST (sem WebSocket) | `transcriber.py` + `tts.py` | médio — reestrutura fluxo LLM |
| **(c) GPT-4o Realtime** | WebSocket | transcribe + TTS | alto — troca harness SSE |

---

## Opção A — Groq Whisper drop-in (escolhida)

**Modelo**: `whisper-large-v3-turbo`

Groq hospeda o Whisper da OpenAI em hardware próprio (LPU). A API é idêntica à OpenAI:
`client.audio.transcriptions.create(model="whisper-large-v3-turbo", file=file)`.

### Benchmark (publicado por Groq/comunidade, junho 2025)

| Provider | Modelo | Latência STT (áudio 30s) | pt-BR |
|---|---|---|---|
| OpenAI | `whisper-1` | ~1.5–2.0s | ✅ boa |
| Groq | `whisper-large-v3-turbo` | ~0.2–0.4s | ✅ boa |
| Groq | `whisper-large-v3` | ~0.5–0.8s | ✅ melhor precisão |

**Economia**: ~1.2–1.7s no passo de STT — o maior item individual no fluxo de áudio.

### Impacto no SC-007

Com B1 (parallel tools) + B2 (prompt eng.) + B5(a) (Groq Whisper):

```
Antes (baseline):   ~4–7s total
Depois B1+B2+B5(a): ~1.3–3.3s total  →  ≈50–67% redução
```

SC-007 (≥50%) alcançável com B5(a) somado às otimizações de B1+B2.

### Trade-offs

| Aspecto | Valor |
|---|---|
| Mudança de código | `transcriber.py` — 4 linhas |
| Nova dependência | `groq>=0.8` |
| Nova env var | `GROQ_API_KEY` |
| Risco | Baixo — mesma API, provider diferente |
| Custo | $0.111/hora de áudio (vs OpenAI: $0.006/min = $0.36/hora) |
| Fallback | Revertível para `whisper-1` trocando provider |

### Modelo escolhido: `whisper-large-v3-turbo`

`whisper-large-v3-turbo` é uma versão destilada com latência 2x menor vs `whisper-large-v3`
e qualidade suficiente para conversas médicas em pt-BR. Se qualidade de transcrição for
problema em produção, trocar para `whisper-large-v3` (1 linha de mudança).

---

## Opção B — `gpt-4o-audio-preview` multimodal (deferida)

**Por que não agora:**

O fluxo com `gpt-4o-audio-preview` não é tão simples quanto "1 chamada":

```
1. Primeira chamada: áudio in → transcrição implícita → tool calls (rodadas de texto)
2. N rodadas de text in/out (tool calling — igual ao fluxo atual)
3. Chamada final: text in + modality=audio → áudio out (substitui tts-1)
```

A simplificação real é: (1) sem chamada separada ao Whisper, (3) sem chamada separada ao TTS.
Mas o meio (rodadas de tool calling) continua igual.

**O que muda na arquitetura:**
- `transcriber.py` é removido — o primeiro `llm_core.py` recebe `input_audio` content part
- `detect_input_type` ainda decide o fluxo, mas não há nó de transcrição separado
- `synthesize_tts` é removido — a última chamada ao LLM pede `modalities: ["text", "audio"]`
- `llm_core.py` precisa de dois modos: text-only e audio-aware (estado `input_type`)

**Custo**: ~$0.06/min áudio in, ~$0.24/min áudio out — significativamente maior que Groq.

**Quando ativar:**
- Qualidade de voz for requisito crítico (voz nativa do GPT-4o é superior ao tts-1)
- Budget de API justificar o custo maior
- Quisermos eliminar a dependência do Groq

**Outcome → deferido para sprint de qualidade, não de latência.**

---

## Opção C — GPT-4o Realtime (deferida)

Exige substituir o harness SSE por WebSocket. Fora de escopo para spec 005.

---

## Decisão

**Implementar Opção A: Groq Whisper (`whisper-large-v3-turbo`).**

Mudança cirúrgica em `agent/agent/nodes/transcriber.py`. Zero impacto no grafo ou no fluxo de texto. Ganho imediato de ~1.2–1.7s no passo dominante do fluxo de voz.

```python
# agent/agent/nodes/transcriber.py — depois da mudança
from groq import AsyncGroq

groq_client = AsyncGroq()  # lê GROQ_API_KEY do ambiente

transcript = await groq_client.audio.transcriptions.create(
    model="whisper-large-v3-turbo",
    file=audio_file,
)
```

---

## Consequências

### Aceitas agora
- Nova env var `GROQ_API_KEY` necessária para fluxo de voz.
- Fallback manual: reverter para `whisper-1` trocando `groq_client` por `openai_client` e o model string.
- Latência de STT reduzida de ~1.5–2s para ~0.2–0.4s.

### Condições que ativam revisão
1. Qualidade de transcrição pt-BR insatisfatória em produção → trocar para `whisper-large-v3`.
2. Budget de API justificar → avaliar Opção B (`gpt-4o-audio-preview`).
3. Requisito de voz nativa de alta qualidade → Opção B.

---

## Referências

- [Groq Audio API](https://console.groq.com/docs/speech-text) — modelos whisper disponíveis e latências
- [gpt-4o-audio-preview](https://platform.openai.com/docs/guides/audio) — REST sem WebSocket, base64 in/out
- [Research R8](../../specs/005-agent-hardening/research.md#r8) — análise dos três caminhos
- [ADR-027](./ADR-027-latency-tactics.md) — parallel tool calls + round reduction (B1/B2)
- [Learning lesson áudio](../learning-lessons/modelos_audio_multimodal_litellm.md)
