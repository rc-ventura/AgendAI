import base64
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from agent.logging_config import set_request_id
from agent.state import AgendAIState


def detect_input_type(state: AgendAIState, config: RunnableConfig | None = None) -> dict:
    if config:
        set_request_id((config.get("metadata") or {}).get("request_id", "-"))
    raw = state.get("audio_data")
    if raw:
        audio_bytes = bytes(raw) if isinstance(raw, list) else raw
        b64 = base64.b64encode(audio_bytes).decode()
        fmt = state.get("audio_format") or "wav"
        msg = HumanMessage(content=[{
            "type": "input_audio",
            "input_audio": {"data": b64, "format": fmt},
        }])
        return {
            "input_type": "audio",
            "messages": [msg],
            "audio_data": None,
            "audio_format": None,
        }
    return {"input_type": "text"}
