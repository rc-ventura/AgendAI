"""Audio input validation helpers for the voice path.

Output synthesis lives in tts.py and transcription in transcriber.py; this module
keeps only the input-side format/container checks so a mislabeled or unsupported
payload fails with a clear local error before reaching OpenAI.
"""


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
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b"\x1aE\xdf\xa3":
        return "webm"  # EBML header (webm/mkv)
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b"OggS":
        return "ogg"
    return "unknown"
