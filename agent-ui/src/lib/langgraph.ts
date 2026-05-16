import { Client } from "@langchain/langgraph-sdk";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8123";
const apiKey = process.env.NEXT_PUBLIC_LANGGRAPH_API_KEY;
export const graphId = process.env.NEXT_PUBLIC_GRAPH_ID ?? "agendai_agent";

export function createClient() {
  return new Client({ apiUrl, apiKey });
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isAudio?: boolean;
}

let threadId: string | null = null;

export async function getOrCreateThread(): Promise<string> {
  if (threadId) return threadId;
  const client = createClient();
  const thread = await client.threads.create();
  threadId = thread.thread_id;
  return threadId;
}

export function resetThread() {
  threadId = null;
}

export async function* streamChat(
  userMessage: string,
  currentThreadId: string
): AsyncGenerator<string> {
  const client = createClient();

  const stream = client.runs.stream(currentThreadId, graphId, {
    input: {
      messages: [{ role: "user", content: userMessage }],
      input_type: "text",
    },
    streamMode: "messages",
  });

  // Track accumulated content PER message id so that a new AIMessage
  // (e.g. after a tool round, or when the LLM emits text + tool_call in one
  // message and then a separate final answer) does not get its initial
  // characters silently truncated by a stale prevContent from a previous
  // message.
  const seen = new Map<string, string>();
  for await (const chunk of stream) {
    if (chunk.event === "messages/partial") {
      const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
      for (const msg of msgs) {
        const isAI = msg?.type === "ai" || msg?.type === "AIMessageChunk" || msg?.role === "assistant";
        if (!isAI) continue;
        const raw = msg?.content;
        if (!raw) continue;
        const fullText = typeof raw === "string"
          ? raw
          : Array.isArray(raw)
            ? raw.map((p: unknown) => (typeof p === "string" ? p : (p as { text?: string })?.text ?? "")).join("")
            : "";
        const msgId = (msg?.id as string | undefined) ?? "__default__";
        const prev = seen.get(msgId) ?? "";
        const delta = fullText.slice(prev.length);
        if (delta) {
          seen.set(msgId, fullText);
          yield delta;
        }
      }
    }
  }
}

export async function sendAudio(
  audioBlob: Blob,
  currentThreadId: string
): Promise<string> {
  const client = createClient();
  const arrayBuffer = await audioBlob.arrayBuffer();
  const audioData = Array.from(new Uint8Array(arrayBuffer));

  let result = "";
  const stream = client.runs.stream(currentThreadId, graphId, {
    input: {
      messages: [{ role: "user", content: "[Mensagem de áudio]" }],
      input_type: "audio",
      audio_data: audioData,
    },
    streamMode: "values",
  });

  for await (const chunk of stream) {
    if (chunk.event === "values" && chunk.data?.final_response) {
      result = "[Resposta em áudio recebida]";
    }
    if (chunk.event === "values" && chunk.data?.messages) {
      const msgs = chunk.data.messages;
      const last = msgs[msgs.length - 1];
      if (last?.role === "assistant" || last?.type === "ai") {
        result = last.content ?? result;
      }
    }
  }

  return result || "[Áudio processado]";
}
