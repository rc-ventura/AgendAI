/**
 * Integration tests for lib/langgraph.ts
 * Mocks @langchain/langgraph-sdk Client directly — no fetch/jsdom issues.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Mock the SDK before importing our wrapper ─────────────────────────────────

const mockCreate = vi.fn().mockResolvedValue({ thread_id: "test-thread-123" });

async function* makeStreamEvents(events: Array<{ event: string; data: unknown }>) {
  for (const e of events) yield e;
}

const mockStream = vi.fn();

vi.mock("@langchain/langgraph-sdk", () => ({
  Client: vi.fn().mockImplementation(() => ({
    threads: { create: mockCreate },
    runs: { stream: mockStream },
  })),
}));

import { getOrCreateThread, resetThread, streamChat, sendAudio } from "@/lib/langgraph";

// ─────────────────────────────────────────────────────────────────────────────

beforeEach(() => {
  resetThread();
  vi.clearAllMocks();
  mockCreate.mockResolvedValue({ thread_id: "test-thread-123" });
});

// ── Thread management ─────────────────────────────────────────────────────────

describe("Thread management", () => {
  it("creates a thread and returns thread_id", async () => {
    const id = await getOrCreateThread();
    expect(id).toBe("test-thread-123");
    expect(mockCreate).toHaveBeenCalledOnce();
  });

  it("reuses thread_id on subsequent calls without creating a new one", async () => {
    await getOrCreateThread();
    await getOrCreateThread();
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it("creates a new thread after resetThread()", async () => {
    await getOrCreateThread();
    resetThread();
    await getOrCreateThread();
    expect(mockCreate).toHaveBeenCalledTimes(2);
  });
});

// ── UC1 — consultar horários ──────────────────────────────────────────────────

describe("UC1 — consultar horários disponíveis", () => {
  it("yields assistant message content from stream", async () => {
    const reply = "Temos horários: Segunda 09h com Dr. Carlos Lima.";
    mockStream.mockReturnValue(
      makeStreamEvents([
        { event: "messages/partial", data: [{ role: "assistant", content: reply }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("Quais horários?", "thread-123")) {
      chunks.push(c);
    }
    expect(chunks.join("")).toBe(reply);
  });
});

// ── UC2 — agendar consulta ────────────────────────────────────────────────────

describe("UC2 — agendar consulta por texto", () => {
  it("sends correct input_type=text and yields reply", async () => {
    const reply = "Consulta agendada com sucesso!";
    mockStream.mockReturnValue(
      makeStreamEvents([
        { event: "messages/partial", data: [{ role: "assistant", content: reply }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("Agendar para joao@email.com horário 3", "t1")) {
      chunks.push(c);
    }
    expect(chunks.join("")).toContain("agendada");

    const [, , opts] = mockStream.mock.calls[0] as [string, string, { input: { input_type: string } }];
    expect(opts.input.input_type).toBe("text");
  });
});

// ── UC3 — cancelar agendamento ────────────────────────────────────────────────

describe("UC3 — cancelar agendamento por texto", () => {
  it("yields cancellation reply", async () => {
    const reply = "Agendamento cancelado com sucesso!";
    mockStream.mockReturnValue(
      makeStreamEvents([
        { event: "messages/partial", data: [{ role: "assistant", content: reply }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("Cancelar consulta 1", "t1")) {
      chunks.push(c);
    }
    expect(chunks.join("")).toContain("cancelado");
  });
});

// ── UC4 — valores e pagamento ─────────────────────────────────────────────────

// ── Streaming delta tracking (regression: per-message-id accumulator) ─────────

describe("streamChat — delta tracking across multiple AIMessages", () => {
  it("accumulates deltas per message id (single growing message)", async () => {
    mockStream.mockReturnValue(
      makeStreamEvents([
        { event: "messages/partial", data: [{ id: "m1", role: "assistant", content: "Olá" }] },
        { event: "messages/partial", data: [{ id: "m1", role: "assistant", content: "Olá, tudo" }] },
        { event: "messages/partial", data: [{ id: "m1", role: "assistant", content: "Olá, tudo bem?" }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("oi", "t1")) chunks.push(c);

    expect(chunks).toEqual(["Olá", ", tudo", " bem?"]);
    expect(chunks.join("")).toBe("Olá, tudo bem?");
  });

  it("does NOT truncate a second AIMessage that follows a longer one", async () => {
    // Regression for: prevContent leaking across messages would slice off the
    // beginning of msg #2 until it grew past msg #1's length.
    mockStream.mockReturnValue(
      makeStreamEvents([
        // First AIMessage (e.g. "thinking out loud" before a tool call)
        { event: "messages/partial", data: [{ id: "m1", role: "assistant", content: "Vou verificar isso pra você agora." }] },
        // Second AIMessage starts from scratch with a SHORTER beginning
        { event: "messages/partial", data: [{ id: "m2", role: "assistant", content: "Encontrei" }] },
        { event: "messages/partial", data: [{ id: "m2", role: "assistant", content: "Encontrei 3 horários" }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("agendar", "t1")) chunks.push(c);

    // m1 fully delivered, m2 fully delivered (not silently truncated)
    expect(chunks).toEqual([
      "Vou verificar isso pra você agora.",
      "Encontrei",
      " 3 horários",
    ]);
  });
});

describe("UC4 — consultar valores e formas de pagamento", () => {
  it("yields price and payment info", async () => {
    const reply = "Consulta: R$ 200,00. Formas: PIX, Cartão, Dinheiro.";
    mockStream.mockReturnValue(
      makeStreamEvents([
        { event: "messages/partial", data: [{ role: "assistant", content: reply }] },
      ])
    );

    const chunks: string[] = [];
    for await (const c of streamChat("Quanto custa?", "t1")) {
      chunks.push(c);
    }
    expect(chunks.join("")).toMatch(/R\$|PIX/);
  });
});

// ── UC5 — áudio ───────────────────────────────────────────────────────────────

// jsdom Blob doesn't implement arrayBuffer() — create a compatible fake
function makeAudioBlob(): Blob {
  const buf = new Uint8Array([1, 2, 3]).buffer;
  const blob = new Blob([buf], { type: "audio/mpeg" });
  // polyfill for jsdom
  (blob as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer = () =>
    Promise.resolve(buf);
  return blob;
}

describe("UC5 — envio de áudio", () => {
  it("sends input_type=audio and returns assistant text", async () => {
    const reply = "Temos horários disponíveis às 9h.";
    mockStream.mockReturnValue(
      makeStreamEvents([
        {
          event: "values",
          data: {
            messages: [{ role: "assistant", content: reply }],
            final_response: null,
          },
        },
      ])
    );

    const result = await sendAudio(makeAudioBlob(), "t1");

    const [, , opts] = mockStream.mock.calls[0] as [string, string, { input: { input_type: string } }];
    expect(opts.input.input_type).toBe("audio");
    expect(result).toBe(reply);
  });

  it("returns fallback message when stream is empty", async () => {
    mockStream.mockReturnValue(makeStreamEvents([]));
    const result = await sendAudio(makeAudioBlob(), "t1");
    expect(result).toBeTruthy();
  });
});
