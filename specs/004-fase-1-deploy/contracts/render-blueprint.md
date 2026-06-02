# Contract: Render Blueprint (`infra/render/render.yaml`)

**Feature**: [../spec.md](../spec.md) · **Decisions**: [../research.md](../research.md)
(D1, D2, D7, D8, D10).

Defines the production service topology. **Only `nginx` is public.** API, agent, and UI are
private services reachable only inside Render's private network (and the gateway).

---

## Service topology

```
Internet ──HTTPS──> nginx (PUBLIC, edge/reverse-proxy)
                      ├─ /                         → agent-ui-pro:3002   (PRIVATE, Next.js)
                      └─ /threads /runs /assistants → langgraph-server:8123 (PRIVATE)
                                                        └─ tool calls → api:3000 (PRIVATE)

Managed (NOT Render services): Neon Postgres (agendai_app, agendai_lg) · Upstash Redis · LangSmith
```

| Service | Render type | Public? | Image / build | Port |
|---|---|---|---|---|
| `nginx` | Docker web service | **Yes** | `./nginx` | 8080 → 443 (Render TLS) |
| `agent-ui-pro` | Docker (or Node) private service | No | `./agent-ui-pro` (build args) | 3002 |
| `langgraph-server` | Docker private service | No | GHCR image from `langgraph build` | 8123 |
| `api` | Node private service | No | `./api` | 3000 |

---

## Environment variable matrix

`sync: false` = set manually in the Render dashboard (secret). Internal hostnames use
Render's private service discovery.

### nginx (public)
| Var | Value | sync |
|---|---|---|
| `LANGGRAPH_AUTH_TOKEN` | shared agent token | false |
| upstream hosts | `agent-ui-pro`, `langgraph-server` (private hostnames) | template |

### agent-ui-pro (private) — build args (baked at build time)
| Var | Value | sync |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | **public nginx URL** (same-origin) | n/a (build arg) |
| `NEXT_PUBLIC_ASSISTANT_ID` | `agendai_agent` | n/a |
| `NEXT_PUBLIC_LANGGRAPH_API_KEY` | = `LANGGRAPH_AUTH_TOKEN` | false |

### langgraph-server (private)
| Var | Value | sync |
|---|---|---|
| `DATABASE_URI` | Neon `agendai_lg` connection string | false |
| `REDIS_URI` | Upstash Redis URL | false |
| `LANGSMITH_API_KEY` | server license key | false |
| `LANGCHAIN_API_KEY` | tracing key | false |
| `LANGCHAIN_TRACING_V2` | `true` | true |
| `LANGCHAIN_PROJECT` | `AgendAI` | true |
| `OPENAI_API_KEY` | model/STT/TTS key | false |
| `API_BASE_URL` | `http://api:3000` (private) | true |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | optional SMTP | false |

### api (private)
| Var | Value | sync |
|---|---|---|
| `DATABASE_URL` | Neon `agendai_app` connection string | false |
| `PORT` | `3000` | true |

---

## Managed dependencies (created outside Render)

1. **Neon** — one project, two databases:
   - `agendai_app` → `DATABASE_URL` (api)
   - `agendai_lg` → `DATABASE_URI` (langgraph-server)
   - Connection strings require SSL (`?sslmode=require`).
2. **Upstash Redis** — one database → `REDIS_URI` (langgraph-server SSE).
3. **LangSmith Developer** — `LANGSMITH_API_KEY` (license) + `LANGCHAIN_API_KEY` (tracing).

`infra/render/` should include a short README documenting how to create these and paste the
resulting secrets into Render.

---

## Acceptance

- `render.yaml` validates as a Render Blueprint; `nginx` is the only service with a public
  URL.
- Hitting the public URL serves the UI at `/` and proxies agent calls; the private services
  have no public route (US4 / SC-007).
- A first redeploy preserves data (managed DB) and threads (FR-005/FR-006).
