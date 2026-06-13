import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";
import { NextRequest } from "next/server";

/**
 * BFF (Backend for Frontend) proxy for the LangGraph server.
 *
 * Durability is set here — server-side Node.js — not in the browser UI.
 * The client calls /api/<langgraph-path> and this handler forwards to the
 * internal LangGraph server, injecting durability="exit" on run creation
 * to minimise checkpoint writes (1 write/turn instead of ~6).
 *
 * Env vars (runtime, NOT NEXT_PUBLIC_):
 *   LANGGRAPH_API_URL     — internal LangGraph server URL
 *   LANGGRAPH_AUTH_TOKEN  — shared x-api-key token
 */
const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } = initApiPassthrough({
  apiUrl: process.env.LANGGRAPH_API_URL,
  headers: (_req: NextRequest) => ({
    "X-Api-Key": process.env.LANGGRAPH_AUTH_TOKEN ?? "",
  }),
  bodyParameters: (req: NextRequest, body: unknown) => {
    if (req.method === "POST" && req.url.includes("/runs")) {
      const base = { ...(body as object), durability: "exit" };
      const requestId = req.headers.get("x-request-id");
      if (!requestId) return base;
      const existingMeta = (body as any)?.metadata ?? {};
      return {
        ...base,
        metadata: { ...existingMeta, request_id: requestId },
      };
    }
    return body;
  },
  baseRoute: "api",
  runtime: "nodejs",
  disableWarningLog: true,
});

export { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime };
