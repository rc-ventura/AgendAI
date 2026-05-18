# ADR-007: OpenAI TTS para síntese de voz (Text-to-Speech)

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/nodes/tts.py`

---

## Contexto

Quando o paciente envia áudio, a resposta do agente também deve ser em áudio (requisito multimodal do desafio técnico). Após o LLM gerar a resposta em texto, ela precisa ser convertida para fala em português.

## Decisão

Usar **OpenAI TTS** (`tts-1`, voice `alloy`) via `openai` Python SDK para sintetizar a resposta do agente em áudio MP3. O áudio gerado é retornado como base64 no estado do grafo e reproduzido pelo Agent UI.

## Alternativas consideradas

### Alternativa A: ElevenLabs
**Por que não**: Vozes mais naturais, mas adiciona fornecedor separado com custo adicional. OpenAI TTS é suficiente para demonstração.

### Alternativa B: Edge TTS / Azure Cognitive Services
**Por que não**: Adiciona segundo cloud provider. OpenAI unifica LLM + STT + TTS.

### Alternativa C: TTS open-source local (Coqui, Piper)
**Por que não**: Qualidade inferior em português. Exige servir modelo no container. Complexidade desnecessária.

### Alternativa D: Modelo multimodal nativo (GPT-4o audio)
**Por que não**: Mais caro. Para MVP, pipeline LLM texto → TTS é mais econômico. Ver ADR-011 (caminho #2).

## Consequências

### Aceitas
- **Voz natural em pt-BR**: `alloy` tem entonação aceitável para português.
- **API unificada**: mesma `OPENAI_API_KEY`.
- **Simples**: ~3 linhas — `client.audio.speech.create(model="tts-1", voice="alloy", input=text)`.
- **Formato universal**: MP3 reproduzido nativamente em todos os browsers.

### Trade-offs
- **Latência**: 2-3s para sintetizar resposta típica (2-3 frases). Somado ao Whisper (~3s) + LLM (~3s), pipeline de áudio total ~8-10s.
- **Custo**: $15/1M caracteres. Resposta típica de 200 caracteres custa ~$0.003.
- **Voz única**: sem escolha de voz pelo paciente. `alloy` é a mais neutra das 6 vozes disponíveis.

### Condições que invalidam
1. Latência total de áudio >10s inaceitável → migrar para multimodal (ADR-011, #2).
2. Necessidade de vozes customizadas (médico específico) → ElevenLabs.
3. Streaming de áudio (ouvir enquanto gera) → TTS com chunked response.

## Referências

- `agent/agent/nodes/tts.py` — nó `synthesize_tts`
- ADR-004: GPT-4o-mini
- ADR-006: Whisper STT
- ADR-011: caminho evolutivo #2 (agente multimodal)
