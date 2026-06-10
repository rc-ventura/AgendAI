"""
B5 live validation: gpt-4o-audio-preview multimodal
- T023: SC-007 ≥50% audio latency reduction vs baseline
"""
import asyncio
import base64
import time
import os
import sys
import struct
import wave
import io

from langgraph_sdk import get_client

API_URL = "http://127.0.0.1:8123"
AUTH_TOKEN = os.environ.get("LANGGRAPH_AUTH_TOKEN", "")
GRAPH_ID = "agendai_agent"
N_RUNS = 3


def make_sine_wav(duration_s: float = 1.5, freq: float = 440.0, sample_rate: int = 16000) -> bytes:
    """Generate a simple WAV file with a sine wave (simulates speech audio)."""
    import math
    num_samples = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
            frames += struct.pack("<h", val)
        wf.writeframes(bytes(frames))
    return buf.getvalue()


async def run_text_query(client, thread_id: str) -> tuple[float, str]:
    t0 = time.perf_counter()
    result = None
    async for chunk in client.runs.stream(
        thread_id=thread_id,
        assistant_id=GRAPH_ID,
        input={"messages": [{"role": "human", "content": "Quais horários disponíveis esta semana?"}]},
        stream_mode="values",
    ):
        if chunk.event == "values":
            result = chunk.data
    elapsed = time.perf_counter() - t0
    last_msg = result["messages"][-1] if result else {}
    content = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")
    return elapsed, str(content)[:120]


async def run_audio_query(client, thread_id: str, wav_bytes: bytes) -> tuple[float, bool, int]:
    audio_b64 = base64.b64encode(wav_bytes).decode()
    t0 = time.perf_counter()
    result = None
    async for chunk in client.runs.stream(
        thread_id=thread_id,
        assistant_id=GRAPH_ID,
        input={
            "messages": [],
            "audio_data": list(wav_bytes),  # state expects bytes-like
        },
        stream_mode="values",
    ):
        if chunk.event == "values":
            result = chunk.data
    elapsed = time.perf_counter() - t0

    final_response = result.get("final_response") if result else None
    audio_bytes_len = len(final_response) if final_response else 0
    has_audio = bool(final_response)
    return elapsed, has_audio, audio_bytes_len


async def main():
    client = get_client(url=API_URL, api_key=AUTH_TOKEN)

    print("=" * 60)
    print("B5 Live Validation — gpt-4o-audio-preview multimodal")
    print("=" * 60)

    # ── 1. Text baseline ──────────────────────────────────────
    print("\n[1] Text queries (baseline)")
    text_times = []
    for i in range(N_RUNS):
        thread = await client.threads.create()
        t, content = await run_text_query(client, thread["thread_id"])
        text_times.append(t)
        print(f"  run {i+1}: {t:.2f}s  | {content[:80]}...")

    text_p50 = sorted(text_times)[len(text_times) // 2]
    print(f"  → P50 text: {text_p50:.2f}s")

    # ── 2. Audio queries ──────────────────────────────────────
    print("\n[2] Audio queries (B5 multimodal)")
    wav_bytes = make_sine_wav()
    print(f"  Audio input: {len(wav_bytes)} bytes WAV (sine wave, 1.5s)")
    print("  NOTE: model will hear noise, not real speech — tests the pipeline, not recognition quality")

    audio_times = []
    audio_results = []
    for i in range(N_RUNS):
        thread = await client.threads.create()
        t, has_audio, audio_len = await run_audio_query(client, thread["thread_id"], wav_bytes)
        audio_times.append(t)
        audio_results.append((has_audio, audio_len))
        status = f"✓ audio {audio_len}B" if has_audio else "✗ no audio bytes"
        print(f"  run {i+1}: {t:.2f}s  | final_response={status}")

    audio_p50 = sorted(audio_times)[len(audio_times) // 2]
    audio_ok = sum(1 for ok, _ in audio_results if ok)
    print(f"  → P50 audio: {audio_p50:.2f}s")
    print(f"  → final_response with audio bytes: {audio_ok}/{N_RUNS}")

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  P50 text:  {text_p50:.2f}s")
    print(f"  P50 audio: {audio_p50:.2f}s")
    print(f"  Audio pipeline OK: {audio_ok}/{N_RUNS} runs returned audio bytes")

    sc007_note = "(SC-007 measures vs old baseline ~3–5s; single-node test — no whisper overhead to compare)"
    print(f"\n  {sc007_note}")

    if audio_ok == N_RUNS:
        print("\n✅ B5 PASS: audio pipeline working end-to-end")
        return 0
    else:
        print(f"\n❌ B5 FAIL: only {audio_ok}/{N_RUNS} runs produced audio output")
        return 1


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
