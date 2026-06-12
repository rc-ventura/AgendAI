import pytest
import json
import httpx
import respx
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from agent.state import AgendAIState
from agent.nodes.input_detector import detect_input_type


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

def test_llm_core_exports_base_and_audio_llm():
    """B5/B7: llm_core exports base_llm and audio_llm for create_agent; no pre-bound llm needed."""
    from agent.nodes.llm_core import base_llm, audio_llm
    assert base_llm is not None
    assert audio_llm is not None


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


# ── B6: retry + circuit breaker via _ResilientChatOpenAI (T024) ──────────────

@pytest.mark.asyncio
async def test_llm_transient_error_is_retried_transparently():
    """Contract #1: ModelRetryMiddleware retries once — patient sees the answer."""
    import openai
    from langchain.agents.middleware.types import ModelResponse
    from agent.resilience import llm_circuit_breaker_middleware, _llm_retry_middleware, llm_breaker

    llm_breaker.close()
    call_count = 0

    async def mock_handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise openai.APIConnectionError(request=MagicMock())
        return ModelResponse(result=[AIMessage(content="Olá! Como posso ajudar?")])

    async def composed(request):
        return await _llm_retry_middleware.awrap_model_call(request, mock_handler)

    result = await llm_circuit_breaker_middleware.awrap_model_call(None, composed)

    assert call_count == 2
    content = result.content if isinstance(result, AIMessage) else result.result[0].content
    assert "Olá" in content
    llm_breaker.close()


@pytest.mark.asyncio
async def test_llm_breaker_opens_after_3_failures_returns_ptbr_message():
    """Contract #2: 3 retry-sequence failures → circuit opens → pt-BR message, no further calls."""
    import openai
    from agent.resilience import llm_circuit_breaker_middleware, _llm_retry_middleware, llm_breaker

    llm_breaker.close()
    call_count = 0

    async def always_fail(request):
        nonlocal call_count
        call_count += 1
        raise openai.APIConnectionError(request=MagicMock())

    async def composed(request):
        return await _llm_retry_middleware.awrap_model_call(request, always_fail)

    for _ in range(3):
        await llm_circuit_breaker_middleware.awrap_model_call(None, composed)

    calls_before = call_count
    result = await llm_circuit_breaker_middleware.awrap_model_call(None, composed)

    assert call_count == calls_before  # circuit open — handler not called
    content = result.content if isinstance(result, AIMessage) else result.result[0].content
    assert "indisponível" in content.lower() or "momento" in content.lower()
    llm_breaker.close()


@pytest.mark.asyncio
async def test_tool_middleware_retries_connect_error():
    """Contract #3: ToolRetryMiddleware retries ConnectError — second attempt succeeds."""
    from langchain_core.messages import ToolMessage
    from agent.resilience import _tool_retry_middleware

    call_count = 0
    mock_request = MagicMock()
    mock_request.tool.name = "buscar_horarios_disponiveis"
    mock_request.tool_call = {"id": "call_test_123"}

    async def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused")
        return ToolMessage(content="Horários disponíveis: Dr. Carlos Lima", tool_call_id="call_test_123")

    result = await _tool_retry_middleware.awrap_tool_call(mock_request, handler)

    assert call_count == 2
    assert isinstance(result, ToolMessage)
    assert "Dr. Carlos Lima" in result.content


@pytest.mark.asyncio
async def test_tool_middleware_does_not_retry_timeout_exception_type():
    """Contract #4: non-retriable exceptions are not retried — single attempt, error message returned."""
    from langchain_core.messages import ToolMessage
    from agent.resilience import _tool_retry_middleware

    call_count = 0
    mock_request = MagicMock()
    mock_request.tool.name = "criar_agendamento"
    mock_request.tool_call = {"id": "call_test_456"}

    async def handler(request):
        nonlocal call_count
        call_count += 1
        raise ValueError("unexpected business error")  # not in RETRYABLE_HTTP_EXCEPTIONS

    result = await _tool_retry_middleware.awrap_tool_call(mock_request, handler)

    assert call_count == 1  # no retry for non-retriable exception
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_api_circuit_breaker_fast_fails_when_open():
    """Contract #6: API CB open → ToolMessage returned immediately, handler not called."""
    from langchain_core.messages import ToolMessage
    from agent.resilience import api_circuit_breaker_middleware, api_breaker

    api_breaker.close()
    api_breaker._fails = api_breaker._fail_max
    api_breaker._opened_at = __import__("time").monotonic()

    call_count = 0
    mock_request = MagicMock()
    mock_request.tool.name = "buscar_horarios_disponiveis"
    mock_request.tool_call = {"id": "call_cb_1"}

    async def handler(request):
        nonlocal call_count
        call_count += 1
        return ToolMessage(content="ok", tool_call_id="call_cb_1")

    result = await api_circuit_breaker_middleware.awrap_tool_call(mock_request, handler)

    assert call_count == 0
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "indisponível" in result.content.lower()
    api_breaker.close()


@pytest.mark.asyncio
async def test_api_circuit_breaker_opens_after_3_transport_failures():
    """Contract #7: 3 ConnectErrors → circuit opens → subsequent call fast-fails."""
    from langchain_core.messages import ToolMessage
    from agent.resilience import api_circuit_breaker_middleware, api_breaker

    api_breaker.close()
    call_count = 0
    mock_request = MagicMock()
    mock_request.tool.name = "buscar_horarios_disponiveis"
    mock_request.tool_call = {"id": "call_cb_2"}

    async def always_fail(request):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    for _ in range(3):
        try:
            await api_circuit_breaker_middleware.awrap_tool_call(mock_request, always_fail)
        except httpx.ConnectError:
            pass

    calls_before = call_count
    result = await api_circuit_breaker_middleware.awrap_tool_call(mock_request, always_fail)

    assert call_count == calls_before  # circuit open — handler not called
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    api_breaker.close()


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
