import json
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from agent.state import AgendAIState
from agent.nodes.tool_result_processor import (
    _find_last_email_tool_call,
    _get_tool_message,
    _get_payment_tool_message,
    _build_email_payload,
    process_tool_results,
)


def _make_state(**kwargs) -> AgendAIState:
    defaults: AgendAIState = {
        "messages": [],
        "input_type": "text",
        "audio_data": None,
        "session_id": "test",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    defaults.update(kwargs)
    return defaults


def _ai_with_tool_call(tool_name: str, call_id: str) -> AIMessage:
    msg = AIMessage(content="")
    msg.tool_calls = [{"name": tool_name, "id": call_id, "args": {}}]
    return msg


def _tool_msg(content: str, call_id: str) -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=call_id)


AGENDAMENTO_JSON = json.dumps({
    "sucesso": True,
    "mensagem": "Consulta agendada com sucesso!",
    "agendamento_id": 10,
    "paciente_nome": "João Silva",
    "paciente_email": "joao@email.com",
    "medico_nome": "Dr. Carlos Lima",
    "data_hora": "2026-05-20 09:00",
})

CANCELAMENTO_JSON = json.dumps({
    "sucesso": True,
    "mensagem": "Agendamento cancelado com sucesso.",
    "agendamento_id": 1,
    "paciente_nome": "Maria Souza",
    "paciente_email": "maria@email.com",
    "medico_nome": "Dra. Ana Paula",
    "data_hora": "2026-05-21 14:00",
})

PAGAMENTO_JSON = json.dumps({
    "disponivel": True,
    "descricao": "Consulta",
    "valor": 200.0,
    "formas_pagamento": ["PIX", "Cartão"],
})


# ── _find_last_email_tool_call ─────────────────────────────────────────────────

def test_find_email_tool_call_criar():
    ai = _ai_with_tool_call("criar_agendamento", "call-1")
    state = _make_state(messages=[HumanMessage(content="Agendar"), ai])
    name, call_id = _find_last_email_tool_call(state)
    assert name == "criar_agendamento"
    assert call_id == "call-1"


def test_find_email_tool_call_cancelar():
    ai = _ai_with_tool_call("cancelar_agendamento", "call-2")
    state = _make_state(messages=[ai])
    name, call_id = _find_last_email_tool_call(state)
    assert name == "cancelar_agendamento"
    assert call_id == "call-2"


def test_find_email_tool_call_no_email_tool():
    ai = _ai_with_tool_call("buscar_horarios_disponiveis", "call-3")
    state = _make_state(messages=[ai])
    name, call_id = _find_last_email_tool_call(state)
    assert name is None
    assert call_id is None


def test_find_email_tool_call_no_messages():
    state = _make_state(messages=[HumanMessage(content="Olá")])
    name, call_id = _find_last_email_tool_call(state)
    assert name is None


# ── _get_tool_message ─────────────────────────────────────────────────────────

def test_get_tool_message_found():
    tm = _tool_msg(AGENDAMENTO_JSON, "call-1")
    state = _make_state(messages=[tm])
    result = _get_tool_message(state, "call-1")
    assert result is tm


def test_get_tool_message_not_found():
    tm = _tool_msg(AGENDAMENTO_JSON, "call-1")
    state = _make_state(messages=[tm])
    result = _get_tool_message(state, "call-999")
    assert result is None


# ── _get_payment_tool_message ─────────────────────────────────────────────────

def test_get_payment_tool_message_found():
    pm = _tool_msg(PAGAMENTO_JSON, "pay-1")
    state = _make_state(messages=[pm])
    result = _get_payment_tool_message(state)
    assert result is pm


def test_get_payment_tool_message_not_found():
    state = _make_state(messages=[_tool_msg(AGENDAMENTO_JSON, "call-1")])
    result = _get_payment_tool_message(state)
    assert result is None


def test_get_payment_tool_message_invalid_json():
    state = _make_state(messages=[_tool_msg("texto inválido", "call-x")])
    result = _get_payment_tool_message(state)
    assert result is None


# ── _build_email_payload ──────────────────────────────────────────────────────

def test_build_payload_agendamento_com_pagamento():
    tool_data = json.loads(AGENDAMENTO_JSON)
    payment_data = json.loads(PAGAMENTO_JSON)
    payload = _build_email_payload("criar_agendamento", tool_data, payment_data)

    assert payload["tipo"] == "agendamento"
    assert payload["paciente_nome"] == "João Silva"
    assert payload["paciente_email"] == "joao@email.com"
    assert payload["medico_nome"] == "Dr. Carlos Lima"
    assert payload["data_hora"] == "2026-05-20 09:00"
    assert payload["valor"] == 200.0
    assert payload["formas_pagamento"] == ["PIX", "Cartão"]


def test_build_payload_agendamento_sem_pagamento():
    tool_data = json.loads(AGENDAMENTO_JSON)
    payload = _build_email_payload("criar_agendamento", tool_data, None)

    assert payload["tipo"] == "agendamento"
    assert payload["paciente_nome"] == "João Silva"
    assert payload["valor"] is None
    assert payload["formas_pagamento"] is None


def test_build_payload_cancelamento():
    tool_data = json.loads(CANCELAMENTO_JSON)
    payload = _build_email_payload("cancelar_agendamento", tool_data, None)

    assert payload["tipo"] == "cancelamento"
    assert payload["paciente_nome"] == "Maria Souza"
    assert payload["paciente_email"] == "maria@email.com"
    assert payload["medico_nome"] == "Dra. Ana Paula"
    assert payload["valor"] is None
    assert payload["formas_pagamento"] is None


def test_build_payload_nome_fallback():
    tool_data = {"sucesso": True, "paciente_email": "x@x.com", "data_hora": "2026-01-01 10:00"}
    payload = _build_email_payload("criar_agendamento", tool_data, None)
    assert payload["paciente_nome"] == "Paciente"
    assert payload["medico_nome"] == "Médico"


# ── process_tool_results (integração) ────────────────────────────────────────

def test_process_tool_results_agendamento():
    ai = _ai_with_tool_call("criar_agendamento", "call-1")
    tm = _tool_msg(AGENDAMENTO_JSON, "call-1")
    state = _make_state(messages=[HumanMessage(content="Agendar"), ai, tm])

    result = process_tool_results(state)

    assert result["email_pending"] is True
    assert result["email_payload"]["tipo"] == "agendamento"
    assert result["email_payload"]["paciente_nome"] == "João Silva"
    assert result["email_payload"]["paciente_email"] == "joao@email.com"
    assert result["email_payload"]["medico_nome"] == "Dr. Carlos Lima"


def test_process_tool_results_agendamento_com_pagamento():
    ai = _ai_with_tool_call("criar_agendamento", "call-1")
    tm = _tool_msg(AGENDAMENTO_JSON, "call-1")
    pm = _tool_msg(PAGAMENTO_JSON, "pay-1")
    state = _make_state(messages=[pm, ai, tm])

    result = process_tool_results(state)

    assert result["email_payload"]["valor"] == 200.0
    assert result["email_payload"]["formas_pagamento"] == ["PIX", "Cartão"]


def test_process_tool_results_cancelamento():
    ai = _ai_with_tool_call("cancelar_agendamento", "call-2")
    tm = _tool_msg(CANCELAMENTO_JSON, "call-2")
    state = _make_state(messages=[ai, tm])

    result = process_tool_results(state)

    assert result["email_pending"] is True
    assert result["email_payload"]["tipo"] == "cancelamento"
    assert result["email_payload"]["paciente_nome"] == "Maria Souza"
    assert result["email_payload"]["medico_nome"] == "Dra. Ana Paula"


def test_process_tool_results_nao_email_tool():
    ai = _ai_with_tool_call("buscar_horarios_disponiveis", "call-3")
    tm = _tool_msg("Horários disponíveis...", "call-3")
    state = _make_state(messages=[ai, tm])

    result = process_tool_results(state)
    assert result == {}


def test_process_tool_results_tool_falhou():
    ai = _ai_with_tool_call("criar_agendamento", "call-4")
    tm = _tool_msg(json.dumps({"sucesso": False, "erro": "Horário ocupado"}), "call-4")
    state = _make_state(messages=[ai, tm])

    result = process_tool_results(state)
    assert result == {}


def test_process_tool_results_sem_tool_message():
    ai = _ai_with_tool_call("criar_agendamento", "call-5")
    state = _make_state(messages=[ai])

    result = process_tool_results(state)
    assert result == {}
