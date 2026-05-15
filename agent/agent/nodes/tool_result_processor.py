"""
Inspects the most recent ToolMessages to determine whether email notification
needs to be triggered (criar_agendamento or cancelar_agendamento succeeded).
"""
import json
from langchain_core.messages import ToolMessage, AIMessage

from agent.state import AgendAIState

_EMAIL_TOOLS = {"criar_agendamento", "cancelar_agendamento"}


def _find_last_tool_call_name(state: AgendAIState) -> str | None:
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            return msg.tool_calls[0].get("name")
    return None


def _build_email_payload(state: AgendAIState, tool_name: str) -> dict | None:
    # Find the last ToolMessage result
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            continue
        # Parse agendamento result from criar_agendamento tool output
        if tool_name == "criar_agendamento":
            return {
                "tipo": "agendamento",
                "paciente_email": _extract_field(state, "paciente_email"),
                "paciente_nome": _extract_field(state, "paciente_nome") or "Paciente",
                "medico_nome": _extract_field(state, "medico_nome") or "Médico",
                "data_hora": _extract_field(state, "data_hora") or "",
                "valor": _extract_field(state, "valor"),
                "formas_pagamento": _extract_field(state, "formas_pagamento"),
            }
        if tool_name == "cancelar_agendamento":
            return {
                "tipo": "cancelamento",
                "paciente_email": _extract_field(state, "paciente_email") or "",
                "paciente_nome": _extract_field(state, "paciente_nome") or "Paciente",
                "medico_nome": _extract_field(state, "medico_nome") or "Médico",
                "data_hora": _extract_field(state, "data_hora") or "",
                "valor": None,
                "formas_pagamento": None,
            }
    return None


def _extract_field(state: AgendAIState, field: str):
    """Best-effort extraction of contextual data from tool messages content."""
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            content = msg.content or ""
            # Simple heuristic: look for structured data in content
            if field == "paciente_email" and "@" in content:
                import re
                match = re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", content)
                if match:
                    return match.group(0)
            if field == "data_hora":
                import re
                match = re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", content)
                if match:
                    return match.group(0).replace("T", " ")
            if field == "medico_nome" and "Dr." in content:
                import re
                match = re.search(r"Dr\.?\s+[\w\s]+", content)
                if match:
                    return match.group(0).strip()
    return None


def process_tool_results(state: AgendAIState) -> dict:
    tool_name = _find_last_tool_call_name(state)
    if tool_name in _EMAIL_TOOLS:
        payload = _build_email_payload(state, tool_name)
        return {"email_pending": True, "email_payload": payload}
    return {}
