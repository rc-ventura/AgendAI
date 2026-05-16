import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AgendAI — Agendamento Médico",
  description: "Assistente inteligente para agendamento médico",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f0f4f8" }}>
        {children}
      </body>
    </html>
  );
}
