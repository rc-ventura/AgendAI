import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.state import AgendAIState


def _build_message(payload: dict) -> tuple[str, str]:
    """Returns (subject, body) for the email."""
    if payload["tipo"] == "agendamento":
        subject = f"AgendAI — Confirmação de consulta em {payload['data_hora']}"
        formas = ", ".join(payload.get("formas_pagamento") or [])
        valor = payload.get("valor")
        body = (
            f"Olá, {payload['paciente_nome']}!\n\n"
            f"Sua consulta foi agendada com sucesso.\n\n"
            f"Médico: {payload['medico_nome']}\n"
            f"Data/Hora: {payload['data_hora']}\n"
            + (f"Valor: R$ {valor:.2f}\n" if valor else "")
            + (f"Formas de pagamento: {formas}\n" if formas else "")
            + "\nAté logo!\nEquipe AgendAI"
        )
    else:
        subject = f"AgendAI — Consulta cancelada em {payload['data_hora']}"
        body = (
            f"Olá, {payload['paciente_nome']}!\n\n"
            f"Sua consulta com {payload['medico_nome']} "
            f"em {payload['data_hora']} foi cancelada com sucesso.\n\n"
            "Se precisar reagendar, estamos à disposição.\n\nEquipe AgendAI"
        )
    return subject, body


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _send_smtp(subject: str, body: str, to_email: str) -> None:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_user or not gmail_password:
        # In dev/test without credentials, log and skip
        print(f"[email_sender] Skipping email (no credentials): {subject} → {to_email}")
        return

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.send_message(msg)


async def send_email(state: AgendAIState) -> dict:
    payload = state.get("email_payload")
    if not payload:
        return {"email_pending": False, "email_payload": None}

    subject, body = _build_message(payload)
    try:
        _send_smtp(subject, body, payload["paciente_email"])
    except Exception as e:
        print(f"[email_sender] Failed after retries: {e}")

    return {"email_pending": False, "email_payload": None}
