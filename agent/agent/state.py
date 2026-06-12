from typing import Literal
from langgraph.graph import MessagesState


class AgendAIState(MessagesState):
    input_type: Literal["text", "audio"]
    audio_data: bytes | None
    audio_format: str | None  # "wav", "mp3", "webm", "ogg" — declarado pelo chamador
    session_id: str
    email_pending: bool
    email_payload: dict | None
    final_response: str | bytes | None
    context_summary: str | None  # (ADR-030): last summarization text (observability/debug)
