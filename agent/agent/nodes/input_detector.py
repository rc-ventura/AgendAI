import base64
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState


def detect_input_type(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if raw:
        audio_bytes = bytes(raw) if isinstance(raw, list) else raw
        b64 = base64.b64encode(audio_bytes).decode()
        fmt = state.get("audio_format") or "wav"
        msg = HumanMessage(content=[{
            "type": "input_audio",
            "input_audio": {"data": b64, "format": fmt},
        }])
        return {"input_type": "audio", "messages": [msg]}
    return {"input_type": "text"}
