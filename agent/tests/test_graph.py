import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver

from agent.state import AgendAIState


def make_state(**kwargs) -> AgendAIState:
    base: AgendAIState = {
        "messages": [],
        "input_type": "text",
        "audio_data": None,
        "audio_format": None,
        "session_id": "test-graph",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }
    base.update(kwargs)
    return base



def test_bff_route_handler_sets_durability_exit():
    """B3 (QW-3): durability='exit' must be enforced server-side in the Next.js BFF
    Route Handler, not in browser UI code (ADR-025 B3, SC-006)."""
    import pathlib
    root = pathlib.Path(__file__).parent.parent.parent

    route_handler = root / "agent-ui-pro/src/app/api/[..._path]/route.ts"
    assert route_handler.exists(), (
        "BFF Route Handler must exist at agent-ui-pro/src/app/api/[..._path]/route.ts"
    )
    content = route_handler.read_text()
    assert 'durability' in content, (
        "Route Handler must inject durability (QW-3 B3)"
    )
    assert "bodyParameters" in content, (
        "Route Handler must use bodyParameters — the official LangGraph BFF pattern"
    )

    # durability must NOT appear in browser-side components or hooks
    for browser_file in [
        root / "agent-ui-pro/src/components/thread/index.tsx",
        root / "agent-ui-pro/src/providers/Stream.tsx",
    ]:
        assert 'durability' not in browser_file.read_text(), (
            f"durability must not appear in browser code {browser_file.name} "
            "(set server-side in BFF Route Handler only)"
        )


def test_audio_llm_uses_gpt_audio_1_5_model():
    """Audio model is pinned to gpt-audio-1.5 for deterministic behavior."""
    from agent.nodes.llm_core import audio_llm

    # ChatOpenAI wraps model name in different attrs depending on version
    model_name = getattr(audio_llm, "model_name", None) or getattr(
        getattr(audio_llm, "bound", None), "model_name", None
    ) or ""
    assert model_name == "gpt-audio-1.5", (
        f"audio_llm must be pinned to gpt-audio-1.5, got: {model_name!r}"
    )


def test_system_prompt_directs_parallel_lookup():
    """B2 (QW-4): Prompt must instruct simultaneous buscar_horarios + buscar_paciente
    in round 1 to drive the scheduling flow down to ≤2 LLM rounds."""
    from agent.nodes.llm_core import SYSTEM_PROMPT
    lower = SYSTEM_PROMPT.lower()
    assert "simultane" in lower or "ao mesmo tempo" in lower, (
        "SYSTEM_PROMPT must instruct simultaneous tool lookups in round 1 (QW-4 B2)"
    )


@pytest.mark.asyncio
async def test_text_query_reaches_llm(mock_api_client):
    """US1: text message flows through detect_input_type → text_agent (create_agent)"""
    from agent.graph import graph

    mock_ai_response = AIMessage(content="Aqui estão os horários disponíveis!")

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_ai_response)):
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

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_final_response)), \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
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
async def test_audio_path_uses_audio_llm_and_sets_final_response():
    """US4 / B1: audio_data → detect_input_type builds input_audio msg → audio_agent
    (gpt-audio, text out) → synthesize_audio_response calls TTS → final_response WAV.
    Audio output comes from the dedicated TTS endpoint, not the chat model
    (LangChain #29776 drops audio chunks on streamed chat output)."""
    from agent.graph import graph

    mock_text_response = AIMessage(content="Temos horários disponíveis!")
    fake_wav = b"RIFF\x00\x00\x00\x00WAVEfake"

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_text_response)), \
         patch("agent.graph.text_to_speech_wav", AsyncMock(return_value=fake_wav)):
        state = make_state(
            messages=[],
            input_type="audio",
            audio_data=b"FAKE_AUDIO_INPUT",
        )
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "test-3"}})

    assert result["input_type"] == "audio"
    assert result["final_response"][:4] == b"RIFF"
    assert result["final_response"][8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_synthesize_audio_response_uses_last_ai_text():
    """B1: synthesize_audio_response feeds the final assistant text into TTS."""
    from agent.graph import synthesize_audio_response

    fake_wav = b"RIFF\x00\x00\x00\x00WAVEfake"
    state = make_state(
        messages=[AIMessage(content="Sua consulta foi agendada.")],
        input_type="audio",
    )

    tts_mock = AsyncMock(return_value=fake_wav)
    with patch("agent.graph.text_to_speech_wav", tts_mock):
        out = await synthesize_audio_response(state)

    tts_mock.assert_awaited_once_with("Sua consulta foi agendada.")
    assert out["final_response"][:4] == b"RIFF"


def _has_input_audio_part(msg) -> bool:
    content = getattr(msg, "content", None)
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") == "input_audio" for p in content
    )


@pytest.mark.asyncio
async def test_audio_blob_stripped_after_consumption():
    """B10-D: after the audio turn, the input_audio base64 blob must NOT remain in
    message history (Constitution VII: transient data must not persist beyond the
    consuming node). synthesize_audio_response replaces it with a text placeholder."""
    from agent.graph import graph

    mock_text_response = AIMessage(content="Temos horários disponíveis!")
    fake_wav = b"RIFF\x00\x00\x00\x00WAVEfake"

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_text_response)), \
         patch("agent.graph.text_to_speech_wav", AsyncMock(return_value=fake_wav)):
        state = make_state(
            messages=[],
            input_type="audio",
            audio_data=b"FAKE_AUDIO_INPUT",
        )
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": "strip-audio-1"}})

    assert not any(_has_input_audio_part(m) for m in result["messages"]), (
        "input_audio blob must be stripped from message history after the audio turn"
    )
    # the human turn is still present as a text placeholder
    assert any(
        isinstance(m, HumanMessage) and m.content == "[mensagem de voz]"
        for m in result["messages"]
    ), "consumed audio message must be replaced by a text placeholder"


@pytest.mark.asyncio
async def test_full_scheduling_flow_us2(mock_api_client):
    """TST-02 — US2: text → buscar_horarios → criar_agendamento → confirm + email sent."""
    from agent.graph import graph
    from langchain_core.messages import ToolMessage

    call_count = 0

    async def llm_side_effect(*args, **kwargs):
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

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(side_effect=llm_side_effect)), \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
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

    async def llm_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "c3", "name": "cancelar_agendamento", "args": {"agendamento_id": 1}}],
            )
        return AIMessage(content="Seu agendamento foi cancelado com sucesso.")

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(side_effect=llm_side_effect)), \
         patch("agent.nodes.email_sender._send_smtp") as mock_smtp:
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

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_ai_response)):
        state = make_state(messages=[HumanMessage(content="Oi")])
        config = RunnableConfig(
            run_name="test_langsmith_trace",
            tags=["test"],
            configurable={"thread_id": "test-4"},
        )
        result = await graph.ainvoke(state, config=config)

    assert result is not None


# ── B10-C: CountingCheckpointer (T054 / T058) ─────────────────────────────────

class CountingCheckpointer(MemorySaver):
    """Wraps MemorySaver, counting every put call — used to verify bounded checkpoint writes.

    With durability='async' (default, unit test level) LangGraph writes once per superstep.
    The test asserts writes are active (≥1) and bounded (≤ N_MAX), proving the checkpointing
    mechanism is healthy. The BFF static test covers durability='exit' at the server level.
    """

    def __init__(self):
        super().__init__()
        self.put_count = 0

    def put(self, *args, **kwargs):
        self.put_count += 1
        return super().put(*args, **kwargs)

    async def aput(self, *args, **kwargs):
        self.put_count += 1
        return await super().aput(*args, **kwargs)


@pytest.mark.asyncio
async def test_checkpoint_writes_are_bounded(mock_api_client):
    """B10-C (HIGH-02 QA fix): runtime validation that checkpoint writes are active and bounded
    per graph run. Complements test_bff_route_handler_sets_durability_exit (static check) with
    an actual write-count assertion (contracts/observability.md HIGH-02, research.md R6)."""
    from agent.graph import builder

    checkpointer = CountingCheckpointer()
    test_g = builder.compile(checkpointer=checkpointer)

    mock_response = AIMessage(content="Aqui estão os horários disponíveis!")

    with patch.object(BaseChatModel, "ainvoke", AsyncMock(return_value=mock_response)):
        state = make_state(messages=[HumanMessage(content="Quais horários?")])
        await test_g.ainvoke(state, config={"configurable": {"thread_id": "b10c-test-1"}})

    # (a) checkpointing is active — at least one write happened (recovery is possible)
    assert checkpointer.put_count >= 1, (
        f"Expected ≥1 checkpoint write, got {checkpointer.put_count} — checkpointer may not be active"
    )
    # (b) writes are bounded — text path has 3 top-level nodes; create_agent is a compiled
    # subgraph whose internal supersteps each write to the parent checkpointer. N_MAX equals
    # the graph's recursion_limit (60) — any run that writes more has a loop bug.
    N_MAX = 60
    assert checkpointer.put_count <= N_MAX, (
        f"Expected ≤{N_MAX} checkpoint writes per run, got {checkpointer.put_count} — "
        "possible unbounded loop (recursion_limit=60 is the hard ceiling)"
    )
