import io
from groq import AsyncGroq
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState

# B5 (ADR-028): Groq Whisper drop-in — ~0.2–0.4s vs ~1.5–2.0s do OpenAI whisper-1.
# Para reverter ao OpenAI: trocar AsyncGroq() por AsyncOpenAI() e o model abaixo.
groq_client = AsyncGroq()


async def transcribe_audio(state: AgendAIState) -> dict:
    raw = state["audio_data"]
    audio_bytes = bytes(raw) if isinstance(raw, list) else raw
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.mp3"

    transcript = await groq_client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=audio_file,
    )
    return {"messages": [HumanMessage(content=transcript.text)]}
