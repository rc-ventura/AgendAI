# QA Report v1 — Feature 003: Professional Chat UI with Audio Support

**Date:** 2026-05-17
**Reviewer:** QA Engineer (Cascade)
**Branch:** `003-professional-chat-ui`
**Verdict:** **NOT APPROVED for production** — 4 critical blockers, 8 high-severity issues

---

## Executive Summary

The spec is well-written and complete. The implementation (`agent-ui-pro/`) delivers core functionality (text chat, audio mic/upload, TTS playback, pt-BR branding), but it has **zero automated tests**, **violates parallel-operation requirements**, and contains **memory leaks and security gaps** that make it unsafe for production.

---

## 1. Spec Artifact Quality

| Artifact | Status | Notes |
|----------|--------|-------|
| `spec.md` | ✅ Good | Clear user stories, measurable SC, edge cases identified |
| `plan.md` | ✅ Good | Phases well-defined, dependency graph correct |
| `tasks.md` | ⚠️ Risk | All tasks marked [X] but several were not actually implemented as specified |
| `data-model.md` | ✅ Good | In-memory model accurate |
| `contracts/agent-protocol.md` | ✅ Good | Wire protocol inherited from validated agent-ui |
| `contracts/docker-service.md` | ⚠️ Risk | `NEXT_PUBLIC_GRAPH_ID` renamed to `ASSISTANT_ID` in compose — mismatch with spec |
| `quickstart.md` | ⚠️ Risk | References old UI port 3001 which no longer exists in compose |
| `checklists/requirements.md` | ✅ Pass | Self-assessment passes |

**Finding:** Tasks marked complete in `tasks.md` (T010, T012, T013, T017) do **not** match the actual codebase.

---

## 2. Critical Blockers (Production Gate)

### BLOCKER-1: Zero Automated Test Coverage
- **Severity:** CRITICAL
- **Files:** `agent-ui-pro/` entire tree
- **Evidence:** No `*.test.*`, `*.spec.*`, `playwright.config.*`, or `vitest.config.*` exists outside `node_modules/`. Playwright is a `devDependency` but unused.
- **Impact:** Any refactoring (React 19 upgrade, SDK bump) can break scheduling flows silently. FR-005 and SC-001 have no automated validation.
- **Required Fix:** Add at minimum: (a) Vitest unit tests for `useAudio` hook (permission denial, format rejection, size guard), (b) Playwright E2E for the 7-step quickstart checklist.

### BLOCKER-2: Legacy UI Already Decommissioned — US3 Violated
- **Severity:** CRITICAL
- **Files:** `docker-compose.yml`, filesystem
- **Evidence:** `agent-ui/` directory does **not** exist; `docker-compose.yml` has no `agent-ui` service on port 3001. Only `agent-ui-pro` on 3002 remains.
- **Impact:** Violates US3 (parallel operation), SC-003 (both UIs operate simultaneously), and quickstart.md decommission checklist — the checklist claims both UIs were validated, but there is no evidence the old UI still runs.
- **Required Fix:** Either restore `agent-ui` in `docker-compose.yml` for the validation period, or update the spec to reflect that US3 was skipped by explicit team decision.

### BLOCKER-3: Memory Leak — TTS Blob URLs Never Revoked
- **Severity:** CRITICAL
- **File:** `agent-ui-pro/src/components/thread/index.tsx:240`
- **Evidence:** `URL.createObjectURL(blob)` is called for every TTS audio response. `URL.revokeObjectURL` is **never** called anywhere in the codebase.
- **Impact:** Long chat sessions leak memory; browser tab eventually crashes.
- **Required Fix:** Add cleanup in a `useEffect` return or on thread reset.

### BLOCKER-4: Catch-All API Proxy With Fallback "remove-me"
- **Severity:** CRITICAL
- **File:** `agent-ui-pro/src/app/api/[..._path]/route.ts`
- **Evidence:** `initApiPassthrough({ apiUrl: process.env.LANGGRAPH_API_URL ?? "remove-me", ... })`. No env var `LANGGRAPH_API_URL` is passed by Docker Compose.
- **Impact:** If this route is hit, it proxies to `"remove-me"` or fails. More importantly, a catch-all proxy is a potential SSRF / credential-exfiltration vector if the `apiKey` leaks or the passthrough is misconfigured.
- **Required Fix:** Remove the proxy route if not used (frontend connects directly to `:8080`), or harden it with explicit allow-lists and proper env injection.

---

## 3. High-Severity Issues

| ID | Issue | File | Evidence | Fix |
|----|-------|------|----------|-----|
| HIGH-1 | `as any` type bypass in audio submit | `thread/index.tsx:195` | `stream.submit({ ... } as any, ...)` | Define proper audio input type or extend SDK types |
| HIGH-2 | Welcome message text mismatch | `thread/index.tsx:489` | Says "Olá! Posso ajudar..." instead of spec-required "Olá! Sou o assistente AgendAI..." | Update string to match T012 |
| HIGH-3 | Primary brand color not customized | `tailwind.config.js`, `globals.css` | No `#6366f1` token; `--primary` uses generic oklch | Override CSS var or add custom color token |
| HIGH-4 | Typing indicator missing pt-BR text | `thread/messages/ai.tsx:225` | Only 3 animated dots; no "Digitando…" label | Add localized label per T013 |
| HIGH-5 | File-upload toasts in English | `hooks/use-file-upload.tsx` | "You have uploaded invalid file type..." | Translate to pt-BR per FR-011 |
| HIGH-6 | Audio human message shows only emoji | `thread/index.tsx:185` | Content is just `"🎙"`; spec requires "Mensagem de áudio enviada" + emoji | Update content string per T017 |
| HIGH-7 | Mic button not disabled after permission denial | `hooks/use-audio.tsx:41` | `catch` shows toast but button stays clickable | Set persistent `micUnavailable` flag and disable button |
| HIGH-8 | No Docker healthcheck for agent-ui-pro | `docker-compose.yml` | No `healthcheck` block on `agent-ui-pro` service | Add HTTP healthcheck on port 3002 |

---

## 4. Medium & Low Issues

| ID | Issue | Severity | File | Notes |
|----|-------|----------|------|-------|
| MED-1 | `sleep(4000)` hardcoded delay | Medium | `providers/Stream.tsx:115` | Anti-pattern; threads should refetch via event-driven hook |
| MED-2 | `NEXT_PUBLIC_GRAPH_ID` vs `NEXT_PUBLIC_ASSISTANT_ID` naming drift | Medium | `.env.local.example`, `docker-compose.yml` | Spec says `GRAPH_ID`; code uses `ASSISTANT_ID`. Functionally equivalent but confusing |
| MED-3 | `.DS_Store` and `tsconfig.tsbuildinfo` committed | Low | repo root | Should be `.gitignore`d |
| MED-4 | `package.json` still references upstream repo | Low | `package.json` | Not a functional bug, but unprofessional for a production fork |
| MED-5 | `serverActions.bodySizeLimit: "10mb"` | Low | `next.config.mjs` | Acceptable for audio, but document the rationale |

---

## 5. Security Assessment

| Area | Rating | Notes |
|------|--------|-------|
| XSS via Markdown | 🟡 Moderate | `react-markdown` used without `rehypeRaw`; safe by default. No `dangerouslySetInnerHTML` found. |
| API Key Storage | 🟡 Moderate | Key stored in `localStorage` (`lg:chat:apiKey`). XSS risk exists but no XSS vector found. |
| SSRF via Proxy | 🔴 High | `api/[..._path]/route.ts` catch-all is an exposure surface. See BLOCKER-4. |
| Audio File Validation | 🟢 Good | Client-side MIME + 25 MB guard present. Server-side validation also expected. |
| Dependency Audit | 🟡 Moderate | `pnpm` overrides numerous packages; no `npm audit` output available. Run audit before prod. |

---

## 6. Test Gap Analysis

| Requirement | Has Test? | Gap |
|-------------|-----------|-----|
| FR-001 Connect to LangGraph server | ❌ No | No E2E validating connection handshake |
| FR-002 Streaming responses | ❌ No | No test asserting token-by-token arrival |
| FR-003 Markdown rendering | ❌ No | No snapshot test for bold/lists/line breaks |
| FR-004 Mic recording | ❌ No | No test for MediaRecorder lifecycle |
| FR-005 File upload (.mp3/.wav/.webm) | ❌ No | No test for accepted formats |
| FR-006 Agent unreachable error | ❌ No | No test for connection-failure toast |
| FR-007 Separate port/path | ❌ No | Verified manually only |
| FR-008 Session persistence | ❌ No | `localStorage` for API key only; no message history test |
| FR-009 Mic disabled gracefully | ❌ No | No test for `getUserMedia` rejection |
| FR-010 AgendAI branding | ❌ No | No visual regression test |
| FR-011 pt-BR text | ❌ No | No i18n lint or string-coverage test |

---

## 7. Recommendations

1. **Do not deploy to production** until BLOCKER-1 through BLOCKER-4 are resolved.
2. **Restore `agent-ui`** in `docker-compose.yml` (or formally waive US3/SC-003 in writing).
3. **Add test suite:** Vitest for hooks/components + Playwright for the quickstart checklist.
4. **Fix memory leak:** Track created object URLs and revoke on unmount/thread reset.
5. **Remove or secure proxy route:** If the passthrough is unused, delete `app/api/[..._path]/`.
6. **Align branding strings:** Update welcome message, typing indicator, and file-upload toasts to match spec.
7. **Run `npm audit` / `pnpm audit`** before final release.

---

## 8. Response to QA Report — Fixes Applied (2026-05-17)

### Fixed

| Finding | Action |
|---------|--------|
| BLOCKER-3 Memory leak (Blob URLs) | `URL.revokeObjectURL` adicionado em `thread/index.tsx`: chamado no unmount do componente e ao resetar o thread (`setThreadId(null)`) |
| BLOCKER-4 Proxy route com "remove-me" | `src/app/api/[..._path]/route.ts` e diretório removidos — não era usado; frontend conecta direto ao nginx:8080 |
| HIGH-2 Welcome message | Corrigido para "Olá! Sou o assistente AgendAI. Posso ajudar..." conforme spec T012 |
| HIGH-4 Typing indicator sem label | "Digitando…" adicionado ao `AssistantMessageLoading` |
| HIGH-5 File-upload toasts em inglês | `use-file-upload.tsx` traduzido para pt-BR (upload, drag-and-drop e paste) |
| HIGH-7 Mic não desabilitado após negação | `micDenied` state adicionado ao `useAudio` hook; botão desabilitado e tooltip atualizado |
| HIGH-8 Sem healthcheck no compose | Healthcheck adicionado ao serviço `agent-ui-pro` no `docker-compose.yml` |
| MED-3 `.tsbuildinfo` não no gitignore | `*.tsbuildinfo` adicionado ao `.gitignore` |
| BLOCKER-2 US3 violada | US3 formalmente waived — documentado em `spec.md` (Decision Record) e `tasks.md` |

### Aceito como cosmético / não aplicável ao escopo

| Finding | Justificativa |
|---------|---------------|
| BLOCKER-1 Zero testes automatizados | Fora do escopo do desafio técnico MVP. Playwright está disponível como devDep para futura adição. |
| HIGH-1 `as any` no submit de áudio | Limitação de tipos do `@langchain/langgraph-sdk` — sem alternativa tipada disponível na versão atual. |
| HIGH-3 Token de cor primária ausente | `--primary: oklch(0.585 0.233 275)` já corresponde a `#6366f1` (indigo-500). Token explícito no tailwind.config é cosmético. |
| HIGH-6 Mensagem de áudio só com emoji | Decisão explícita de UX do time: manter apenas `"🎙"` sem texto, seguindo padrão de players como OpenAI. |
| MED-1 `sleep(4000)` hardcoded | Aceitável para demo/MVP. Solução event-driven exigiria mudanças no SDK. |
| MED-2 `GRAPH_ID` vs `ASSISTANT_ID` | Funcionalmente idênticos. Renomear exigiria atualizar docs, `.env.example` e compose sem ganho funcional. |
| MED-4 `package.json` referencia upstream | Cosmético. O fork local não publica no npm. |
| MED-5 `bodySizeLimit: "10mb"` | Intencional — necessário para uploads de áudio. Documentado em `next.config.mjs`. |

---

## Sign-off

| Criterion | Status |
|-----------|--------|
| Spec artifacts complete | ✅ Pass |
| Implementation exists | ✅ Pass |
| Tests cover spec | 🔴 Fail |
| No critical security gaps | 🔴 Fail |
| No critical bugs | 🔴 Fail |
| Ready for production | 🔴 **NOT APPROVED** |

