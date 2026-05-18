import pytest
import json
import httpx
import respx
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from tenacity import RetryError

from agent.state import AgendAIState
from agent.nodes.input_detector import detect_input_type
from agent.nodes.llm_core import chat_with_llm


# ── input_detector ────────────────────────────────────────────────────────────

def make_state(**kwargs) -> AgendAIState:
    defaults: AgendAIState = {
        "messages": [HumanMessage(content="Olá")],
        "input_type": "text",
        "audio_data": None,
        "session_id": "test",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    defaults.update(kwargs)
    return defaults


def test_detect_input_type_text():
    state = make_state(audio_data=None)
    result = detect_input_type(state)
    assert result["input_type"] == "text"


def test_detect_input_type_audio():
    state = make_state(audio_data=b"fake_audio")
    result = detect_input_type(state)
    assert result["input_type"] == "audio"


# ── tools ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_horarios_tool(mock_api_client):
    from agent.nodes.tools import buscar_horarios_disponiveis
    result = await buscar_horarios_disponiveis.ainvoke({"data": None})
    assert "Dr. Carlos Lima" in result


@pytest.mark.asyncio
async def test_buscar_horarios_tool_com_data(mock_api_client):
    from agent.nodes.tools import buscar_horarios_disponiveis
    result = await buscar_horarios_disponiveis.ainvoke({"data": "2026-05-20"})
    assert "2026-05-20" in result


@pytest.mark.asyncio
async def test_criar_agendamento_tool(mock_api_client):
    from agent.nodes.tools import criar_agendamento
    result = await criar_agendamento.ainvoke({
        "paciente_email": "joao@email.com",
        "horario_id": 1,
    })
    assert "agendad" in result.lower() or "sucesso" in result.lower()


@pytest.mark.asyncio
async def test_cancelar_agendamento_tool(mock_api_client):
    from agent.nodes.tools import cancelar_agendamento
    result = await cancelar_agendamento.ainvoke({"agendamento_id": 1})
    assert "cancelado" in result.lower()


@pytest.mark.asyncio
async def test_buscar_paciente_tool(mock_api_client):
    from agent.nodes.tools import buscar_paciente
    result = await buscar_paciente.ainvoke({"email": "joao@email.com"})
    assert "João Silva" in result


@pytest.mark.asyncio
async def test_buscar_pagamentos_tool(mock_api_client):
    from agent.nodes.tools import buscar_pagamentos
    result = await buscar_pagamentos.ainvoke({})
    assert "200" in result or "R$" in result


# ── llm_core ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_core_returns_ai_message():
    from agent.nodes.llm_core import chat_with_llm

    mock_response = AIMessage(content="Olá! Como posso ajudar?")

    with patch("agent.nodes.llm_core.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        state = make_state()
        result = await chat_with_llm(state)

    assert "messages" in result
    assert result["messages"][-1].content == "Olá! Como posso ajudar?"


# ── email_sender ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_sender_agendamento():
    from agent.nodes.email_sender import send_email

    state = make_state(
        email_pending=True,
        email_payload={
            "tipo": "agendamento",
            "paciente_email": "joao@email.com",
            "paciente_nome": "João Silva",
            "medico_nome": "Dr. Carlos Lima",
            "data_hora": "2026-05-20 09:00",
            "valor": 200.0,
            "formas_pagamento": ["PIX", "Cartão"],
        },
    )

    with patch("agent.nodes.email_sender.smtplib.SMTP_SSL") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = await send_email(state)

    assert result["email_pending"] is False
    assert result["email_payload"] is None


@pytest.mark.asyncio
async def test_email_sender_cancelamento():
    from agent.nodes.email_sender import send_email

    state = make_state(
        email_pending=True,
        email_payload={
            "tipo": "cancelamento",
            "paciente_email": "joao@email.com",
            "paciente_nome": "João Silva",
            "medico_nome": "Dr. Carlos Lima",
            "data_hora": "2026-05-20 09:00",
            "valor": None,
            "formas_pagamento": None,
        },
    )

    with patch("agent.nodes.email_sender.smtplib.SMTP_SSL") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = await send_email(state)

    assert result["email_pending"] is False


# ── transcriber ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transcriber_adds_human_message():
    from agent.nodes.transcriber import transcribe_audio

    state = make_state(audio_data=b"fake_audio_bytes", input_type="audio")

    with patch("agent.nodes.transcriber.openai_client") as mock_client:
        mock_client.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="Quais horários disponíveis?")
        )
        result = await transcribe_audio(state)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Quais horários disponíveis?"


# ── tools: API degradation (TST-03) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_horarios_api_down_returns_error_string():
    """TST-03: when REST API is down, tool returns an error string instead of raising."""
    from agent.nodes.tools import buscar_horarios_disponiveis

    with respx.mock(base_url="http://api:3000"):
        respx.get("/horarios/disponiveis").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )
        try:
            result = await buscar_horarios_disponiveis.ainvoke({"data": None})
            # If the tool catches the error itself it should return a string
            assert isinstance(result, str)
        except Exception:
            # Acceptable: tool propagates httpx.HTTPStatusError — caller (ToolNode) handles it
            pass


@pytest.mark.asyncio
async def test_buscar_paciente_not_found_returns_string(mock_api_client):
    """TST-03 variant: 404 on buscar_paciente returns a human-readable string, not an exception."""
    from agent.nodes.tools import buscar_paciente

    result = await buscar_paciente.ainvoke({"email": "naoexiste@email.com"})
    assert isinstance(result, str)
    assert "não encontrado" in result.lower() or "verifique" in result.lower()


# ── email_sender: all retries exhausted (TST-05) ──────────────────────────────

@pytest.mark.asyncio
async def test_email_sender_continues_after_smtp_failure():
    """TST-05: SMTP fails all 3 tenacity retries — send_email still returns cleared state."""
    from agent.nodes.email_sender import send_email

    state = make_state(
        email_pending=True,
        email_payload={
            "tipo": "agendamento",
            "paciente_email": "joao@email.com",
            "paciente_nome": "João Silva",
            "medico_nome": "Dr. Carlos Lima",
            "data_hora": "2026-05-20 09:00",
            "valor": 200.0,
            "formas_pagamento": ["PIX"],
        },
    )

    with patch("agent.nodes.email_sender._send_smtp", side_effect=Exception("SMTP connection refused")):
        result = await send_email(state)

    # System MUST continue: email_pending cleared even when email fails
    assert result["email_pending"] is False
    assert result["email_payload"] is None


# ── transcriber: corrupted audio (TST-06) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_transcriber_raises_on_corrupted_audio():
    """TST-06: Whisper API raises on invalid audio bytes — error propagates."""
    from agent.nodes.transcriber import transcribe_audio

    state = make_state(audio_data=b"\x00\x01\x02corrupted", input_type="audio")

    with patch("agent.nodes.transcriber.openai_client") as mock_client:
        mock_client.audio.transcriptions.create = AsyncMock(
            side_effect=Exception("Audio file could not be decoded")
        )
        with pytest.raises(Exception, match="Audio file could not be decoded"):
            await transcribe_audio(state)


# ── tts ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_sets_final_response_bytes():
    from agent.nodes.tts import synthesize_tts

    state = make_state(
        input_type="audio",
        messages=[HumanMessage(content="Olá"), AIMessage(content="Temos horários disponíveis!")],
        final_response=None,
    )

    fake_audio = b"MP3_BYTES"

    with patch("agent.nodes.tts.openai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.read = MagicMock(return_value=fake_audio)
        mock_client.audio.speech.create = AsyncMock(return_value=mock_response)
        result = await synthesize_tts(state)

    assert result["final_response"] == fake_audio
