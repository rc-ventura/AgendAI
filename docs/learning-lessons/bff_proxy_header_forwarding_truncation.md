# BFF Proxy Header Forwarding: content-encoding + content-length Truncation

**Context:** Descoberto durante o debug de produção do AgendAI (Spec 005) ao investigar `SyntaxError: Unterminated string in JSON at position 158/160` no browser. O erro aparecia no console DevTools mas não em nenhum log de serviço.
**Date:** 2026-06-16

---

## Mental Model: Decompressão Silenciosa do undici + Headers Obsoletos

O Node.js `fetch` (undici) descomprime o body do upstream **transparentemente**, mas mantém os headers originais intactos. Quando o BFF repassa esses headers para o cliente, o tamanho declarado não bate com o body real.

```
LangGraph Server
  │  body: gzip(JSON) → 155 bytes
  │  headers: content-encoding: gzip
  │            content-length: 155
  ▼
Node.js fetch (undici) no BFF
  │  decomprime silenciosamente
  │  body em memória: JSON puro → 256 bytes   ← body MUDOU
  │  res.headers: content-encoding: gzip      ← headers NÃO mudaram
  │               content-length: 155         ← ainda aponta para o tamanho comprimido
  ▼
langgraph-nextjs-api-passthrough
  │  copia TODOS os headers verbatim:
  │  new NextResponse(res.body, { headers: { ...res.headers } })
  │                                            ← body=256 bytes puros
  │                                            ← header diz 155 bytes gzip
  ▼
Next.js standalone (compress: true por padrão)
  │  vê body puro de 256 bytes → aplica brotli → 118 bytes
  │  mas content-length: 155 continua nos headers
  ▼
nginx / Cloudflare → Browser
  browser recebe 118 bytes brotli + content-length: 155 (errado)
  descomprime brotli → recebe JSON truncado (~155 bytes) de 256
  └─► SyntaxError: Unterminated string in JSON at position 158
```

| Camada | O que muda | O que NÃO muda automaticamente |
|---|---|---|
| undici (Node.js fetch) | Descomprime o body | Headers `content-encoding`, `content-length` |
| `langgraph-nextjs-api-passthrough` | Repassa body e headers | Não filtra headers problemáticos |
| Next.js standalone | Recomprime com brotli | Não recalcula `content-length` se já setado |

---

## Diagnóstico

O erro `SyntaxError: Unterminated string` não aparece em nenhum log de servidor — é puramente client-side. Para localizar:

```bash
# 1. Medir o tamanho via BFF vs direto
curl -s "https://agendai-nginx.onrender.com/api/info" -H "X-Api-Key: <token>" | wc -c
# → 155 bytes (truncado) ← BFF com bug

curl -s "https://agendai-langgraph.onrender.com/info" -H "X-Api-Key: <token>" | wc -c
# → 256 bytes (correto) ← LangGraph direto

# 2. Verificar headers de resposta do BFF
curl -sI "https://agendai-nginx.onrender.com/api/info" -H "X-Api-Key: <token>" | grep -i content
# → content-encoding: br   ← brotli aplicado pelo Next.js
# → content-length: 155    ← tamanho antigo do upstream (errado)
```

---

## Fix Aplicado no AgendAI

**Arquivo:** `agent-ui-pro/src/app/api/[..._path]/route.ts`

Envolver cada handler para deletar os headers de encoding/tamanho antes que o Next.js processe a resposta:

```typescript
async function stripEncodingHeaders(p: Promise<Response>): Promise<Response> {
  const res = await p;
  const h = new Headers(res.headers);
  h.delete("content-encoding");   // evita conflito de encoding
  h.delete("content-length");     // Next.js recalcula o valor correto
  h.delete("transfer-encoding"); // undici já de-chunkou; header ficou obsoleto
  return new Response(res.body, { status: res.status, headers: h });
}

const wrap =
  (fn: (req: NextRequest) => Promise<Response>) =>
  (req: NextRequest) =>
    stripEncodingHeaders(fn(req));

export const GET    = wrap((req) => getHandlers().GET(req));
export const POST   = wrap((req) => getHandlers().POST(req));
// ... demais métodos
```

Com isso, o Next.js calcula `content-length` e `content-encoding` corretos para o body real — e o browser recebe JSON completo.

---

## Fix Secundário: nginx chunked_transfer_encoding

Mesmo sem o problema de headers, havia um segundo ponto de truncação no nginx.

**Arquivo:** `nginx/nginx.conf.template` — bloco `/api/`

```nginx
# ❌ ANTES: proxy_buffering off + chunked_transfer_encoding off = conflito
location /api/ {
    proxy_buffering           off;
    chunked_transfer_encoding off;   # ← REMOVIDO
    ...
}
```

Com `proxy_buffering off` (não pode bufferizar) e `chunked_transfer_encoding off` (não pode usar chunked TE), o nginx não conseguia enquadrar respostas do Next.js sem `Content-Length` → enviava apenas o primeiro buffer (~155 bytes) e fechava.

O bloco LangGraph direto mantém `chunked_transfer_encoding off` porque o LangGraph inclui `Content-Length` nas respostas JSON e usa SSE nativo para streams.

---

## Regra Geral para BFF Proxies com Next.js

Sempre que um BFF reutilizar a resposta de um upstream HTTP:

1. **Deletar** `content-encoding`, `content-length`, `transfer-encoding` da resposta upstream antes de retornar
2. Deixar o Next.js (ou o HTTP server) recalcular esses headers para o body real
3. Se usar nginx à frente do Next.js, **não** usar `chunked_transfer_encoding off` para rotas BFF que retornam streams sem `Content-Length`

---

## Relação com ADRs e próximos passos

- **Spec 005** — bug de produção resolvido; SSE e JSON via BFF funcionando corretamente
- Considerar abrir issue no repositório `bracesproul/langgraph-nextjs-api-passthrough` reportando o comportamento de cópia verbatim de `content-encoding`/`content-length`
