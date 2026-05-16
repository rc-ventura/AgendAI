/**
 * Unit tests for AudioUploadButton component (UC5 — áudio)
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AudioUploadButton } from "@/components/AudioUploadButton";

describe("AudioUploadButton — UC5 áudio", () => {
  it("renders both mic and file upload buttons", () => {
    render(<AudioUploadButton onAudio={vi.fn()} />);
    expect(screen.getByTitle("Gravar áudio")).toBeDefined();
    expect(screen.getByTitle("Enviar arquivo de áudio")).toBeDefined();
  });

  it("calls onAudio when an audio file is selected", () => {
    const onAudio = vi.fn();
    render(<AudioUploadButton onAudio={onAudio} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const fakeFile = new File([new Uint8Array([1, 2, 3])], "test.mp3", {
      type: "audio/mpeg",
    });

    Object.defineProperty(input, "files", {
      value: [fakeFile],
      configurable: true,
    });

    fireEvent.change(input);
    expect(onAudio).toHaveBeenCalledWith(fakeFile);
  });

  it("disables buttons when disabled=true", () => {
    render(<AudioUploadButton onAudio={vi.fn()} disabled />);
    const micBtn = screen.getByTitle("Gravar áudio") as HTMLButtonElement;
    const fileBtn = screen.getByTitle("Enviar arquivo de áudio") as HTMLButtonElement;
    expect(micBtn.disabled).toBe(true);
    expect(fileBtn.disabled).toBe(true);
  });

  it("accepts audio/* file types only", () => {
    render(<AudioUploadButton onAudio={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.accept).toBe("audio/*");
  });
});
