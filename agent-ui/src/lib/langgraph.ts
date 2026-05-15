import { Client } from "@langchain/langgraph-sdk";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8123";
export const graphId = process.env.NEXT_PUBLIC_GRAPH_ID ?? "agendai_agent";

export function createClient() {
  return new Client({ apiUrl });
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

  for await (const chunk of stream) {
    if (chunk.event === "messages/partial") {
      const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
      for (const msg of msgs) {
        if (msg?.role === "assistant" && msg?.content) {
          yield msg.content;
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
