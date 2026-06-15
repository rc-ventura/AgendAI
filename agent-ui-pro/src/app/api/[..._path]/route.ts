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
 *
 * initApiPassthrough is deferred to first request (not module load) so that
 * `next build` does not throw when LANGGRAPH_API_URL is absent at build time.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Handlers = ReturnType<typeof initApiPassthrough>;
let _handlers: Handlers | null = null;

function getHandlers(): Handlers {
  if (!_handlers) {
    _handlers = initApiPassthrough({
      apiUrl: process.env.LANGGRAPH_API_URL,
      headers: (_req: NextRequest) => ({
        "X-Api-Key": process.env.LANGGRAPH_AUTH_TOKEN ?? "",
      }),
      bodyParameters: (req: NextRequest, body: unknown) => {
        if (req.method === "POST" && req.url.includes("/runs")) {
          const base = { ...(body as object), durability: "exit" };
          const requestId = req.headers.get("x-request-id");
          if (!requestId) return base;
          const existingMeta = (body as Record<string, unknown>)?.metadata ?? {};
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
  }
  return _handlers;
}

export const GET     = (req: NextRequest) => getHandlers().GET(req);
export const POST    = (req: NextRequest) => getHandlers().POST(req);
export const PUT     = (req: NextRequest) => getHandlers().PUT(req);
export const PATCH   = (req: NextRequest) => getHandlers().PATCH(req);
export const DELETE  = (req: NextRequest) => getHandlers().DELETE(req);
export const OPTIONS = () => getHandlers().OPTIONS();
