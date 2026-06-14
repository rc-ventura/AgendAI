"""TST-07 — Unit tests for graph routing functions."""
from langchain_core.messages import HumanMessage, AIMessage

from agent.state import AgendAIState
from agent.graph import route_after_input, route_after_agent, route_after_email


def make_state(**kwargs) -> AgendAIState:
    base: AgendAIState = {
        "messages": [HumanMessage(content="Olá")],
        "input_type": "text",
        "audio_data": None,
        "audio_format": None,
        "session_id": "test-routing",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    base.update(kwargs)
    return base


# ── route_after_input ─────────────────────────────────────────────────────────

def test_route_after_input_text_goes_to_text_agent():
    state = make_state(input_type="text")
    assert route_after_input(state) == "text_agent"


def test_route_after_input_audio_goes_to_transcribe():
    state = make_state(input_type="audio")
    assert route_after_input(state) == "transcribe_audio"


def test_route_after_input_default_is_text_agent():
    """Missing input_type defaults to text path."""
    state = make_state()
    state.pop("input_type", None)
    assert route_after_input(state) == "text_agent"


# ── route_after_agent ─────────────────────────────────────────────────────────

def test_route_after_agent_email_pending_sends_email():
    state = make_state(
        messages=[HumanMessage(content="Olá"), AIMessage(content="Agendado!")],
        email_pending=True,
    )
    assert route_after_agent(state) == "send_email"


def test_route_after_agent_no_email_ends():
    state = make_state(
        messages=[HumanMessage(content="Olá"), AIMessage(content="Resposta final.")],
        email_pending=False,
    )
    assert route_after_agent(state) == "__end__"


def test_route_after_agent_audio_no_email_synthesizes():
    """Audio turn with no email → synthesize TTS before ending."""
    state = make_state(
        messages=[HumanMessage(content="Olá"), AIMessage(content="Temos horários!")],
        input_type="audio",
        email_pending=False,
    )
    assert route_after_agent(state) == "synthesize_tts"


def test_route_after_agent_audio_with_email_sends_email_first():
    """email_pending takes priority; TTS happens after send_email (route_after_email)."""
    state = make_state(
        messages=[HumanMessage(content="Olá"), AIMessage(content="Agendado!")],
        input_type="audio",
        email_pending=True,
    )
    assert route_after_agent(state) == "send_email"


def test_route_after_email_audio_synthesizes():
    """After sending the email, an audio turn still needs the spoken reply."""
    state = make_state(input_type="audio", email_pending=True)
    assert route_after_email(state) == "synthesize_tts"


def test_route_after_email_text_ends():
    state = make_state(input_type="text", email_pending=True)
    assert route_after_email(state) == "__end__"
