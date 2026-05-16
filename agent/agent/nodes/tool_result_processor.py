"""
Inspects the most recent ToolMessages to determine whether email notification
needs to be triggered (criar_agendamento or cancelar_agendamento succeeded).
"""
import json
from langchain_core.messages import ToolMessage, AIMessage

from agent.state import AgendAIState

_EMAIL_TOOLS = {"criar_agendamento", "cancelar_agendamento"}


def _find_last_email_tool_call(state: AgendAIState) -> tuple[str, str] | tuple[None, None]:
    """Returns (tool_name, tool_call_id) for an email-triggering tool call in the
    CURRENT execution round only.

    Only the most recent AIMessage with tool_calls is inspected. If that message
    does not contain any email-triggering tool call, we return (None, None)
    immediately instead of scanning older messages — otherwise tool calls from
    previous turns (already processed) would be re-detected and cause duplicate
    emails to be sent.
    """
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc.get("name") in _EMAIL_TOOLS:
                    return tc["name"], tc["id"]
            return None, None
    return None, None


def _get_tool_message(state: AgendAIState, tool_call_id: str) -> ToolMessage | None:
    """Finds the ToolMessage that matches a given tool_call_id."""
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage) and msg.tool_call_id == tool_call_id:
            return msg
    return None


def _get_payment_tool_message(state: AgendAIState) -> ToolMessage | None:
    """Finds the most recent ToolMessage from buscar_pagamentos, if any."""
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
            if "formas_pagamento" in data and "valor" in data:
                return msg
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _parse_json(msg: ToolMessage) -> dict:
    try:
        return json.loads(msg.content)
    except (json.JSONDecodeError, TypeError):
        return {}


def _build_email_payload(tool_name: str, tool_data: dict, payment_data: dict | None) -> dict:
    if tool_name == "criar_agendamento":
        return {
            "tipo": "agendamento",
            "paciente_email": tool_data.get("paciente_email", ""),
            "paciente_nome": tool_data.get("paciente_nome") or "Paciente",
            "medico_nome": tool_data.get("medico_nome") or "Médico",
            "data_hora": tool_data.get("data_hora", ""),
            "valor": payment_data.get("valor") if payment_data else None,
            "formas_pagamento": payment_data.get("formas_pagamento") if payment_data else None,
        }
    return {
        "tipo": "cancelamento",
        "paciente_email": tool_data.get("paciente_email", ""),
        "paciente_nome": tool_data.get("paciente_nome") or "Paciente",
        "medico_nome": tool_data.get("medico_nome") or "Médico",
        "data_hora": tool_data.get("data_hora", ""),
        "valor": None,
        "formas_pagamento": None,
    }


def process_tool_results(state: AgendAIState) -> dict:
    tool_name, tool_call_id = _find_last_email_tool_call(state)
    if tool_name is None:
        return {}

    tool_msg = _get_tool_message(state, tool_call_id)
    if tool_msg is None:
        return {}

    tool_data = _parse_json(tool_msg)
    if not tool_data.get("sucesso"):
        return {}

    payment_msg = _get_payment_tool_message(state) if tool_name == "criar_agendamento" else None
    payment_data = _parse_json(payment_msg) if payment_msg else None

    payload = _build_email_payload(tool_name, tool_data, payment_data)
    return {"email_pending": True, "email_payload": payload}
