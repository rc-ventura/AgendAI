import asyncio
import os

import resend
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.state import AgendAIState


def _build_message(payload: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for the email."""
    if payload["tipo"] == "agendamento":
        subject = f"AgendAI — Confirmação de consulta em {payload['data_hora']}"
        formas = ", ".join(payload.get("formas_pagamento") or [])
        valor = payload.get("valor")
        body = (
            f"<p>Olá, <strong>{payload['paciente_nome']}</strong>!</p>"
            f"<p>Sua consulta foi agendada com sucesso.</p>"
            f"<ul>"
            f"<li><strong>Médico:</strong> {payload['medico_nome']}</li>"
            f"<li><strong>Data/Hora:</strong> {payload['data_hora']}</li>"
            + (f"<li><strong>Valor:</strong> R$ {valor:.2f}</li>" if valor else "")
            + (f"<li><strong>Formas de pagamento:</strong> {formas}</li>" if formas else "")
            + "</ul><p>Até logo!<br>Equipe AgendAI</p>"
        )
    else:
        subject = f"AgendAI — Consulta cancelada em {payload['data_hora']}"
        body = (
            f"<p>Olá, <strong>{payload['paciente_nome']}</strong>!</p>"
            f"<p>Sua consulta com <strong>{payload['medico_nome']}</strong> "
            f"em <strong>{payload['data_hora']}</strong> foi cancelada com sucesso.</p>"
            f"<p>Se precisar reagendar, estamos à disposição.</p>"
            f"<p>Equipe AgendAI</p>"
        )
    return subject, body


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _send_resend(subject: str, html_body: str, to_email: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print(f"[email_sender] Skipping email (no RESEND_API_KEY): {subject} → {to_email}")
        return

    resend.api_key = api_key
    email_from = os.environ.get("EMAIL_FROM", "AgendAI <onboarding@resend.dev>")

    resend.Emails.send({
        "from": email_from,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    })


async def send_email(state: AgendAIState) -> dict:
    payload = state.get("email_payload")
    if not payload:
        return {"email_pending": False, "email_payload": None}

    subject, html_body = _build_message(payload)
    try:
        await asyncio.to_thread(_send_resend, subject, html_body, payload["paciente_email"])
    except Exception as e:
        print(f"[email_sender] Failed after retries: {e}")

    return {"email_pending": False, "email_payload": None}
