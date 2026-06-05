# ADR-022 — Backend-for-Frontend (BFF) com Next.js para segurança do token LangGraph

**Status:** Proposto (Fase 1 usa token compartilhado; BFF entra na Fase 2 ou spec 005)

**Data:** 2026-06-03

---

## Contexto

Na arquitetura atual (Fase 1), o token de autenticação do agente (`LANGGRAPH_AUTH_TOKEN`) é
exposto no bundle JavaScript da UI como `NEXT_PUBLIC_LANGGRAPH_API_KEY`. Qualquer usuário pode
extraí-lo via DevTools e chamar o nginx diretamente, bypassando a UI.

Isso é uma consequência estrutural do padrão adotado pelo `@langchain/langgraph-sdk`: o SDK foi
desenhado para fazer chamadas SSE **diretamente do browser** ao LangGraph Server, o que exige
que a credencial esteja disponível no client-side.

Mesmo com redes privadas (Fase 2 — Terraform), o problema persiste: o nginx é obrigatoriamente
público, e o token que o nginx exige para liberar acesso ao agente continua visível no browser.

---

## Decisão

Implementar um **BFF (Backend-for-Frontend)** usando as **API Routes do Next.js App Router**
como proxy transparente entre o browser e o LangGraph Server.

O token sai do bundle do browser e passa a viver exclusivamente no servidor Next.js, como
variável de ambiente sem prefixo `NEXT_PUBLIC_`.

---

## Arquitetura com BFF

```
Fase 1 (atual):
Browser (token no JS) ──x-api-key──► nginx ──► langgraph-server

Fase 2 com BFF:
Browser (sem token) ──► nginx ──► Next.js /api/langgraph/* ──x-api-key──► langgraph-server
                                        ↑
                              LANGGRAPH_AUTH_TOKEN (server-side)
                              Validação de sessão/JWT do usuário
```

---

## Implementação

### 1. Catch-all route no Next.js

```ts
// agent-ui-pro/app/api/langgraph/[...path]/route.ts
import { NextRequest } from "next/server";

const LANGGRAPH_URL = process.env.LANGGRAPH_URL!;        // sem NEXT_PUBLIC_
const LANGGRAPH_TOKEN = process.env.LANGGRAPH_AUTH_TOKEN!; // sem NEXT_PUBLIC_

async function proxy(req: NextRequest, path: string) {
  const upstream = await fetch(`${LANGGRAPH_URL}/${path}`, {
    method: req.method,
    headers: {
      "x-api-key": LANGGRAPH_TOKEN,
      "Content-Type": req.headers.get("Content-Type") ?? "application/json",
    },
    body: req.method !== "GET" ? req.body : undefined,
    // @ts-expect-error — necessário para streaming bidirecional (Node 18+)
    duplex: "half",
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-cache",
    },
  });
}

export const GET  = (req: NextRequest, { params }: any) => proxy(req, params.path.join("/"));
export const POST = (req: NextRequest, { params }: any) => proxy(req, params.path.join("/"));
export const PUT  = (req: NextRequest, { params }: any) => proxy(req, params.path.join("/"));
export const DELETE = (req: NextRequest, { params }: any) => proxy(req, params.path.join("/"));
```

### 2. SDK aponta para o proxy Next.js

```ts
// NEXT_PUBLIC_API_URL=/api/langgraph  ← relativo, sem segredo
const client = new Client({ apiUrl: process.env.NEXT_PUBLIC_API_URL })
```

### 3. Variáveis de ambiente

```bash
# Sem NEXT_PUBLIC_ — nunca vão ao browser
LANGGRAPH_URL=https://agendai-langgraph.onrender.com
LANGGRAPH_AUTH_TOKEN=...

# Com NEXT_PUBLIC_ — apenas a URL do proxy Next.js (não é segredo)
NEXT_PUBLIC_API_URL=/api/langgraph
NEXT_PUBLIC_ASSISTANT_ID=agendai_agent
```

---

## SSE / Streaming

O Next.js App Router faz pipe do `ReadableStream` diretamente para o browser sem bufferizar,
desde que o `Content-Type` seja `text/event-stream`. O streaming token-a-token do LangGraph
é preservado sem perda de latência perceptível.

```
LangGraph ──SSE stream──► Next.js route handler ──SSE stream──► Browser
                              (pipe direto, sem buffer)
```

---

## Consequências

### Positivas

- Token do LangGraph nunca presente no browser
- Bypass via DevTools eliminado
- Ponto natural para adicionar validação de sessão/JWT (P3 — auth de usuário):
  o middleware do Next.js valida o JWT antes de repassar ao LangGraph
- nginx fica mais simples: só roteia, sem validar token do LangGraph
- Preparação para o padrão de auth de Fase 3 (Cognito/Firebase → JWT no Next.js middleware)

### Negativas / Trade-offs

- Latência adicional de 1 hop (browser → Next.js → LangGraph)
- Necessidade de implementar proxy para todos os métodos HTTP usados pelo SDK
- Next.js no free tier do Render também sofre spin-down após 15 min de inatividade
- Adiciona complexidade ao `agent-ui-pro`

---

## Alternativas consideradas

### Token compartilhado (status quo — Fase 1)
Simples, funciona, mas expõe o token no browser permanentemente.
Aceitável para portfólio/demo; inaceitável para produção real.

### Redes privadas sem BFF (Fase 2 — Terraform)
Protege comunicação servidor-a-servidor, mas não resolve token no browser.
O nginx permanece público e o token continua extraível via DevTools.

### JWT por usuário sem BFF (Fase 3 — Cognito)
Melhora em relação ao token compartilhado: JWT é por usuário, expira, tem escopo.
Mas o JWT ainda fica no browser — só reduz o impacto, não elimina a exposição.

### BFF + JWT (combinação ideal)
BFF elimina o token do browser. JWT valida o usuário no Next.js middleware.
Nenhum segredo de serviço chega ao client-side. Solução completa para produção.

---

## Relação com outras decisões

- **ADR-016** (nginx reverse proxy): com BFF, o nginx não precisa mais validar
  `x-api-key` para o LangGraph — apenas roteia. O `LANGGRAPH_AUTH_TOKEN` sai
  do nginx e fica somente no Next.js.
- **ADR-017** (segurança por tokens): este ADR substitui o token compartilhado
  client-side pela abordagem BFF + validação server-side.
- **ADR-019** (Chat UI com Next.js): o BFF é uma extensão natural do Next.js —
  usa API Routes do App Router sem adicionar nova tecnologia ao stack.
