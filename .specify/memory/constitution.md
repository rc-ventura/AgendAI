<!--
SYNC IMPACT REPORT
==================
Latest change: 1.0.0 → 1.1.0 (2026-06-01)
Bump rationale (MINOR): Added a new first-class principle (VI. Security & Data Protection)
and clarified the name of Principle II to surface that it already mandates TDD. No principle
was removed or redefined incompatibly, so this is a MINOR bump.

This amendment:
  - RENAMED  Principle II: "Test-First with Real DB" → "Test-First (TDD) with Real DB"
             (name-only clarification; the body already mandated the red-green cycle).
  - ADDED    Principle VI: Security & Data Protection (PII protection, single trusted
             boundary, fail-closed auth, least exposure, secrets, input validation, deps).

History:
  - 1.0.0 (2026-06-01): First formal ratification. Converted the placeholder template into
    the adopted constitution, codifying the five de-facto principles referenced by the
    Constitution Check sections of features 003 and 004.

Principles (current set):
  I.   Layered Architecture
  II.  Test-First (TDD) with Real DB (NON-NEGOTIABLE)
  III. Stateless Services via Dependency Injection
  IV.  Observability & Cache Consistency
  V.   Simplicity & Minimal Abstraction
  VI.  Security & Data Protection

Sections: Technology & Architecture Constraints; Development Workflow & Quality Gates;
Governance (all filled; no template placeholders remain).

Templates / artifacts reviewed for consistency:
  ✅ .specify/templates/plan-template.md  — "Constitution Check" gate references the
       constitution generically; it now covers 6 principles automatically; no edit needed.
  ✅ .specify/templates/spec-template.md  — no mandatory section added/removed; no edit.
  ✅ .specify/templates/tasks-template.md — task categories accommodate security/testing/
       observability tasks; no edit needed.
  ✅ specs/004-fase-1-deploy/plan.md       — Constitution Check updated to add a Security
       row (already compliant: single public edge, fail-closed auth, secrets externalized).
  ✅ specs/003-professional-chat-ui/plan.md — pre-existing table reflects v1.0.0 principle
       names; acceptable as a historical record (frontend-only feature, security N/A).

Deferred / TODO: none. RATIFICATION_DATE unchanged (2026-06-01).
-->

# AgendAI Constitution

AgendAI is a medical scheduling automation system built from four independent components: a
REST API (Node.js 20 + Express), a LangGraph agent (Python 3.11), a professional chat UI
(Next.js 14), and an nginx gateway. This constitution defines the non-negotiable engineering
principles that govern how those components are designed, tested, and shipped.

## Core Principles

### I. Layered Architecture

The REST API MUST preserve a strict, one-directional layering:
`routes → controllers → services → repositories → datastore`.

- Each layer MUST only call the layer directly beneath it. Controllers MUST NOT touch the
  datastore; repositories MUST NOT contain business rules; routes MUST only wire dependencies
  and map paths.
- Business logic lives in **services**; data access lives in **repositories**; HTTP concerns
  (status codes, request/response shaping, validation entry) live in **controllers/routes**.
- New cross-cutting concerns MUST be introduced as middleware or a dedicated module, never by
  leaking responsibilities across layers.

**Rationale**: The layering is the project's primary defense against coupling. It is what
made the SQLite→Postgres migration a mechanical, test-guarded change confined to the
repository/connection layers rather than a rewrite.

### II. Test-First (TDD) with Real DB (NON-NEGOTIABLE)

Automated tests are the gate for every change.

- The data layer MUST be exercised against a **real database engine** — never a mock or stub
  of the datastore. (Tests run against real Postgres; the API test suite drops + seeds a
  dedicated database per test.)
- A change MUST keep the existing suites green. New behavior MUST ship with tests that fail
  before the implementation and pass after.
- CI MUST run the full API (Jest) and agent (pytest) suites on every pull request, and a
  failing suite MUST block merge to `main`.

**Rationale**: Real-DB testing catches dialect, transaction, and concurrency bugs that mocks
hide (e.g., the atomic double-booking guard). Tests-as-gate is what makes continuous
deployment safe.

### III. Stateless Services via Dependency Injection

Application components MUST receive their dependencies explicitly and hold no hidden state.

- The API app and its services MUST be constructed via factory functions that take their
  dependencies as arguments (`createApp(pool)`, `createXService(deps)`), enabling test
  injection of an isolated database.
- Containers (API, agent, UI, nginx) MUST be **stateless**. All durable state MUST live in
  external, managed backing services (Postgres, Redis), per twelve-factor — never on a
  container's local filesystem in production.
- Module-level singletons are permitted only for stateless utilities (e.g., the cache client,
  the connection pool) and MUST be resettable/injectable for tests.

**Rationale**: Statelessness enables horizontal scaling, zero-downtime redeploys, and
deterministic tests. It is the precondition for the managed-state production architecture.

### IV. Observability & Cache Consistency

The system MUST be debuggable in production and never serve stale or raw output.

- Any write that affects a cached read MUST invalidate the affected cache entries **after**
  the write commits (e.g., availability cache invalidated on booking/cancellation).
- Agent interactions MUST be traceable (LangSmith traces, including tool calls) when
  observability is configured.
- Errors surfaced to users MUST be clear, user-facing messages in pt-BR — never a raw stack
  trace or internal detail. Server misconfiguration (e.g., a missing required secret) MUST
  fail fast with a diagnostic, not degrade silently.

**Rationale**: Cache-after-commit prevents stale availability; tracing and fail-fast behavior
turn production incidents into diagnosable events rather than mysteries.

### V. Simplicity & Minimal Abstraction

Prefer the simplest thing that works; justify every abstraction.

- Prefer official/managed components over hand-rolled equivalents (e.g., the official
  LangGraph Server image for persistence/streaming; nginx as the gateway).
- Prefer raw, parametrized SQL over an ORM/query builder, matching the existing repository
  style. Reuse existing patterns verbatim before inventing new ones.
- Any new abstraction, extra service, or deviation from these principles MUST be recorded and
  justified in the plan's **Complexity Tracking** table.

**Rationale**: YAGNI keeps the four-component system understandable and the diffs reviewable.
Unjustified abstraction is treated as a defect.

### VI. Security & Data Protection

AgendAI stores patient PII (names, emails, phone numbers, appointments); protecting it is a
primary design constraint, not an afterthought.

- **Single trusted boundary**: all public traffic MUST enter only through the gateway; the
  API and agent MUST run as private services with no public route. The gateway MUST enforce
  authentication and rate limiting and **fail closed** — a missing or misconfigured auth
  token MUST reject the request, never allow it.
- **Least exposure**: responses and logs MUST NOT leak secrets, internal stack traces, or PII
  beyond what the requesting user is entitled to. User-facing errors are pt-BR messages only.
- **Secrets**: MUST be supplied at runtime/CI from a secret store, MUST NEVER be committed,
  and their absence MUST fail fast with a diagnostic.
- **Input validation**: validation at the API boundary is mandatory. Untrusted input that
  drives the agent MUST be validated/guarded before it is acted upon (input guardrails are a
  planned hardening item and MUST land before the system processes unmoderated public input
  at scale).
- **Dependencies**: known-vulnerable dependencies MUST be remediated before reaching `main`.

**Rationale**: A medical scheduling assistant is an attractive target and a privacy liability
if mishandled. Fail-closed auth, a single audited entry point, and disciplined secret/PII
handling are the minimum bar for handling patient data responsibly.

## Technology & Architecture Constraints

- **Components & stacks** (MUST remain the canonical stack unless amended):
  - REST API: Node.js 20 + Express 4.
  - Agent: Python 3.11 + LangGraph (v1.0+); the compiled graph MUST NOT embed environment- or
    deployment-specific persistence wiring (persistence is provided by the runtime/server).
  - Chat UI: Next.js 14 + `@langchain/langgraph-sdk`.
  - Gateway: nginx as the single public entry point (auth, rate limiting, SSE).
- **Datastore**: PostgreSQL is the production datastore; it MUST be a managed service in
  production (no database in an application container on ephemeral filesystems).
- **Public surface**: Only the gateway is publicly reachable in production; the API and agent
  run as private services.
- **Secrets**: MUST be supplied at runtime/CI from a secret store (Render env vars / GitHub
  Secrets) and MUST NEVER be committed. `.env` stays gitignored; `.env.example` documents all
  required keys without values.

## Development Workflow & Quality Gates

- **Spec-Kit flow**: Features proceed through `/speckit-specify → /speckit-plan →
  /speckit-tasks → /speckit-analyze → /speckit-implement`. Each `plan.md` MUST include a
  Constitution Check that evaluates all five principles before and after design.
- **CI as deploy gate**: Merges to `main` require the full API + agent suites green (branch
  protection enforced). Deployment to production happens only from a passing `main`.
- **Review**: Changes land via pull request. Reviewers MUST verify constitution compliance and
  that any complexity is justified in the plan.
- **Documentation**: `CLAUDE.md` and `README.md` MUST stay consistent with the deployed
  architecture (stack, topology, environment variables).

## Governance

- This constitution supersedes ad-hoc practices. Where a plan or task conflicts with a
  principle, the principle wins; the plan/spec/tasks MUST be adjusted rather than the
  principle diluted or silently ignored.
- **Amendments** MUST be made by editing this file in a pull request, accompanied by a version
  bump and an updated Sync Impact Report. Amending a principle's meaning is not permitted
  inside `/speckit-analyze` or other downstream commands — it requires an explicit
  `/speckit-constitution` change.
- **Versioning** follows semantic versioning:
  - MAJOR: backward-incompatible governance changes or principle removals/redefinitions.
  - MINOR: a new principle/section or materially expanded guidance.
  - PATCH: clarifications and non-semantic refinements.
- **Compliance** is verified at planning time (the plan's Constitution Check) and at review
  time (PR review). Repeated, unjustified deviations are treated as defects to be remediated.

**Version**: 1.1.0 | **Ratified**: 2026-06-01 | **Last Amended**: 2026-06-01
