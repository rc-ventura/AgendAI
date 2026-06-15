"""STT node — transcribe user audio to text via Whisper.

gpt-audio-1.5 (chat completions) was tried here but behaves as a conversational
model without a strict transcription prompt — it interprets audio and returns
structured responses instead of literal transcripts. Whisper (audio.transcriptions)
is purpose-built for STT: cheaper, faster, and returns the spoken words verbatim.
"""
import io

from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI

from agent.nodes.audio import normalize_input_audio_format
from agent.state import AgendAIState

_STT_MODEL = "whisper-1"
_openai_client = AsyncOpenAI()


async def transcribe_audio(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if not raw:
        return {}
    audio_bytes = bytes(raw) if isinstance(raw, list) else raw

    # Label the upload with its real container so Whisper does not reject an
    # MP3 payload that was hardcoded as WAV (the pipeline allows wav and mp3).
    fmt = normalize_input_audio_format(state.get("audio_format"))
    transcript = await _openai_client.audio.transcriptions.create(
        model=_STT_MODEL,
        file=(f"audio.{fmt}", io.BytesIO(audio_bytes), f"audio/{fmt}"),
        language="pt",
    )
    text = (transcript.text or "").strip()

    return {
        "messages": [HumanMessage(content=text or "[áudio sem fala reconhecida]")],
        "audio_data": None,
        "audio_format": None,
    }
