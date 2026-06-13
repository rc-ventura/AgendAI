import operator
from typing import Annotated, Literal
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
    # Idempotency guard: tool_call_ids that already triggered an email, so a
    # later turn with no tool calls cannot re-detect an old booking and resend.
    processed_tool_ids: Annotated[list[str], operator.add]
