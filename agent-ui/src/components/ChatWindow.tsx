"use client";

import { useEffect, useRef, useState } from "react";
import { AudioUploadButton } from "./AudioUploadButton";
import {
  ChatMessage,
  getOrCreateThread,
  resetThread,
  sendAudio,
  streamChat,
} from "@/lib/langgraph";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 8,
      }}
    >
      <div
        style={{
          maxWidth: "70%",
          padding: "10px 14px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "#6366f1" : "#fff",
          color: isUser ? "#fff" : "#1f2937",
          boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
          whiteSpace: "pre-wrap",
          fontSize: 14,
          lineHeight: 1.5,
        }}
      >
        {msg.isAudio && <span style={{ marginRight: 6 }}>🎙</span>}
        {msg.content}
      </div>
    </div>
  );
}

export function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Olá! Sou o assistente AgendAI. Posso ajudar com agendamentos médicos, consulta de horários disponíveis, cancelamentos e informações de pagamento. Como posso ajudá-lo?",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getOrCreateThread().then(setThreadId);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function addMessage(msg: Omit<ChatMessage, "id">) {
    const id = crypto.randomUUID();
    setMessages((prev) => [...prev, { id, ...msg }]);
    return id;
  }

  async function handleSend() {
    if (!input.trim() || loading || !threadId) return;
    const text = input.trim();
    setInput("");
    addMessage({ role: "user", content: text });
    setLoading(true);

    const assistantId = addMessage({ role: "assistant", content: "" });

    try {
      for await (const chunk of streamChat(text, threadId)) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m
          )
        );
      }
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Erro ao processar mensagem. Tente novamente." }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleAudio(blob: Blob) {
    if (loading || !threadId) return;
    addMessage({ role: "user", content: "Mensagem de áudio enviada", isAudio: true });
    setLoading(true);
    const assistantId = addMessage({ role: "assistant", content: "Processando áudio..." });
    try {
      const reply = await sendAudio(blob, threadId);
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: reply } : m))
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Erro ao processar áudio. Tente novamente." }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    resetThread();
    setThreadId(null);
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: "Nova conversa iniciada. Como posso ajudá-lo?",
      },
    ]);
    getOrCreateThread().then(setThreadId);
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        maxWidth: 700,
        margin: "0 auto",
        background: "#fff",
        boxShadow: "0 0 20px rgba(0,0,0,0.08)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px 20px",
          background: "#6366f1",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontWeight: 700, fontSize: 18 }}>AgendAI</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>Assistente de Agendamento Médico</div>
        </div>
        <button
          onClick={handleReset}
          style={{
            background: "rgba(255,255,255,0.2)",
            border: "none",
            color: "#fff",
            padding: "6px 12px",
            borderRadius: 8,
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          Nova Conversa
        </button>
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px 20px",
          background: "#f8fafc",
        }}
      >
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {loading && (
          <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 8 }}>
            <div
              style={{
                padding: "10px 14px",
                borderRadius: "18px 18px 18px 4px",
                background: "#fff",
                boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                color: "#9ca3af",
                fontSize: 13,
              }}
            >
              Digitando...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid #e5e7eb",
          display: "flex",
          gap: 8,
          alignItems: "flex-end",
          background: "#fff",
        }}
      >
        <AudioUploadButton onAudio={handleAudio} disabled={loading} />
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Digite sua mensagem... (Enter para enviar)"
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: 12,
            border: "1px solid #d1d5db",
            resize: "none",
            fontSize: 14,
            fontFamily: "inherit",
            outline: "none",
            maxHeight: 120,
            minHeight: 42,
          }}
          rows={1}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          style={{
            padding: "10px 18px",
            borderRadius: 12,
            border: "none",
            background: "#6366f1",
            color: "#fff",
            fontWeight: 600,
            cursor: loading || !input.trim() ? "not-allowed" : "pointer",
            opacity: loading || !input.trim() ? 0.5 : 1,
            fontSize: 14,
          }}
        >
          Enviar
        </button>
      </div>
    </div>
  );
}
