import pytest
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph.message import add_messages

from agent.state import AgendAIState


def test_state_has_required_fields():
    state: AgendAIState = {
        "messages": [],
        "input_type": "text",
        "audio_data": None,
        "session_id": "s1",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    assert state["input_type"] == "text"
    assert state["email_pending"] is False
    assert state["audio_data"] is None


def test_add_messages_accumulates():
    existing = [HumanMessage(content="Olá")]
    new_msg = [AIMessage(content="Oi!")]
    result = add_messages(existing, new_msg)
    assert len(result) == 2
    assert result[0].content == "Olá"
    assert result[1].content == "Oi!"


def test_state_audio_type():
    state: AgendAIState = {
        "messages": [],
        "input_type": "audio",
        "audio_data": b"fake_audio_bytes",
        "session_id": "s2",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    assert state["input_type"] == "audio"
    assert isinstance(state["audio_data"], bytes)


def test_email_payload_structure():
    payload = {
        "tipo": "agendamento",
        "paciente_email": "joao@email.com",
        "paciente_nome": "João Silva",
        "medico_nome": "Dr. Carlos Lima",
        "data_hora": "2026-05-20 09:00",
        "valor": 200.0,
        "formas_pagamento": ["PIX", "Cartão"],
    }
    state: AgendAIState = {
        "messages": [],
        "input_type": "text",
        "audio_data": None,
        "session_id": "s3",
        "email_pending": True,
        "email_payload": payload,
        "final_response": None,
    }
    assert state["email_pending"] is True
    assert state["email_payload"]["tipo"] == "agendamento"
