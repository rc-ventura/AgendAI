"""Audio pre/post-processing helpers for the audio path of the graph.

Keeps the audio-blob handling out of graph.py, which stays focused on wiring
the StateGraph and the graph-level node functions.
"""

from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI

from agent.state import AgendAIState

# B1: dedicated text-to-speech for the audio path. The /audio/speech endpoint is a
# plain non-streaming HTTP call that returns a complete WAV container, so we avoid
# both the PCM16 streaming constraint and LangChain #29776 (audio dropped on the
# chat model's streamed output).
_TTS_MODEL = "gpt-4o-mini-tts"
_TTS_VOICE = "alloy"
_tts_client = AsyncOpenAI()


async def text_to_speech_wav(text: str) -> bytes:
    """Synthesize `text` to speech, returning a full WAV file (bytes)."""
    response = await _tts_client.audio.speech.create(
        model=_TTS_MODEL,
        voice=_TTS_VOICE,
        input=text,
        response_format="wav",
    )
    return response.content


def normalize_input_audio_format(raw_format: str | None) -> str:
    """Normalize caller-provided format/MIME into OpenAI `input_audio.format`.

    Supported values for our Chat Completions audio-input flow: wav and mp3.
    """
    if not raw_format:
        return "wav"

    fmt = str(raw_format).strip().lower()
    if "/" in fmt:
        fmt = fmt.split("/", 1)[1]
    if ";" in fmt:
        fmt = fmt.split(";", 1)[0]

    aliases = {
        "mpeg": "mp3",
        "x-wav": "wav",
        "wave": "wav",
    }
    fmt = aliases.get(fmt, fmt)

    allowed = {"wav", "mp3"}
    if fmt not in allowed:
        raise ValueError(
            f"Unsupported input audio format '{raw_format}'. Supported formats: wav, mp3"
        )
    return fmt


def detect_audio_container(audio_bytes: bytes) -> str:
    """Best-effort detection for wav/mp3 containers to catch mislabeled payloads."""
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "wav"
    if audio_bytes[:3] == b"ID3":
        return "mp3"
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return "mp3"
    return "unknown"


def is_input_audio_message(msg) -> bool:
    """True if msg is a HumanMessage carrying an input_audio content part."""
    content = getattr(msg, "content", None)
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") == "input_audio" for p in content
    )


def strip_consumed_audio(state: AgendAIState) -> list:
    """Replace consumed input_audio HumanMessages with a lightweight text placeholder."""
    replacements = []
    for msg in state["messages"]:
        if is_input_audio_message(msg) and getattr(msg, "id", None):
            replacements.append(HumanMessage(id=msg.id, content="[mensagem de voz]"))
    return replacements
