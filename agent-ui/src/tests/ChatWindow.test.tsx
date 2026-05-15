/**
 * Integration tests for ChatWindow component
 * Validates the full UI interaction flows from the challenge.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the langgraph lib so we control the stream
vi.mock("@/lib/langgraph", () => ({
  getOrCreateThread: vi.fn().mockResolvedValue("thread-abc"),
  resetThread: vi.fn(),
  streamChat: vi.fn(),
  sendAudio: vi.fn(),
}));

import { ChatWindow } from "@/components/ChatWindow";
import * as lg from "@/lib/langgraph";

async function* makeStream(chunks: string[]) {
  for (const c of chunks) yield c;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(lg.getOrCreateThread).mockResolvedValue("thread-abc");
});

describe("ChatWindow — mensagem inicial", () => {
  it("shows welcome message on load", async () => {
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([]));
    render(<ChatWindow />);
    expect(screen.getByText(/Sou o assistente AgendAI/i)).toBeDefined();
  });
});

describe("UC1 — consultar horários (texto)", () => {
  it("sends text message and renders streamed reply", async () => {
    const reply = "Temos horários: Segunda 09h com Dr. Carlos Lima.";
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([reply]));

    render(<ChatWindow />);
    await waitFor(() => screen.getByPlaceholderText(/Digite sua mensagem/));

    const input = screen.getByPlaceholderText(/Digite sua mensagem/) as HTMLTextAreaElement;
    await userEvent.type(input, "Quais horários disponíveis?");
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(/Quais horários disponíveis\?/)).toBeDefined();
    });
    await waitFor(() => {
      expect(screen.getByText(reply)).toBeDefined();
    });

    expect(lg.streamChat).toHaveBeenCalledWith(
      "Quais horários disponíveis?",
      "thread-abc"
    );
  });
});

describe("UC2 — agendar consulta (texto)", () => {
  it("sends scheduling request and shows confirmation", async () => {
    const reply = "Consulta agendada com sucesso! E-mail enviado.";
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([reply]));

    render(<ChatWindow />);
    await waitFor(() => screen.getByPlaceholderText(/Digite sua mensagem/));

    const input = screen.getByPlaceholderText(/Digite sua mensagem/) as HTMLTextAreaElement;
    await userEvent.type(input, "Agendar para joao@email.com horário 3");
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(reply)).toBeDefined();
    });
  });
});

describe("UC3 — cancelar agendamento (texto)", () => {
  it("sends cancellation request and shows confirmation", async () => {
    const reply = "Agendamento cancelado. E-mail de confirmação enviado.";
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([reply]));

    render(<ChatWindow />);
    await waitFor(() => screen.getByPlaceholderText(/Digite sua mensagem/));

    const input = screen.getByPlaceholderText(/Digite sua mensagem/) as HTMLTextAreaElement;
    await userEvent.type(input, "Cancelar consulta 1");
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(reply)).toBeDefined();
    });
  });
});

describe("UC4 — valores e pagamento (texto)", () => {
  it("returns price and payment info", async () => {
    const reply = "Consulta: R$ 200,00. Formas: PIX, Cartão.";
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([reply]));

    render(<ChatWindow />);
    await waitFor(() => screen.getByPlaceholderText(/Digite sua mensagem/));

    const input = screen.getByPlaceholderText(/Digite sua mensagem/) as HTMLTextAreaElement;
    await userEvent.type(input, "Quanto custa?");
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText(reply)).toBeDefined();
    });
  });
});

describe("UC5 — envio de áudio", () => {
  it("calls sendAudio with audio blob and shows reply", async () => {
    const reply = "Temos horários disponíveis às 9h.";
    vi.mocked(lg.sendAudio).mockResolvedValue(reply);

    render(<ChatWindow />);
    await waitFor(() => screen.getByTitle("Enviar arquivo de áudio"));

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const audioBlob = new File([new Uint8Array([1, 2, 3])], "audio.mp3", {
      type: "audio/mpeg",
    });
    Object.defineProperty(input, "files", { value: [audioBlob], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(lg.sendAudio).toHaveBeenCalledWith(audioBlob, "thread-abc");
    });
    await waitFor(() => {
      expect(screen.getByText(reply)).toBeDefined();
    });
  });

  it("shows audio indicator emoji when audio message is sent", async () => {
    vi.mocked(lg.sendAudio).mockResolvedValue("Resposta de áudio.");

    render(<ChatWindow />);
    await waitFor(() => screen.getByTitle("Enviar arquivo de áudio"));

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const audioFile = new File([new Uint8Array([1])], "msg.mp3", { type: "audio/mpeg" });
    Object.defineProperty(input, "files", { value: [audioFile], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      // The mic emoji appears in user bubble for audio messages
      expect(document.body.textContent).toContain("🎙");
    });
  });
});

describe("Nova conversa", () => {
  it("resets thread and shows new welcome message", async () => {
    vi.mocked(lg.streamChat).mockImplementation(() => makeStream([]));
    render(<ChatWindow />);

    const btn = screen.getByText("Nova Conversa");
    await userEvent.click(btn);

    expect(lg.resetThread).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText(/Nova conversa iniciada/i)).toBeDefined();
    });
  });
});
