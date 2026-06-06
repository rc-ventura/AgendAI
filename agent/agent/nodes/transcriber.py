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

    # Replace the UI's audio placeholder message instead of appending a new one.
    # add_messages updates in-place when the returned message shares the same id.
    last_human = next(
        (m for m in reversed(state.get("messages", [])) if getattr(m, "type", None) == "human"),
        None,
    )
    msg_id = last_human.id if last_human and last_human.id else None
    transcribed = HumanMessage(content=transcript.text, id=msg_id) if msg_id else HumanMessage(content=transcript.text)

    return {"messages": [transcribed], "audio_data": None}
