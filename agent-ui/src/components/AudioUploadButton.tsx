"use client";

import { useRef, useState } from "react";

interface Props {
  onAudio: (blob: Blob) => void;
  disabled?: boolean;
}

export function AudioUploadButton({ onAudio, disabled }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [recording, setRecording] = useState(false);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  async function toggleRecord() {
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
        onAudio(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      recorder.start();
      mediaRef.current = recorder;
      setRecording(true);
    } catch {
      alert("Microfone não disponível");
    }
  }

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onAudio(file);
    e.target.value = "";
  }

  const btnStyle: React.CSSProperties = {
    padding: "8px 12px",
    borderRadius: 8,
    border: "none",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: 18,
    background: recording ? "#ef4444" : "#6366f1",
    color: "#fff",
    opacity: disabled ? 0.5 : 1,
  };

  return (
    <div style={{ display: "flex", gap: 4 }}>
      <button style={btnStyle} onClick={toggleRecord} disabled={disabled} title={recording ? "Parar gravação" : "Gravar áudio"}>
        {recording ? "⏹" : "🎙"}
      </button>
      <button
        style={{ ...btnStyle, background: "#4b5563", fontSize: 16 }}
        onClick={() => fileRef.current?.click()}
        disabled={disabled}
        title="Enviar arquivo de áudio"
      >
        📎
      </button>
      <input ref={fileRef} type="file" accept="audio/*" style={{ display: "none" }} onChange={handleFile} />
    </div>
  );
}
