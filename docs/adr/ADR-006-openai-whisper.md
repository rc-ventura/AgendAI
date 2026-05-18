# ADR-006: OpenAI Whisper para Speech-to-Text (STT)

**Status**: Accepted
**Data**: 2026-05-17
**Spec relacionada**: [001-n8n-medical-scheduling](../../specs/001-n8n-medical-scheduling/), [002-langgraph-orchestration](../../specs/002-langgraph-orchestration/)
**Código**: `agent/agent/nodes/transcriber.py`

---

## Contexto

O agente aceita áudio do paciente como entrada (via `AudioUploadButton` no Agent UI). O áudio precisa ser convertido para texto antes de ser processado pelo LLM. O sistema precisa de transcrição precisa em português, com latência aceitável (<5s).

## Decisão

Usar **OpenAI Whisper** (`whisper-1`) via `openai` Python SDK para transcrição de áudio. O áudio é recebido como base64 no estado do grafo, decodificado para bytes e enviado à API.

## Alternativas consideradas

### Alternativa A: Whisper local (open-source)
**Por que não**: Exige GPU ou CPU potente para latência aceitável. Modelo `large-v3` pesa ~3GB. Adiciona complexidade de servir o modelo no container.

### Alternativa B: Google Cloud Speech-to-Text
**Por que não**: Adiciona segundo fornecedor de cloud. OpenAI já cobre LLM + STT + TTS com uma única API key.

### Alternativa C: AssemblyAI / Deepgram
**Por que não**: Fornecedores adicionais com custos separados. Whisper via OpenAI é conveniente por compartilhar a mesma fatura.

### Alternativa D: Modelo multimodal nativo (GPT-4o audio)
**Por que não**: Modelos multimodais são mais caros. Para MVP, pipeline Whisper → LLM texto é mais econômico. Ver ADR-011 (caminho evolutivo #2) para migração futura.

## Consequências

### Aceitas
- **Precisão em português**: Whisper tem boa acurácia para pt-BR, incluindo termos médicos comuns.
- **API unificada**: mesma `OPENAI_API_KEY` do LLM e TTS.
- **Simples**: ~5 linhas de código — `client.audio.transcriptions.create(model="whisper-1", file=audio_bytes)`.

### Trade-offs
- **Latência**: 2-5s para transcrição de áudio típico (10-30s). Gargalo no pipeline de áudio.
- **Custo**: $0.006/minuto de áudio. Conversa típica com áudio de 15s custa ~$0.0015.
- **Sem streaming**: transcrição só retorna após áudio completo — paciente espera.

### Condições que invalidam
1. Latência de áudio inaceitável → migrar para modelo multimodal (ADR-011, caminho #2).
2. Custo proibitivo em escala → Whisper local com GPU.
3. Necessidade de streaming de transcrição → Deepgram ou AssemblyAI.

## Referências

- `agent/agent/nodes/transcriber.py` — nó `transcribe_audio`
- ADR-004: GPT-4o-mini como LLM
- ADR-007: OpenAI TTS
- ADR-011: caminho evolutivo #2 (agente multimodal)
