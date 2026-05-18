"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";

export const AUDIO_MAX_BYTES = 25 * 1024 * 1024; // 25 MB
export const AUDIO_ACCEPT = "audio/mp3,audio/mpeg,audio/wav,audio/webm,audio/*";

interface UseAudioOptions {
  onAudio: (blob: Blob) => void;
  disabled?: boolean;
}

export function useAudio({ onAudio, disabled }: UseAudioOptions) {
  const [recording, setRecording] = useState(false);
  const [micDenied, setMicDenied] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

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
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        onAudio(blob);
      };
      recorder.start();
      mediaRef.current = recorder;
      setRecording(true);
    } catch {
      setMicDenied(true);
      toast.error("Microfone não disponível. Use o botão de arquivo para enviar áudio.");
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
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
    onAudio(file);
    e.target.value = "";
  }

  return { recording, micDenied, toggleRecord, handleFileChange, fileRef };
}
