from typing import Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage

from agent.state import AgendAIState
from agent.nodes.input_detector import detect_input_type
from agent.nodes.transcriber import transcribe_audio
from agent.nodes.llm_core import chat_with_llm
from agent.nodes.tools import tool_node, ALL_TOOLS
from agent.nodes.email_sender import send_email
from agent.nodes.tts import synthesize_tts
from agent.nodes.tool_result_processor import process_tool_results


def route_after_input(state: AgendAIState) -> Literal["transcribe_audio", "chat_with_llm"]:
    return "transcribe_audio" if state["input_type"] == "audio" else "chat_with_llm"


def route_after_llm(state: AgendAIState) -> Literal["execute_tools", "send_email", "synthesize_tts", "__end__"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "execute_tools"
    if state.get("email_pending"):
        return "send_email"
    if state.get("input_type") == "audio":
        return "synthesize_tts"
    return END


def route_after_email(state: AgendAIState) -> Literal["synthesize_tts", "__end__"]:
    return "synthesize_tts" if state.get("input_type") == "audio" else END


builder = StateGraph(AgendAIState)

builder.add_node("detect_input_type", detect_input_type)
builder.add_node("transcribe_audio", transcribe_audio)
builder.add_node("chat_with_llm", chat_with_llm)
builder.add_node("execute_tools", tool_node)
builder.add_node("process_tool_results", process_tool_results)
builder.add_node("send_email", send_email)
builder.add_node("synthesize_tts", synthesize_tts)

builder.add_edge(START, "detect_input_type")
builder.add_conditional_edges("detect_input_type", route_after_input)
builder.add_edge("transcribe_audio", "chat_with_llm")
builder.add_conditional_edges(
    "chat_with_llm",
    route_after_llm,
    {"execute_tools": "execute_tools", "send_email": "send_email",
     "synthesize_tts": "synthesize_tts", END: END},
)
builder.add_edge("execute_tools", "process_tool_results")
builder.add_edge("process_tool_results", "chat_with_llm")
builder.add_conditional_edges("send_email", route_after_email,
                              {"synthesize_tts": "synthesize_tts", END: END})
builder.add_edge("synthesize_tts", END)

graph = builder.compile()
