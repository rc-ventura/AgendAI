import base64
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState


def _detect_format(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return "wav"
    if data[:4] in (b"\x1aE\xdf\xa3", b"\x1aE\xdf\xa4"):
        return "webm"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    return "mp3"


def detect_input_type(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if raw:
        audio_bytes = bytes(raw) if isinstance(raw, list) else raw
        b64 = base64.b64encode(audio_bytes).decode()
        fmt = _detect_format(audio_bytes)
        msg = HumanMessage(content=[{
            "type": "input_audio",
            "input_audio": {"data": b64, "format": fmt},
        }])
        return {"input_type": "audio", "messages": [msg]}
    return {"input_type": "text"}
