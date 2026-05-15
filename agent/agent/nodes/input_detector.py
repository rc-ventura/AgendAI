from agent.state import AgendAIState


def detect_input_type(state: AgendAIState) -> dict:
    return {"input_type": "audio" if state.get("audio_data") else "text"}
