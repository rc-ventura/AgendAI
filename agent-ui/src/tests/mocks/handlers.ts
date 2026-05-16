import { http, HttpResponse } from "msw";

const BASE_URL = "http://localhost:8123";

export const handlers = [
  // Create thread
  http.post(`${BASE_URL}/threads`, () => {
    return HttpResponse.json({ thread_id: "test-thread-123" });
  }),

  // Stream run — text response
  http.post(`${BASE_URL}/threads/:threadId/runs/stream`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const input = body?.input as Record<string, unknown> | undefined;
    const messages = input?.messages as Array<{ content: string }> | undefined;
    const inputType = input?.input_type as string | undefined;

    if (inputType === "audio") {
      // Audio flow — returns values event with final_response
      const stream = new ReadableStream({
        start(controller) {
          const encode = (s: string) => new TextEncoder().encode(s);
          controller.enqueue(encode('event: values\ndata: {"messages":[{"role":"assistant","content":"Temos horários disponíveis às 9h com Dr. Carlos Lima."}],"final_response":null}\n\n'));
          controller.enqueue(encode('event: values\ndata: {"messages":[{"role":"assistant","content":"Temos horários disponíveis às 9h com Dr. Carlos Lima."}],"final_response":"AUDIO_BYTES_BASE64"}\n\n'));
          controller.enqueue(encode("event: end\ndata: {}\n\n"));
          controller.close();
        },
      });
      return new HttpResponse(stream, {
        headers: { "Content-Type": "text/event-stream" },
      });
    }

    const userText = messages?.[0]?.content ?? "";
    let reply = "Olá! Como posso ajudá-lo?";

    if (/horário|horario|disponív/i.test(userText)) {
      reply = "Temos horários disponíveis:\n- Segunda 09:00 — Dr. Carlos Lima\n- Terça 14:00 — Dra. Ana Costa";
    } else if (/agend/i.test(userText)) {
      reply = "Consulta agendada com sucesso! Você receberá uma confirmação por e-mail.";
    } else if (/cancel/i.test(userText)) {
      reply = "Agendamento cancelado com sucesso! E-mail de confirmação enviado.";
    } else if (/pagamento|valor|custa/i.test(userText)) {
      reply = "Consulta: R$ 200,00. Formas aceitas: PIX, Cartão de crédito, Dinheiro.";
    }

    const stream = new ReadableStream({
      start(controller) {
        const encode = (s: string) => new TextEncoder().encode(s);
        controller.enqueue(encode(`event: messages/partial\ndata: [{"role":"assistant","content":"${reply}"}]\n\n`));
        controller.enqueue(encode("event: end\ndata: {}\n\n"));
        controller.close();
      },
    });

    return new HttpResponse(stream, {
      headers: { "Content-Type": "text/event-stream" },
    });
  }),
];
