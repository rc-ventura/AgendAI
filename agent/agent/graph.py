from typing import Literal

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage

from agent.cache import build_cache
from agent.state import AgendAIState
from agent.nodes.input_detector import detect_input_type
from agent.nodes.llm_core import chat_with_llm
from agent.nodes.tools import tool_node
from agent.nodes.email_sender import send_email
from agent.nodes.tool_result_processor import process_tool_results


def route_after_llm(state: AgendAIState) -> Literal["execute_tools", "send_email", "__end__"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "execute_tools"
    if state.get("email_pending"):
        return "send_email"
    return END


builder = StateGraph(AgendAIState)

builder.add_node("detect_input_type", detect_input_type)
builder.add_node("chat_with_llm", chat_with_llm)
builder.add_node("execute_tools", tool_node)
builder.add_node("process_tool_results", process_tool_results)
builder.add_node("send_email", send_email)

builder.add_edge(START, "detect_input_type")
builder.add_edge("detect_input_type", "chat_with_llm")
builder.add_conditional_edges(
    "chat_with_llm",
    route_after_llm,
    {"execute_tools": "execute_tools", "send_email": "send_email", END: END},
)
builder.add_edge("execute_tools", "process_tool_results")
builder.add_edge("process_tool_results", "chat_with_llm")
builder.add_edge("send_email", END)

# B4 (ADR-025): Redis cache backend. Nodes opt-in via CachePolicy — none configured
# yet (execute_tools mixes stable + dynamic tools; safe split deferred to a future batch).
graph = builder.compile(cache=build_cache())
