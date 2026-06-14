"""Audio pre/post-processing helpers for the audio path of the graph.

Keeps the audio-blob handling out of graph.py, which stays focused on wiring
the StateGraph and the graph-level node functions.
"""
import struct

from langchain_core.messages import HumanMessage

from agent.state import AgendAIState

# gpt-audio outputs raw PCM16 at these specs when stream=True.
# mp3/opus/flac are only available with stream=False, which LangChain does not use.
_WAV_SAMPLE_RATE = 24000
_WAV_CHANNELS = 1
_WAV_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes per sample


def pcm16_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM16 bytes in a RIFF/WAV container.

    The WAV format is a thin header around raw PCM data. The header tells the
    player how to interpret the bytes: sample rate (24 kHz), channels (mono),
    and bit depth (16-bit). Without it, browsers cannot play the audio.

    RIFF layout:
        "RIFF" + file_size (4B LE) + "WAVE"
        "fmt " + chunk_size=16 (4B) + PCM=1 (2B) + channels (2B)
                + sample_rate (4B) + byte_rate (4B) + block_align (2B) + bits (2B)
        "data" + data_size (4B) + <raw PCM bytes>
    """
    data_size = len(pcm_bytes)
    byte_rate = _WAV_SAMPLE_RATE * _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    block_align = _WAV_CHANNELS * _WAV_SAMPLE_WIDTH
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1,  # chunk_size=16, PCM=1
        _WAV_CHANNELS, _WAV_SAMPLE_RATE, byte_rate, block_align,
        _WAV_SAMPLE_WIDTH * 8,
        b"data", data_size,
    )
    return header + pcm_bytes


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
