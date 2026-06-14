# ADR-031: Reverter áudio multimodal → pipeline STT+TTS isolado

**Status**: Accepted
**Data**: 2026-06-14
**Spec relacionada**: [005-agent-hardening](../../specs/005-agent-hardening/)
**Supersede**: [ADR-028](./ADR-028-audio-model.md) (gpt-audio multimodal de chamada única)
**SC afetado**: SC-007 (latência de áudio)

---

## Contexto

O ADR-028 trocou o pipeline STT+TTS (3 chamadas: Whisper → LLM → TTS) por um modelo
multimodal único (`gpt-audio`) que faria transcrição, raciocínio e síntese numa só
chamada de Chat Completions dentro do agente LangGraph.

Em validação ao vivo contra a infra real (nginx → LangGraph Server → Postgres/Redis),
isso **não funcionou**. Dois bloqueios independentes, ambos causados pelo **streaming SSE
forçado** que o LangGraph Server aplica a toda chamada de LLM via LangChain:

1. **Áudio de saída descartado** — sob streaming, o LangChain não popula
   `additional_kwargs["audio"]`; `final_response` voltava `None`.
   Fonte: [LangChain #29776](https://github.com/langchain-ai/langchain/issues/29776)
   (aberto fev/2025, fechado sem fix).

2. **`The model produced invalid content`** — com fala real (que dispara tool calls),
   o `gpt-audio` produz conteúdo malformado sob streaming + tools. A sine wave do teste
   passava porque não gerava tool calls; fala real quebrava.
   Fonte: [OpenAI Community](https://community.openai.com/t/error-the-model-produced-invalid-content/747511).

Tentou-se ainda o **B1** (gpt-audio responde em texto + nó TTS dedicado). O bloqueio nº 2
derrubou também essa variante: o `gpt-audio` não consegue dirigir o loop de tools sob
streaming, nem mesmo para saída de texto.

## Decisão

Reverter ao padrão **STT + TTS isolados**, adaptado ao agente endurecido do spec 005:

```
detect_input_type → transcribe_audio (STT)  → text_agent (gpt-4o-mini + middleware + tools)
                                             → process_results
                                             → [send_email] → synthesize_tts (turno de áudio) → END
```

- **STT** (`transcriber.py`): `gpt-audio-1.5` via Chat Completions **raw** (SDK OpenAI direto),
  `modalities=["text"]`, **sem streaming, sem tools** — a forma que funciona. Mantém a
  compreensão nativa de voz; só não fica no loop do agente.
- **TTS** (`tts.py`): `gpt-4o-mini-tts`, `response_format="wav"` (browser toca direto),
  retry com tenacity.
- **Agente**: o mesmo `text_agent` (`gpt-4o-mini` + middleware + tools) serve texto e voz.
  O `gpt-audio` sai inteiramente do loop do agente.
- **Entrada**: validação preservada (`normalize_input_audio_format`, `detect_audio_container`);
  cliente converte WEBM→WAV antes de enviar.

## Consequências

**Positivas**
- Voz funciona ponta-a-ponta de forma robusta (validado: 6/6 runs com WAV válido).
- Reaproveita todo o hardening do spec 005 (middleware, circuit breaker, PII, retry) no turno de voz.
- Tool-calling confiável na voz (era o requisito duro para agendamento).

**Negativas / trade-offs**
- Volta a ~2–3 chamadas no fluxo de voz (STT + LLM + TTS) — SC-007 ("≥50% redução")
  fica **não atingido** por esta via; é o preço da confiabilidade neste harness.
- Latência de voz dominada por STT (gpt-audio) + TTS; observados outliers de variância/RPM.
- Payload WAV de entrada é grande (ver [learning-lesson](../learning-lessons/audio_multimodal_b5_validacao.md) Lições 7–8): manter `client_max_body_size` no nginx e cap de duração no cliente.

## Não-objetivo (deferido)

Um **agente de voz performático** (latência baixa, possivelmente Realtime API/WebSocket,
ou multimodal quando o ecossistema LangChain/LangGraph suportar áudio-out sob streaming)
fica para uma **spec dedicada**, estudada à parte. Esta reversão apenas restabelece um
fluxo de voz confiável antes de seguir com o spec 005.

## Referências

- [ADR-028](./ADR-028-audio-model.md) — decisão revertida
- [Learning lesson: áudio B5](../learning-lessons/audio_multimodal_b5_validacao.md) — Lições 5–9 (cadeia causal completa)
- [LangChain #29776](https://github.com/langchain-ai/langchain/issues/29776) · [#20980](https://github.com/langchain-ai/langchain/issues/20980)
