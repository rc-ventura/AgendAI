import logging
from typing import Literal

from langchain.agents import create_agent
from langgraph.graph import END, START, StateGraph

from agent.cache import build_cache
from agent.middleware import LLM_MIDDLEWARE
from agent.nodes.email_sender import send_email
from agent.nodes.input_detector import detect_input_type
from agent.nodes.llm_core import SYSTEM_PROMPT, base_llm
from agent.nodes.tool_result_processor import process_tool_results
from agent.nodes.tools import ALL_TOOLS
from agent.nodes.transcriber import transcribe_audio
from agent.nodes.tts import synthesize_tts
from agent.state import AgendAIState

logger = logging.getLogger(__name__)


def route_after_input(state: AgendAIState) -> Literal["transcribe_audio", "text_agent"]:
    return "transcribe_audio" if state.get("input_type") == "audio" else "text_agent"


def route_after_agent(state: AgendAIState) -> Literal["send_email", "synthesize_tts", "__end__"]:
    if state.get("email_pending"):
        return "send_email"
    if state.get("input_type") == "audio":
        return "synthesize_tts"
    return END


def route_after_email(state: AgendAIState) -> Literal["synthesize_tts", "__end__"]:
    return "synthesize_tts" if state.get("input_type") == "audio" else END


# Single text agent (gpt-4o-mini) with the full middleware + tool stack. The voice
# path transcribes to text first (transcribe_audio) and synthesizes the reply
# afterwards (synthesize_tts), so the robust text agent serves both modalities.
_text_agent = create_agent(
    base_llm,
    list(ALL_TOOLS),
    system_prompt=SYSTEM_PROMPT,
    middleware=LLM_MIDDLEWARE,
)

builder = StateGraph(AgendAIState)

builder.add_node("detect_input_type", detect_input_type)
builder.add_node("transcribe_audio", transcribe_audio)
builder.add_node("text_agent", _text_agent)
builder.add_node("process_results", process_tool_results)
builder.add_node("send_email", send_email)
builder.add_node("synthesize_tts", synthesize_tts)

builder.add_edge(START, "detect_input_type")
builder.add_conditional_edges(
    "detect_input_type",
    route_after_input,
    {"transcribe_audio": "transcribe_audio", "text_agent": "text_agent"},
)
builder.add_edge("transcribe_audio", "text_agent")
builder.add_edge("text_agent", "process_results")
builder.add_conditional_edges(
    "process_results",
    route_after_agent,
    {"send_email": "send_email", "synthesize_tts": "synthesize_tts", END: END},
)
builder.add_conditional_edges(
    "send_email",
    route_after_email,
    {"synthesize_tts": "synthesize_tts", END: END},
)
builder.add_edge("synthesize_tts", END)

_MAX_GRAPH_STEPS = 60
graph = builder.compile(cache=build_cache()).with_config({"recursion_limit": _MAX_GRAPH_STEPS})
