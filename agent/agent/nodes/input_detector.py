import base64
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState


def detect_input_type(state: AgendAIState) -> dict:
    raw = state.get("audio_data")
    if raw:
        audio_bytes = bytes(raw) if isinstance(raw, list) else raw
        b64 = base64.b64encode(audio_bytes).decode()
        msg = HumanMessage(content=[{
            "type": "input_audio",
            "input_audio": {"data": b64, "format": "mp3"},
        }])
        return {"input_type": "audio", "messages": [msg]}
    return {"input_type": "text"}
