"""TTS node — synthesize the assistant's final text to speech (WAV bytes).

Uses the dedicated /audio/speech endpoint (non-streaming), which returns a complete
WAV container the browser plays directly (audio/wav) — no PCM16 wrapping, and not
exposed to the chat-model streaming bug that drops audio output (LangChain #29776).
"""
from langchain_core.messages import AIMessage
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.state import AgendAIState

_TTS_MODEL = "gpt-4o-mini-tts"
_TTS_VOICE = "alloy"
_openai_client = AsyncOpenAI()


def _last_ai_text(state: AgendAIState) -> str:
    """Return the final assistant reply text (str content or text parts)."""
    for msg in reversed(state["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            joined = " ".join(p for p in parts if p).strip()
            if joined:
                return joined
    return "Olá! Como posso ajudá-lo?"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _call_tts(text: str) -> bytes:
    response = await _openai_client.audio.speech.create(
        model=_TTS_MODEL,
        voice=_TTS_VOICE,
        input=text,
        response_format="wav",
    )
    return response.read()


async def synthesize_tts(state: AgendAIState) -> dict:
    text = _last_ai_text(state)
    audio_bytes = await _call_tts(text)
    return {"final_response": audio_bytes}
