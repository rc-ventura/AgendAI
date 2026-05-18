"use client";

import { useEffect, useRef, useState } from "react";
import { useStreamContext } from "@/providers/Stream";

function decodeToBytes(value: unknown): Uint8Array | null {
  if (typeof value === "string") {
    // LangGraph serializes Python bytes as base64 string
    try {
      const binary = atob(value);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      return bytes;
    } catch {
      return null;
    }
  }
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === "number") {
    return new Uint8Array(value);
  }
  return null;
}

export function useTtsPlayer() {
  const stream = useStreamContext();
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const prevResponseRef = useRef<unknown>(null);

  useEffect(() => {
    // Only act once loading finishes
    if (stream.isLoading) return;

    const values = (stream as any).values as Record<string, unknown> | undefined;
    const finalResponse = values?.final_response;

    // Skip if nothing new
    if (!finalResponse || finalResponse === prevResponseRef.current) return;
    prevResponseRef.current = finalResponse;

    const bytes = decodeToBytes(finalResponse);
    if (!bytes) return;

    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      const blob = new Blob([bytes], { type: "audio/mpeg" });
      return URL.createObjectURL(blob);
    });
  }, [stream.isLoading, (stream as any).values?.final_response]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, []);

  return { audioUrl };
}
