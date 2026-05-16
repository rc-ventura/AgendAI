from typing import Annotated, Literal
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgendAIState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    input_type: Literal["text", "audio"]
    audio_data: bytes | None
    session_id: str
    email_pending: bool
    email_payload: dict | None
    final_response: str | bytes | None
