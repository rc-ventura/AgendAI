"""B8 (ADR-030): Context manager contract tests — T038 (failing-first → now green).

Five observable outcomes from the context sustainability contract:
  1. SummarizationMiddleware wired in LLM_MIDDLEWARE after all PIIMiddleware
  2. trigger is configured (summarization will fire, not silently skip)
  3. before_model returns RemoveMessage + summary when threshold exceeded
  4. Recent messages are preserved after summarization (keep= policy)
  5. context_summary field in AgendAIState (state schema additive contract)
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage


def _make_long_history(n_turns: int):
    msgs = []
    for i in range(n_turns):
        msgs.append(HumanMessage(content=f"Sobre a consulta {i}", id=f"h{i}"))
        msgs.append(AIMessage(content=f"Detalhes da consulta {i}.", id=f"a{i}"))
    return msgs


# ── 1. Middleware wiring ──────────────────────────────────────────────────────

def test_summarization_middleware_in_llm_middleware():
    from langchain.agents.middleware import SummarizationMiddleware
    from agent.middleware import LLM_MIDDLEWARE

    instances = [m for m in LLM_MIDDLEWARE if isinstance(m, SummarizationMiddleware)]
    assert len(instances) == 1, "Exactly one SummarizationMiddleware must be in LLM_MIDDLEWARE"


def test_summarization_after_pii_in_middleware_stack():
    from langchain.agents.middleware import SummarizationMiddleware, PIIMiddleware
    from agent.middleware import LLM_MIDDLEWARE

    sum_idx = next(
        (i for i, m in enumerate(LLM_MIDDLEWARE) if isinstance(m, SummarizationMiddleware)), None
    )
    pii_indices = [i for i, m in enumerate(LLM_MIDDLEWARE) if isinstance(m, PIIMiddleware)]

    assert sum_idx is not None
    assert all(idx < sum_idx for idx in pii_indices), (
        "SummarizationMiddleware must come after all PIIMiddleware (PII redacted before summary)"
    )


def test_summarization_trigger_is_configured():
    from langchain.agents.middleware import SummarizationMiddleware
    from agent.middleware import LLM_MIDDLEWARE

    mw = next(m for m in LLM_MIDDLEWARE if isinstance(m, SummarizationMiddleware))
    assert mw.trigger is not None, "trigger must not be None — otherwise summarization never fires"
    # OR logic: both messages AND tokens conditions must be present
    conditions = mw._trigger_conditions
    kinds = {k for k, _ in conditions}
    assert "messages" in kinds, "trigger must include a messages condition"
    assert "tokens" in kinds, "trigger must include a tokens condition (for audio-heavy sessions)"


# ── 2. State schema ───────────────────────────────────────────────────────────

def test_context_summary_field_in_agent_state():
    from agent.state import AgendAIState

    hints = {}
    for klass in reversed(AgendAIState.__mro__):
        hints.update(getattr(klass, "__annotations__", {}))
    assert "context_summary" in hints, (
        "context_summary: str | None must be in AgendAIState (agent-state contract, B8)"
    )


# ── 3. Summarization behavior (unit) ─────────────────────────────────────────

def test_summarization_fires_when_threshold_exceeded():
    from langchain.agents.middleware import SummarizationMiddleware

    mw = SummarizationMiddleware(
        "openai:gpt-4o-mini",
        trigger=("messages", 4),
        keep=("messages", 2),
    )
    state = {"messages": _make_long_history(5)}  # 10 msgs > threshold 4

    with patch.object(mw, "_create_summary", return_value="Resumo: consultas 0-4 discutidas."):
        result = mw.before_model(state, MagicMock())

    assert result is not None, "before_model must return update when threshold exceeded"
    assert any(isinstance(m, RemoveMessage) for m in result["messages"]), (
        "RemoveMessage must be present to clear old history"
    )


def test_summarization_does_not_fire_below_threshold():
    from langchain.agents.middleware import SummarizationMiddleware

    mw = SummarizationMiddleware(
        "openai:gpt-4o-mini",
        trigger=("messages", 50),
        keep=("messages", 20),
    )
    state = {"messages": _make_long_history(3)}  # 6 msgs < threshold 50

    result = mw.before_model(state, MagicMock())
    assert result is None, "before_model must return None when threshold not reached"


def test_summary_message_added_with_lc_source():
    from langchain.agents.middleware import SummarizationMiddleware

    mw = SummarizationMiddleware(
        "openai:gpt-4o-mini",
        trigger=("messages", 4),
        keep=("messages", 2),
    )
    summary_text = "Paciente discutiu consultas 0-4. Nenhum agendamento confirmado."
    with patch.object(mw, "_create_summary", return_value=summary_text):
        result = mw.before_model({"messages": _make_long_history(5)}, MagicMock())

    assert result is not None
    summary_msgs = [
        m for m in result["messages"]
        if isinstance(m, HumanMessage)
        and m.additional_kwargs.get("lc_source") == "summarization"
    ]
    assert len(summary_msgs) == 1, "Exactly one summary HumanMessage must be present"
    assert summary_text in summary_msgs[0].content


def test_recent_messages_preserved_after_summarization():
    from langchain.agents.middleware import SummarizationMiddleware

    keep_n = 4
    mw = SummarizationMiddleware(
        "openai:gpt-4o-mini",
        trigger=("messages", 6),
        keep=("messages", keep_n),
    )
    state = {"messages": _make_long_history(6)}  # 12 msgs > threshold 6

    with patch.object(mw, "_create_summary", return_value="Resumo anterior"):
        result = mw.before_model(state, MagicMock())

    assert result is not None
    kept = [
        m for m in result["messages"]
        if not isinstance(m, RemoveMessage)
        and not (isinstance(m, HumanMessage) and m.additional_kwargs.get("lc_source") == "summarization")
    ]
    assert len(kept) == keep_n, f"Expected {keep_n} preserved messages, got {len(kept)}"
