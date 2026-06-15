"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

export const AUDIO_MAX_BYTES = 25 * 1024 * 1024; // 25 MB
export const AUDIO_ACCEPT = "audio/mp3,audio/mpeg,audio/wav,audio/webm,audio/*";

interface UseAudioOptions {
  onAudio: (blob: Blob) => void;
  disabled?: boolean;
}

async function convertWebmBlobToWav(blob: Blob): Promise<Blob> {
  const AudioCtx =
    window.AudioContext ||
    (
      window as Window &
        typeof globalThis & { webkitAudioContext?: typeof AudioContext }
    ).webkitAudioContext;
  if (!AudioCtx) {
    throw new Error("AudioContext indisponivel para conversao de audio.");
  }

  const audioContext = new AudioCtx();
  try {
    const sourceBuffer = await blob.arrayBuffer();
    const decoded = await audioContext.decodeAudioData(sourceBuffer.slice(0));

    const channels = decoded.numberOfChannels;
    const sampleRate = decoded.sampleRate;
    const frameCount = decoded.length;

    const bytesPerSample = 2;
    const blockAlign = channels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = frameCount * blockAlign;
    const out = new ArrayBuffer(44 + dataSize);
    const view = new DataView(out);

    const writeString = (offset: number, text: string) => {
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
    };

    writeString(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, channels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, dataSize, true);

    const channelData = Array.from({ length: channels }, (_, i) => decoded.getChannelData(i));
    let offset = 44;
    for (let i = 0; i < frameCount; i++) {
      for (let c = 0; c < channels; c++) {
        const sample = Math.max(-1, Math.min(1, channelData[c][i] ?? 0));
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      }
    }

    return new Blob([out], { type: "audio/wav" });
  } finally {
    await audioContext.close();
  }
}

export function useAudio({ onAudio, disabled }: UseAudioOptions) {
  const [recording, setRecording] = useState(false);
  const [micDenied, setMicDenied] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  // Keep the latest onAudio in a ref so async callbacks (recorder.onstop fires
  // long after toggleRecord ran) always call the current callback, not a
  // stale closure from when recording started.
  const onAudioRef = useRef(onAudio);
  useEffect(() => {
    onAudioRef.current = onAudio;
  }, [onAudio]);

  async function toggleRecord() {
    if (disabled || micDenied) return;
    if (recording) {
      mediaRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        const raw = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        try {
          const wav = await convertWebmBlobToWav(raw);
          onAudioRef.current(wav);
        } catch {
          toast.error("Erro ao processar áudio. Tente enviar WAV/MP3 por arquivo.");
        }
      };
      recorder.start();
      mediaRef.current = recorder;
      setRecording(true);
    } catch {
      setMicDenied(true);
      toast.error("Microfone não disponível. Use o botão de arquivo para enviar áudio.");
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("audio/")) {
      toast.error("Formato não suportado. Use MP3, WAV ou WEBM.");
      e.target.value = "";
      return;
    }
    if (file.size > AUDIO_MAX_BYTES) {
      toast.error("Arquivo muito grande. Tamanho máximo: 25 MB.");
      e.target.value = "";
      return;
    }
    e.target.value = "";
    if (file.type === "audio/webm") {
      try {
        const wav = await convertWebmBlobToWav(file);
        onAudioRef.current(wav);
      } catch {
        toast.error("Erro ao converter WEBM. Tente enviar WAV ou MP3.");
      }
    } else {
      onAudioRef.current(file);
    }
  }

  return { recording, micDenied, toggleRecord, handleFileChange, fileRef };
}
