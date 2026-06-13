"""Audio pre/post-processing helpers for the audio path of the graph.

Keeps the audio-blob handling out of graph.py, which stays focused on wiring
the StateGraph and the graph-level node functions.
"""
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState


def is_input_audio_message(msg) -> bool:
    """True if msg is a HumanMessage carrying an input_audio content part."""
    content = getattr(msg, "content", None)
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") == "input_audio" for p in content
    )


def strip_consumed_audio(state: AgendAIState) -> list:
    """Replace consumed input_audio HumanMessages with a lightweight text placeholder.

    The base64 audio blob (~64KB for a 1.5s clip) has already been consumed by the
    audio_agent by the time this runs. Leaving it in `messages` would persist it in
    every downstream checkpoint and replay it to the LLM on every subsequent turn
    (Constitution VII: transient data must not persist beyond the consuming node).

    add_messages updates in-place when a returned message shares the same id, so we
    re-emit each audio message as a text placeholder under its original id.

    KNOWN LIMITATION: the transcript (actual words) is NOT preserved — the model loses
    the content of past voice turns. Acceptable for short single-turn booking flows;
    multi-turn voice context degrades. The documented future fix is parallel Whisper
    transcription (see docs/learning-lessons/voice_agent_context_management.md L5/L6).
    """
    replacements = []
    for msg in state["messages"]:
        if is_input_audio_message(msg) and getattr(msg, "id", None):
            replacements.append(HumanMessage(id=msg.id, content="[mensagem de voz]"))
    return replacements
