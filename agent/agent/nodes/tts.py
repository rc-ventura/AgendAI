from openai import AsyncOpenAI
from langchain_core.messages import AIMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.state import AgendAIState

openai_client = AsyncOpenAI()


def _last_ai_text(state: AgendAIState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return "Olá! Como posso ajudá-lo?"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _call_tts(text: str) -> bytes:
    response = await openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    return response.read()


async def synthesize_tts(state: AgendAIState) -> dict:
    text = _last_ai_text(state)
    audio_bytes = await _call_tts(text)
    return {"final_response": audio_bytes}
