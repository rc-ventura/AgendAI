import io
from openai import AsyncOpenAI
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState

openai_client = AsyncOpenAI()


async def transcribe_audio(state: AgendAIState) -> dict:
    raw = state["audio_data"]
    audio_bytes = bytes(raw) if isinstance(raw, list) else raw
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.mp3"

    transcript = await openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return {"messages": [HumanMessage(content=transcript.text)]}
