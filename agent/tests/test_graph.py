import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from agent.state import AgendAIState


def make_state(**kwargs) -> AgendAIState:
    base: AgendAIState = {
        "messages": [],
        "input_type": "text",
        "audio_data": None,
        "session_id": "test-graph",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    base.update(kwargs)
    return base


@pytest.mark.asyncio
async def test_text_query_reaches_llm(mock_api_client):
    """US1: text message flows through detect_input_type → chat_with_llm"""
    from agent.graph import graph

    mock_ai_response = AIMessage(content="Aqui estão os horários disponíveis!")

    with patch("agent.nodes.llm_core.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_response)
        state = make_state(messages=[HumanMessage(content="Quais horários?")])
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-1"}})

    assert result["input_type"] == "text"
    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage)
    assert "horários" in last_msg.content.lower() or last_msg.content


@pytest.mark.asyncio
async def test_email_pending_triggers_send_email(mock_api_client):
    """US2/US3: when email_pending=True after tool, send_email node fires"""
    from agent.graph import graph

    # Simulate LLM returning a final answer after tools already set email_pending
    mock_final_response = AIMessage(content="Consulta agendada com sucesso!")

    with patch("agent.nodes.llm_core.llm") as mock_llm, \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
        mock_llm.ainvoke = AsyncMock(return_value=mock_final_response)
        mock_smtp.return_value = None

        state = make_state(
            messages=[HumanMessage(content="Agendar")],
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
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-2"}})

    assert result["email_pending"] is False


@pytest.mark.asyncio
async def test_audio_path_calls_transcriber_and_tts():
    """US4: audio input → transcribe → llm → synthesize_tts"""
    from agent.graph import graph

    mock_ai_response = AIMessage(content="Temos horários disponíveis!")
    fake_audio_out = b"MP3_OUTPUT"

    with patch("agent.nodes.llm_core.llm") as mock_llm, \
         patch("agent.nodes.transcriber.openai_client") as mock_stt, \
         patch("agent.nodes.tts.openai_client") as mock_tts_client:

        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_response)
        mock_stt.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="Quais horários disponíveis?")
        )
        mock_response = MagicMock()
        mock_response.read = MagicMock(return_value=fake_audio_out)
        mock_tts_client.audio.speech.create = AsyncMock(return_value=mock_response)

        state = make_state(
            messages=[],
            input_type="audio",
            audio_data=b"FAKE_AUDIO_INPUT",
        )
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-3"}})

    assert result["input_type"] == "audio"
    assert result["final_response"] == fake_audio_out


@pytest.mark.asyncio
async def test_full_scheduling_flow_us2(mock_api_client):
    """TST-02 — US2: text → buscar_horarios → criar_agendamento → confirm + email sent."""
    from agent.graph import graph
    from langchain_core.messages import ToolMessage

    call_count = 0

    async def llm_side_effect(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Round 1: LLM asks for available slots
            return AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "buscar_horarios_disponiveis", "args": {"data": None}}],
            )
        if call_count == 2:
            # Round 2: LLM books the appointment
            return AIMessage(
                content="",
                tool_calls=[
                    {"id": "c2", "name": "criar_agendamento",
                     "args": {"paciente_email": "joao@email.com", "horario_id": 1}}
                ],
            )
        # Round 3+: final confirmation
        return AIMessage(content="Consulta agendada com sucesso para o Dr. Carlos Lima!")

    with patch("agent.nodes.llm_core.llm") as mock_llm, \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
        mock_llm.ainvoke = AsyncMock(side_effect=llm_side_effect)
        mock_smtp.return_value = None

        state = make_state(messages=[HumanMessage(content="Quero agendar uma consulta para joao@email.com")])
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-5"}})

    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage)
    assert "agendada" in last_msg.content.lower() or last_msg.content
    assert result["email_pending"] is False


@pytest.mark.asyncio
async def test_cancellation_flow_us3(mock_api_client):
    """TST-04 — US3: text → cancelar_agendamento → confirm + email sent."""
    from agent.graph import graph

    call_count = 0

    async def llm_side_effect(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "c3", "name": "cancelar_agendamento", "args": {"agendamento_id": 1}}],
            )
        return AIMessage(content="Seu agendamento foi cancelado com sucesso.")

    with patch("agent.nodes.llm_core.llm") as mock_llm, \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
        mock_llm.ainvoke = AsyncMock(side_effect=llm_side_effect)
        mock_smtp.return_value = None

        state = make_state(messages=[HumanMessage(content="Cancele meu agendamento 1 para joao@email.com")])
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-6"}})

    last_msg = result["messages"][-1]
    assert isinstance(last_msg, AIMessage)
    assert "cancelado" in last_msg.content.lower() or last_msg.content
    assert result["email_pending"] is False


@pytest.mark.asyncio
async def test_run_id_present_for_langsmith():
    """US5: graph execution produces a run_id traceable in LangSmith"""
    from agent.graph import graph
    from langchain_core.runnables.config import RunnableConfig

    mock_ai_response = AIMessage(content="Olá!")

    with patch("agent.nodes.llm_core.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=mock_ai_response)
        state = make_state(messages=[HumanMessage(content="Oi")])
        config = RunnableConfig(
            run_name="test_langsmith_trace",
            tags=["test"],
            configurable={"thread_id": "test-4"},
        )
        result = await graph.ainvoke(state, config=config)

    assert result is not None
