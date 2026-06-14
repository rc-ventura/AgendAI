import logging
from typing import Literal

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent.cache import build_cache
from agent.middleware import LLM_MIDDLEWARE
from agent.nodes.audio import strip_consumed_audio, text_to_speech_wav
from agent.nodes.email_sender import send_email
from agent.nodes.input_detector import detect_input_type
from agent.nodes.llm_core import SYSTEM_PROMPT, audio_llm, base_llm
from agent.nodes.tool_result_processor import process_tool_results
from agent.nodes.tools import ALL_TOOLS
from agent.state import AgendAIState

logger = logging.getLogger(__name__)


def route_by_input_type(state: AgendAIState) -> Literal["text_agent", "audio_agent"]:
    return "audio_agent" if state.get("input_type") == "audio" else "text_agent"


def route_after_agent(state: AgendAIState) -> Literal["send_email", "__end__"]:
    if state.get("email_pending"):
        return "send_email"
    return END


def _last_ai_text(state: AgendAIState) -> str:
    """Return the text of the final assistant reply (str content or text parts)."""
    for msg in reversed(state["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            joined = " ".join(p for p in parts if p).strip()
            if joined:
                return joined
    return ""


async def synthesize_audio_response(state: AgendAIState) -> dict:
    """B1: the audio agent replies in TEXT (gpt-audio understands the voice input
    natively); we synthesize that text to speech via a dedicated OpenAI TTS call.

    The TTS endpoint is a plain non-streaming HTTP request that returns a complete
    WAV, so no audio is lost to LangChain #29776 and no PCM16 wrapping is needed.
    Also strips the consumed input_audio blob from message history."""
    stripped = strip_consumed_audio(state)
    update: dict = {}
    if stripped:
        update["messages"] = stripped

    text = _last_ai_text(state)
    if not text:
        logger.warning(
            "synthesize_audio_response: no assistant text found in %d messages; "
            "final_response will be None",
            len(state["messages"]),
        )
        return update

    update["final_response"] = await text_to_speech_wav(text)
    return update


_text_agent = create_agent(
    base_llm,
    list(ALL_TOOLS),
    system_prompt=SYSTEM_PROMPT,
    middleware=LLM_MIDDLEWARE,
)

_audio_agent = create_agent(
    audio_llm,
    list(ALL_TOOLS),
    system_prompt=SYSTEM_PROMPT,
    middleware=LLM_MIDDLEWARE,
)

builder = StateGraph(AgendAIState)

builder.add_node("detect_input_type", detect_input_type)
builder.add_node("text_agent", _text_agent)
builder.add_node("process_text_results", process_tool_results)
builder.add_node("audio_agent", _audio_agent)
builder.add_node("process_audio_results", process_tool_results)
builder.add_node("synthesize_audio_response", synthesize_audio_response)
builder.add_node("send_email", send_email)

builder.add_edge(START, "detect_input_type")
builder.add_conditional_edges(
    "detect_input_type",
    route_by_input_type,
    {"text_agent": "text_agent", "audio_agent": "audio_agent"},
)

builder.add_edge("text_agent", "process_text_results")
builder.add_conditional_edges(
    "process_text_results",
    route_after_agent,
    {"send_email": "send_email", END: END},
)

builder.add_edge("audio_agent", "process_audio_results")
builder.add_edge("process_audio_results", "synthesize_audio_response")
builder.add_conditional_edges(
    "synthesize_audio_response",
    route_after_agent,
    {"send_email": "send_email", END: END},
)

builder.add_edge("send_email", END)

_MAX_GRAPH_STEPS = 60
graph = builder.compile(cache=build_cache()).with_config({"recursion_limit": _MAX_GRAPH_STEPS})
