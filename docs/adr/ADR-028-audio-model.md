# ADR-028: Modelo de Áudio — gpt-4o-audio-preview (REST, sem nova infra)

**Status**: Accepted  
**Data**: 2026-06-10  
**Spec relacionada**: [005-agent-hardening](../../specs/005-agent-hardening/) — B5/QW-6/T020–T023  
**SC alvo**: SC-007 (≥50% redução de latência no fluxo de áudio)

---

## Contexto

O fluxo de áudio atual usa `whisper-1` via `openai.audio.transcriptions.create` —
uma chamada REST separada antes do LLM processar a mensagem.

```
audio_bytes
    → transcribe_audio (whisper-1)          ~1.5–2.0s  ← gargalo
    → chat_with_llm (gpt-4o-mini, 2 rounds) ~1.0–2.0s  (otimizado em B1+B2)
    → synthesize_tts (tts-1)                ~0.5–1.0s
    ─────────────────────────────────────────────────
    Total fluxo de voz:                      ~3.0–5.0s  (com B1+B2)
```

Três caminhos avaliados no spike:

| Caminho | Infra adicional | Elimina nós | Esforço |
|---------|----------------|-------------|---------|
| **(a) Groq Whisper** | `GROQ_API_KEY` + `groq>=0.8` | nenhum | 5 linhas |
| **(b) `gpt-4o-audio-preview`** | nenhuma — mesma `OPENAI_API_KEY` | nenhum (mantém arquitetura) | ~10 linhas |
| **(c) GPT-4o Realtime** | WebSocket | transcriber + TTS | alto — troca harness SSE |

---

## Decisão: Opção B — `gpt-4o-audio-preview` via Chat Completions REST

**Princípio**: não adicionar nova infra (chave de API + SDK) para otimizações de desempenho
enquanto a escala não justifica. O mesmo `OPENAI_API_KEY` já em uso serve para STT multimodal.

### Implementação

```python
# agent/agent/nodes/transcriber.py
response = await openai_client.chat.completions.create(
    model="gpt-4o-audio-preview",
    modalities=["text"],
    messages=[{
        "role": "user",
        "content": [{
            "type": "input_audio",
            "input_audio": {
                "data": base64.b64encode(audio_bytes).decode(),
                "format": "mp3",
            },
        }],
    }],
)
text = response.choices[0].message.content
```

A arquitetura do grafo não muda — `transcribe_audio` continua como nó separado,
retornando `HumanMessage(content=text)` como antes.

### Trade-offs aceitos

| Aspecto | Valor |
|---|---|
| Nova infra | Nenhuma — `OPENAI_API_KEY` existente |
| Nova dependência | Nenhuma — `openai` já está em `pyproject.toml` |
| Mudança de código | `transcriber.py` — ~10 linhas |
| Latência STT | Maior que Groq (~0.8–1.5s vs ~0.2–0.4s do Groq) |
| Qualidade pt-BR | ✅ Superior ao whisper-1 (modelo maior, contexto de conversação) |
| Custo | Tokens de áudio (~$0.003/s áudio) — ligeiramente maior que whisper-1 |

---

## Opção A — Groq Whisper (documentada, não implementada)

**Quando considerar**: se a latência de STT se tornar gargalo dominante após outras
otimizações e o projeto já tiver `GROQ_API_KEY` por outro motivo.

```python
# Implementação futura — substituir transcriber.py
from groq import AsyncGroq
groq_client = AsyncGroq()  # requer GROQ_API_KEY

transcript = await groq_client.audio.transcriptions.create(
    model="whisper-large-v3-turbo",  # ~0.2–0.4s; ou whisper-large-v3 para mais precisão
    file=audio_file,
)
```

**Latência**: `whisper-large-v3-turbo` ~0.2–0.4s vs `gpt-4o-audio-preview` ~0.8–1.5s.
**Custo**: $0.111/hora de áudio — mais barato que `gpt-4o-audio-preview` em volume.
**Requisito**: `groq>=0.8` em `pyproject.toml` + `GROQ_API_KEY` em `.env`.

---

## Opção C — GPT-4o Realtime (deferida)

Exige substituir o harness SSE por WebSocket. Fora de escopo para spec 005.

---

## Impacto no SC-007

Com B1 (parallel tools) + B2 (prompt eng.) + B5(b) (`gpt-4o-audio-preview`):

```
Baseline (pré-B1/B2):     ~4–7s
Após B1+B2:               ~3.0–5.0s
Após B1+B2+B5(b):         ~2.0–4.0s   →  ~30–50% redução
```

SC-007 (≥50%) é alcançável na faixa favorável. Validação live necessária (T023).
Se SC-007 não for atingido, Groq (Opção A) é o próximo passo natural — 1 linha de mudança.

---

## Consequências

### Aceitas agora
- `gpt-4o-audio-preview` ainda carrega o label "preview" — comportamento estável
  desde outubro 2024, sem breaking changes conhecidos.
- Latência de STT não é tão baixa quanto o Groq — aceitável enquanto B1+B2 são
  as principais fontes de ganho.

### Condições que ativam revisão
1. SC-007 não atingido em medição live → implementar Groq Whisper (Opção A).
2. `GROQ_API_KEY` já disponível no projeto por outro motivo → migração trivial.
3. Requisito de qualidade de voz nativa → Opção C (Realtime).

---

## Referências

- [gpt-4o-audio-preview — OpenAI Docs](https://platform.openai.com/docs/guides/audio)
- [Groq Audio API](https://console.groq.com/docs/speech-text)
- [Research R8](../../specs/005-agent-hardening/research.md#r8) — análise dos três caminhos
- [ADR-027](./ADR-027-latency-tactics.md) — parallel tool calls + round reduction (B1/B2)
- [Learning lesson áudio](../learning-lessons/modelos_audio_multimodal_litellm.md)
