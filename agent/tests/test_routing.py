"""TST-07 — Unit tests for graph routing functions."""
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent.state import AgendAIState
from agent.graph import route_after_input, route_after_llm, route_after_email


def make_state(**kwargs) -> AgendAIState:
    base: AgendAIState = {
        "messages": [HumanMessage(content="Olá")],
        "input_type": "text",
        "audio_data": None,
        "session_id": "test-routing",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    base.update(kwargs)
    return base


# ── route_after_input ─────────────────────────────────────────────────────────

def test_route_after_input_text():
    state = make_state(input_type="text")
    assert route_after_input(state) == "chat_with_llm"


def test_route_after_input_audio():
    state = make_state(input_type="audio")
    assert route_after_input(state) == "transcribe_audio"


# ── route_after_llm ───────────────────────────────────────────────────────────

def test_route_after_llm_tool_calls():
    ai_msg = AIMessage(content="", tool_calls=[
        {"id": "call_1", "name": "buscar_horarios_disponiveis", "args": {}}
    ])
    state = make_state(messages=[HumanMessage(content="Olá"), ai_msg])
    assert route_after_llm(state) == "execute_tools"


def test_route_after_llm_email_pending():
    ai_msg = AIMessage(content="Consulta agendada!")
    state = make_state(
        messages=[HumanMessage(content="Olá"), ai_msg],
        email_pending=True,
    )
    assert route_after_llm(state) == "send_email"


def test_route_after_llm_audio_synthesize():
    ai_msg = AIMessage(content="Temos horários disponíveis!")
    state = make_state(
        messages=[HumanMessage(content="Olá"), ai_msg],
        input_type="audio",
        email_pending=False,
    )
    assert route_after_llm(state) == "synthesize_tts"


def test_route_after_llm_text_ends():
    ai_msg = AIMessage(content="Resposta final.")
    state = make_state(
        messages=[HumanMessage(content="Olá"), ai_msg],
        input_type="text",
        email_pending=False,
    )
    assert route_after_llm(state) == "__end__"


def test_route_after_llm_tool_calls_take_priority_over_email():
    """tool_calls must be routed to execute_tools even when email_pending is True."""
    ai_msg = AIMessage(content="", tool_calls=[
        {"id": "call_2", "name": "criar_agendamento", "args": {}}
    ])
    state = make_state(
        messages=[HumanMessage(content="Olá"), ai_msg],
        email_pending=True,
    )
    assert route_after_llm(state) == "execute_tools"


# ── route_after_email ─────────────────────────────────────────────────────────

def test_route_after_email_audio_synthesize():
    state = make_state(input_type="audio")
    assert route_after_email(state) == "synthesize_tts"


def test_route_after_email_text_ends():
    state = make_state(input_type="text")
    assert route_after_email(state) == "__end__"
