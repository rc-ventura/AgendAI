"""STT node — transcribe the user's audio to text via a raw OpenAI call.

Spec 005 / B5 tried gpt-audio multimodal (STT + reasoning + TTS in a single model
call inside the agent). That does NOT survive the LangGraph Server's forced SSE
streaming: gpt-audio drops audio output entirely (LangChain #29776) and raises
"The model produced invalid content" on tool-calling turns with real speech.

So STT is isolated here as a plain non-streaming call with no tools — robust — and
the transcript flows through the normal text agent (gpt-4o-mini). A performant
voice agent is deferred to a dedicated future spec.
"""
import base64

from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI

from agent.nodes.audio import normalize_input_audio_format
from agent.state import AgendAIState

# gpt-audio understands voice natively (prosody/context), used here only for STT
# via a raw, non-streaming, tool-free Chat Completions call — the shape that works.
_STT_MODEL = "gpt-audio-1.5"
_openai_client = AsyncOpenAI()


async def transcribe_audio(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if not raw:
        return {}
    audio_bytes = bytes(raw) if isinstance(raw, list) else raw
    fmt = normalize_input_audio_format(state.get("audio_format"))

    response = await _openai_client.chat.completions.create(
        model=_STT_MODEL,
        modalities=["text"],
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um transcritor de áudio. Transcreva exatamente o que "
                    "o usuário disse, palavra por palavra, em português. "
                    "Retorne apenas o texto transcrito, sem resposta, interpretação "
                    "ou formatação adicional."
                ),
            },
            {
                "role": "user",
                "content": [{
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": fmt,
                    },
                }],
            },
        ],
    )
    text = (response.choices[0].message.content or "").strip()

    # The UI sends a "🎙" HumanMessage placeholder with a UUID. Find it and
    # overwrite it with the transcript using the same id — the add_messages
    # reducer replaces in-place when ids match, so the thread shows one message.
    placeholder_id = None
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            placeholder_id = getattr(msg, "id", None)
            break

    return {
        "messages": [HumanMessage(
            content=text or "[áudio sem fala reconhecida]",
            id=placeholder_id,
        )],
        "audio_data": None,
        "audio_format": None,
    }
