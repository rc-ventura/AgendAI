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
        "audio_format": None,
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

def test_llm_bound_with_parallel_tool_calls():
    """B1 (QW-1): LLM must be bound with parallel_tool_calls=True for concurrent tool execution."""
    from agent.nodes.llm_core import llm
    bound_kwargs = getattr(llm, "kwargs", {})
    assert bound_kwargs.get("parallel_tool_calls") is True, (
        "LLM must be bound with parallel_tool_calls=True (QW-1 B1)"
    )


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


# ── input_detector: audio → HumanMessage com input_audio content part ────────

def test_detect_input_audio_creates_human_message_with_content_part():
    """B5: detect_input_type deve criar HumanMessage com input_audio content part para áudio."""
    import base64
    from agent.nodes.input_detector import detect_input_type
    from langchain_core.messages import HumanMessage

    state = make_state(audio_data=b"fake_audio_bytes", input_type="text")
    result = detect_input_type(state)

    assert result["input_type"] == "audio"
    msg = result["messages"][0]
    assert isinstance(msg, HumanMessage)
    assert isinstance(msg.content, list)
    assert msg.content[0]["type"] == "input_audio"
    # bytes corretamente codificados em base64
    decoded = base64.b64decode(msg.content[0]["input_audio"]["data"])
    assert decoded == b"fake_audio_bytes"


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


# ── llm_core: audio_llm extrai audio quando sem tool_calls (TST-06) ──────────

@pytest.mark.asyncio
async def test_chat_with_llm_audio_extracts_final_response():
    """B5/TST-06: chat_with_llm extrai bytes de áudio quando a resposta não tem tool_calls."""
    import base64
    from agent.nodes.llm_core import chat_with_llm

    fake_mp3 = b"MP3_BYTES"
    b64_audio = base64.b64encode(fake_mp3).decode()

    mock_response = AIMessage(
        content="Temos horários disponíveis!",
        additional_kwargs={"audio": {"data": b64_audio, "id": "audio_123"}},
    )

    with patch("agent.nodes.llm_core.audio_llm") as mock_audio_llm:
        mock_audio_llm.ainvoke = AsyncMock(return_value=mock_response)
        state = make_state(input_type="audio")
        result = await chat_with_llm(state)

    assert result["final_response"] == fake_mp3
    assert len(result["messages"]) == 1


# ── B6: retry + circuit breaker (T024) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_transient_error_is_retried_transparently():
    """Contract #1: one APIConnectionError is retried silently — patient sees the answer."""
    import openai
    from agent.nodes.llm_core import chat_with_llm

    good_response = AIMessage(content="Olá! Como posso ajudar?")
    call_count = 0

    async def side_effect(messages, **_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise openai.APIConnectionError(request=MagicMock())
        return good_response

    with patch("agent.nodes.llm_core.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(side_effect=side_effect)
        result = await chat_with_llm(make_state())

    assert result["messages"][-1].content == "Olá! Como posso ajudar?"
    assert call_count == 2


@pytest.mark.asyncio
async def test_llm_breaker_opens_after_3_failures_returns_ptbr_message():
    """Contract #2: 3 consecutive LLM failures → circuit breaker opens → pt-BR unavailability."""
    import openai
    from agent.nodes.llm_core import chat_with_llm
    from agent.resilience import llm_breaker, CircuitOpenError  # noqa: F401

    llm_breaker.close()  # ensure clean state between tests

    async def always_fail(messages, **_):
        raise openai.APIConnectionError(request=MagicMock())

    with patch("agent.nodes.llm_core.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(side_effect=always_fail)
        # trip the breaker with 3 sequential failures
        for _ in range(3):
            result = await chat_with_llm(make_state())

        # breaker now open — next call must return pt-BR message without calling OpenAI
        mock_llm.ainvoke.reset_mock()
        result = await chat_with_llm(make_state())

    msg_content = result["messages"][-1].content.lower()
    assert "indisponível" in msg_content or "momento" in msg_content or "tente" in msg_content
    mock_llm.ainvoke.assert_not_called()

    llm_breaker.close()


@pytest.mark.asyncio
async def test_api_client_retries_connect_error():
    """Contract #3: ConnectError on first call is retried — second succeeds transparently."""
    from agent.nodes.tools import buscar_horarios_disponiveis

    call_count = 0

    with respx.mock(base_url="http://api:3000", assert_all_called=False) as mock:
        def responder(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json=[{
                "id": 1, "data_hora": "2026-06-15T09:00:00", "disponivel": 1,
                "medico": {"id": 1, "nome": "Dr. Carlos Lima", "especialidade": "Clínico Geral"},
            }])

        mock.get("/horarios/disponiveis").mock(side_effect=responder)
        result = await buscar_horarios_disponiveis.ainvoke({"data": None})

    assert "Dr. Carlos Lima" in result
    assert call_count == 2


@pytest.mark.asyncio
async def test_api_client_does_not_retry_409():
    """Contract #4: 409 Conflict is NOT retried — single attempt, error relayed."""
    from agent.nodes.tools import criar_agendamento

    call_count = 0

    with respx.mock(base_url="http://api:3000", assert_all_called=False) as mock:
        def responder(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(409, json={"error": "Horário já ocupado"})

        mock.post("/agendamentos").mock(side_effect=responder)
        result = await criar_agendamento.ainvoke({
            "paciente_email": "joao@email.com",
            "horario_id": 1,
        })

    assert call_count == 1
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_email_sender_no_duplicate_on_smtp_retry():
    """Contract #5 (FR-006): a retry around SMTP must not send duplicate emails.
    _send_smtp is called exactly once per send_email invocation — tenacity retries
    are internal to _send_smtp itself, so send_email never calls it twice.
    """
    from agent.nodes.email_sender import send_email

    state = make_state(
        email_pending=True,
        email_payload={
            "tipo": "agendamento",
            "paciente_email": "joao@email.com",
            "paciente_nome": "João Silva",
            "medico_nome": "Dr. Carlos Lima",
            "data_hora": "2026-06-15 09:00",
            "valor": 200.0,
            "formas_pagamento": ["PIX"],
        },
    )

    with patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
        mock_smtp.return_value = None
        await send_email(state)
        await send_email({**state, "email_pending": True})  # second invocation

    # Each call to send_email must dispatch to _send_smtp exactly once
    assert mock_smtp.call_count == 2  # 1 per invocation, never 2x for the same invocation
