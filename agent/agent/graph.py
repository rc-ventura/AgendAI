import base64
import logging
from typing import Literal

logger = logging.getLogger(__name__)

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

from agent.cache import build_cache
from agent.middleware import LLM_MIDDLEWARE
from agent.state import AgendAIState
from agent.nodes.input_detector import detect_input_type
from agent.nodes.llm_core import base_llm, audio_llm, SYSTEM_PROMPT
from agent.nodes.tools import ALL_TOOLS
from agent.nodes.email_sender import send_email
from agent.nodes.tool_result_processor import process_tool_results
from agent.nodes.audio import strip_consumed_audio


def route_by_input_type(state: AgendAIState) -> Literal["text_agent", "audio_agent"]:
    return "audio_agent" if state.get("input_type") == "audio" else "text_agent"


def route_after_agent(state: AgendAIState) -> Literal["send_email", "__end__"]:
    if state.get("email_pending"):
        return "send_email"
    return END


_WAV_SAMPLE_RATE = 24000  # gpt-4o-audio-preview output sample rate
_WAV_CHANNELS = 1
_WAV_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


def _pcm16_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM16 bytes in a RIFF/WAV container so browsers can play it."""
    import struct
    data_size = len(pcm_bytes)
    byte_rate = _WAV_SAMPLE_RATE * _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    block_align = _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1,  # PCM
        _WAV_CHANNELS, _WAV_SAMPLE_RATE, byte_rate, block_align,
        _WAV_SAMPLE_WIDTH * 8,
        b"data", data_size,
    )
    return header + pcm_bytes


def extract_audio_response(state: AgendAIState) -> dict:
    """Extracts audio bytes from the final AIMessage after the audio_agent loop exits,
    then strips the consumed input_audio blob from message history.

    OpenAI only supports pcm16 when stream=True (LangChain always streams).
    We wrap the raw PCM16 bytes in a WAV container so the browser can play them.
    """
    stripped = strip_consumed_audio(state)
    update: dict = {}
    if stripped:
        update["messages"] = stripped

    for msg in reversed(state["messages"]):
        audio_info = getattr(msg, "additional_kwargs", {}).get("audio", {})
        if audio_info and "data" in audio_info:
            raw = base64.b64decode(audio_info["data"])
            update["final_response"] = _pcm16_to_wav(raw)
            return update

    logger.warning(
        "extract_audio_response: no audio data found in %d messages; final_response will be None",
        len(state["messages"]),
    )
    return update


_text_agent = create_agent(base_llm, list(ALL_TOOLS), system_prompt=SYSTEM_PROMPT, middleware=LLM_MIDDLEWARE)

_audio_agent = create_agent(audio_llm, list(ALL_TOOLS), system_prompt=SYSTEM_PROMPT, middleware=LLM_MIDDLEWARE)

builder = StateGraph(AgendAIState)

builder.add_node("detect_input_type", detect_input_type)
builder.add_node("text_agent", _text_agent)
builder.add_node("process_text_results", process_tool_results)
builder.add_node("audio_agent", _audio_agent)
builder.add_node("process_audio_results", process_tool_results)
builder.add_node("extract_audio_response", extract_audio_response)
builder.add_node("send_email", send_email)

builder.add_edge(START, "detect_input_type")
builder.add_conditional_edges(
    "detect_input_type",
    route_by_input_type,
    {"text_agent": "text_agent", "audio_agent": "audio_agent"},
)

# Text path
builder.add_edge("text_agent", "process_text_results")
builder.add_conditional_edges(
    "process_text_results",
    route_after_agent,
    {"send_email": "send_email", END: END},
)

# Audio path
builder.add_edge("audio_agent", "process_audio_results")
builder.add_edge("process_audio_results", "extract_audio_response")
builder.add_conditional_edges(
    "extract_audio_response",
    route_after_agent,
    {"send_email": "send_email", END: END},
)

builder.add_edge("send_email", END)

_MAX_GRAPH_STEPS = 60
graph = builder.compile(cache=build_cache()).with_config({"recursion_limit": _MAX_GRAPH_STEPS})
