from langchain_core.runnables import RunnableConfig

from agent.logging_config import set_request_id
from agent.nodes.audio import detect_audio_container, normalize_input_audio_format
from agent.state import AgendAIState


def detect_input_type(state: AgendAIState, config: RunnableConfig | None = None) -> dict:
    """Classify the turn as text or audio and validate the audio container.

    Audio bytes are left in `audio_data` for the transcribe_audio node to consume —
    they never enter `messages` (the transcript does, after STT)."""
    if config:
        set_request_id((config.get("metadata") or {}).get("request_id", "-"))

    raw = state.get("audio_data")
    if not raw:
        return {"input_type": "text"}

    audio_bytes = bytes(raw) if isinstance(raw, list) else raw
    fmt = normalize_input_audio_format(state.get("audio_format"))
    detected = detect_audio_container(audio_bytes)
    if detected in {"wav", "mp3"} and detected != fmt:
        raise ValueError(
            f"audio_format '{fmt}' does not match payload container '{detected}'"
        )
    if detected in {"webm", "ogg"}:
        raise ValueError(
            f"Unsupported payload container '{detected}'. Convert audio to WAV or MP3 before submit"
        )

    return {"input_type": "audio"}
