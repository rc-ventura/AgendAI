# Contract: CI/CD (`.github/workflows/ci.yml` + `deploy.yml`)

**Feature**: [../spec.md](../spec.md) · **Decisions**: [../research.md](../research.md)
(D6, D9, D10). Roadmap section 02.

Two workflows. CI is the **merge gate**; deploy runs only after a green merge to `main`.

---

## `ci.yml` — test gate (on `push` + `pull_request`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test-api:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: agendai
          POSTGRES_PASSWORD: agendai
          POSTGRES_DB: agendai_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
    env:
      DATABASE_URL: postgres://agendai:agendai@localhost:5432/agendai_test
      NODE_ENV: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd api && npm ci && npm test

  test-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: cd agent && uv run pytest --tb=short
```

**Contract points**:
- `test-api` provides a **real Postgres** via the `services:` container; `DATABASE_URL`
  points at it (research D6). The service container does **not** speak SSL, so
  `connection.js` must use **conditional SSL** (off for the local/CI host) — see
  data-migration.md §2. The `DATABASE_URL` host is `localhost`, which disables SSL
  automatically; `PGSSLMODE=disable` is also honored as a fallback.
- Both jobs must pass; **branch protection on `main`** requires `test-api` + `test-agent`
  green (FR-009/FR-010, US3).
- A deliberately failing test ⇒ red ⇒ merge blocked (SC-003).

---

## `deploy.yml` — build + deploy (on merge to `main`)

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: []          # gated by branch protection requiring CI; optionally re-run tests here
    permissions:
      contents: read
      packages: write   # GHCR
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build & push agent (LangGraph Server)
        run: |
          pip install langgraph-cli
          cd agent && langgraph build -t ghcr.io/${{ github.repository_owner }}/agendai-agent:latest
          docker push ghcr.io/${{ github.repository_owner }}/agendai-agent:latest
      - name: Build & push api / nginx / agent-ui-pro
        run: |
          for svc in api nginx agent-ui-pro; do
            docker build -t ghcr.io/${{ github.repository_owner }}/agendai-$svc:latest ./$svc
            docker push ghcr.io/${{ github.repository_owner }}/agendai-$svc:latest
          done
      - name: Trigger Render deploy
        run: curl -fsSL -X POST "${{ secrets.RENDER_DEPLOY_HOOK }}"
```

**Contract points**:
- Agent image is produced by `langgraph build` (research D1); the others by `docker build`.
- Images pushed to **GHCR** under the repo owner namespace.
- Render is updated via a **deploy hook** secret (`RENDER_DEPLOY_HOOK`); the public URL then
  serves the new version (FR-012/FR-013, SC-004).
- `agent-ui-pro` build passes `NEXT_PUBLIC_*` as build args (public nginx URL, assistant id,
  key) — these are baked at image build time.

---

## Secrets (GitHub repo settings)

| Secret | Used by |
|---|---|
| `GITHUB_TOKEN` (built-in) | GHCR login/push |
| `RENDER_DEPLOY_HOOK` | trigger Render deploy |
| (Runtime app secrets live in **Render env vars**, not GitHub — see render-blueprint.md) |

The agent-ui-pro build args that are public (`NEXT_PUBLIC_*`) may be repo/Actions variables;
the token value is a secret.

---

## Acceptance

- Opening a PR runs `ci.yml`; a broken test blocks merge; fixing it unblocks (SC-003, SC-005).
- Merge to `main` runs `deploy.yml`, publishes images to GHCR, and triggers Render; the
  public URL reflects the new build with no manual steps (SC-004).
- README shows a green CI badge (FR-019).
