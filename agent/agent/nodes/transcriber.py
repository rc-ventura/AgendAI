import io
import base64
from openai import AsyncOpenAI
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState

# B5 (ADR-028): gpt-4o-audio-preview via Chat Completions REST — mesma OPENAI_API_KEY,
# sem nova infra. Groq whisper-large-v3-turbo documentado como alternativa de latência
# mais baixa caso GROQ_API_KEY seja adicionada futuramente.
openai_client = AsyncOpenAI()


async def transcribe_audio(state: AgendAIState) -> dict:
    raw = state["audio_data"]
    audio_bytes = bytes(raw) if isinstance(raw, list) else raw

    response = await openai_client.chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[{
            "role": "user",
            "content": [{
                "type": "input_audio",
                "input_audio": {
                    "data": base64.b64encode(audio_bytes).decode(),
                    "format": "mp3",
                },
            }],
        }],
    )
    text = response.choices[0].message.content
    return {"messages": [HumanMessage(content=text)]}
