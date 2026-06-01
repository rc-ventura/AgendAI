# Feature Specification: Phase 1 — Production Deploy (Public URL, Managed State, CI Gate)

**Feature Branch**: `004-fase-1-deploy`

**Created**: 2026-06-01

**Status**: Draft

**Input**: User description: "Fase 1: Render + GitHub Actions (Production Deploy). Put AgendAI online with a public URL, managed database, persistent agent state, and automated tests as a deploy gate — turning the local docker-compose demo into a production-grade, portfolio-ready system. Decisions already closed: (1) run the agent on the official managed LangGraph Server image; (2) keep nginx as the single public entry point; (3) migrate from file-based SQLite to a managed Postgres database; (4) defer the LLM Gateway to a later phase."

## Why This Feature Exists

Today AgendAI only runs on a developer's machine via `docker compose up`. There is
no public URL, the database is a local file that disappears when the volume is
wiped, the chat agent forgets every conversation when its process restarts (state
held only in memory), and nothing automatically verifies that a change is safe
before it ships. This makes the project impossible to share, demo reliably, or
present as production-grade work.

Phase 1 closes those gaps: a reachable public address, a managed database whose
data survives restarts, conversation history that persists across agent restarts,
and an automated test gate that blocks broken code from being deployed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reach AgendAI at a Public URL (Priority: P1)

A prospective patient (or a portfolio reviewer) opens a single public web address
in their browser and uses the AgendAI chat to schedule a medical appointment end to
end — text and audio — exactly as they could locally, but now from anywhere, over a
secure connection, without anyone running a local server.

**Why this priority**: A reachable, working public URL is the headline outcome of
Phase 1. Without it, none of the other improvements are observable or shareable.
Every other story exists to make this one trustworthy.

**Independent Test**: From a machine that has never run the project, open the public
URL, complete a full scheduling conversation (including an audio message), and
confirm the appointment is created and a confirmation is shown.

**Acceptance Scenarios**:

1. **Given** the system is deployed, **When** a visitor opens the public URL,
   **Then** the professional chat interface loads over HTTPS with no setup required.
2. **Given** the chat is open, **When** the visitor sends a text scheduling request,
   **Then** the agent streams a reply in real time and the scheduling flow completes.
3. **Given** the chat is open, **When** the visitor sends an audio message,
   **Then** it is transcribed, answered, and (when applicable) the agent replies with
   audio — matching the local experience.
4. **Given** the visitor completes a booking, **When** the agent confirms it,
   **Then** the appointment is persisted and a confirmation email is sent (when email
   is configured).

---

### User Story 2 - Conversations and Data Survive Restarts (Priority: P1)

A patient returns to an in-progress conversation after the backend has been
redeployed or restarted, and the conversation history is still there. Likewise,
appointments and patient records created yesterday are still present today — the
data is no longer tied to an ephemeral local file.

**Why this priority**: Persistence is what separates a demo from a real service. An
agent that forgets every conversation on restart, or a database that resets on
redeploy, cannot be trusted in production. This directly resolves the two core
state gaps (in-memory agent state and file-based database).

**Independent Test**: Start a conversation and create an appointment; restart the
backend services; reopen the same conversation thread and re-query the appointment —
both must still exist.

**Acceptance Scenarios**:

1. **Given** an active conversation thread, **When** the agent backend is restarted,
   **Then** reopening that thread shows the prior messages intact.
2. **Given** appointments exist in the database, **When** the services are redeployed,
   **Then** those appointments are still retrievable (no data reset).
3. **Given** a fresh deployment with an empty database, **When** the system starts,
   **Then** the schema is created and baseline reference data is seeded exactly once
   (not duplicated on subsequent restarts).

---

### User Story 3 - Broken Changes Cannot Be Deployed (Priority: P1)

The project owner opens a change for review. The full automated test suite runs
against the proposed change. If any test fails, the change is blocked from reaching
the production branch and cannot be deployed. When the tests pass, the change merges
and the running system is updated automatically.

**Why this priority**: An automated test gate is what makes continuous deployment
safe. Without it, a regression can silently reach the public URL. This is the
"tests as a deploy gate" promise of Phase 1 and a key portfolio signal.

**Independent Test**: Open a change that deliberately breaks a test and confirm the
gate blocks the merge; fix the test and confirm the gate goes green and the change
becomes mergeable.

**Acceptance Scenarios**:

1. **Given** a proposed change, **When** it is submitted for review, **Then** the
   complete backend and agent test suites run automatically against a real database.
2. **Given** a proposed change with a failing test, **When** the suite runs, **Then**
   the change is reported as failing and is blocked from merging to the production
   branch.
3. **Given** a change whose tests pass, **When** it is merged to the production
   branch, **Then** the deployment updates automatically without manual steps.
4. **Given** a deployment is triggered, **When** it completes, **Then** the public
   URL reflects the new version.

---

### User Story 4 - Single Secure Public Entry Point (Priority: P2)

All public traffic enters through one gateway. The chat interface, the agent
backend, and the internal scheduling service are reachable only through that single
entry point — the backend services are not directly exposed to the internet. The
gateway enforces authentication, rate limiting, and streaming.

**Why this priority**: Reducing the public surface to a single, controlled entry
point is a baseline production security posture and simplifies operations. It builds
on the existing gateway rather than introducing a new pattern.

**Independent Test**: Confirm the public URL serves both the UI and the agent
endpoints; confirm the backend services have no public address of their own and
cannot be reached directly from the internet.

**Acceptance Scenarios**:

1. **Given** the deployment, **When** a client requests the UI or the agent endpoints
   through the public URL, **Then** both are served from the same origin.
2. **Given** the deployment, **When** a client attempts to reach a backend service
   directly, **Then** there is no public route to it.
3. **Given** the gateway, **When** real-time streaming responses are requested,
   **Then** they stream without buffering or interruption.
4. **Given** the gateway, **When** unauthenticated or excessive requests hit the agent
   endpoints, **Then** they are rejected or throttled per the configured policy.

---

### User Story 5 - Observable Production Behavior (Priority: P3)

The project owner can see traces of real conversations — what the agent did, which
tools it called, latency — in an observability dashboard, to debug issues and to
showcase the system's internals.

**Why this priority**: Observability turns production into something you can reason
about and present. It is valuable but not required for the system to function, hence
lower priority than availability, persistence, and the test gate.

**Independent Test**: Complete a conversation on the public URL and confirm a
corresponding trace (with tool calls) appears in the observability dashboard.

**Acceptance Scenarios**:

1. **Given** observability is configured, **When** a conversation runs in production,
   **Then** a trace including the agent's tool calls is recorded and viewable.

---

### Edge Cases

- **Managed database unreachable at startup**: the affected service MUST fail clearly
  with a diagnostic message rather than start in a broken state or silently fall back
  to local storage.
- **Secret missing or invalid in production**: the system MUST fail fast with a clear
  indication of which credential is missing, not leak partial functionality.
- **Free-tier limit reached** (e.g., database, cache, or hosting quota): degraded
  behavior MUST be observable and attributable, not a silent failure.
- **Deploy triggered while a previous deploy is in flight**: deployments MUST not
  corrupt the running system; the latest successful build wins.
- **Schema/seed run against a database that already has data**: startup MUST be
  idempotent — no duplicate seed rows, no destructive re-creation of existing data.
- **Test run against a shared/dirty database**: tests MUST isolate their own state so
  results are deterministic regardless of prior runs.
- **Loss of same-origin assumption** (UI and agent served from different origins):
  cross-origin requests MUST still be handled correctly or explicitly prevented.

## Requirements *(mandatory)*

### Functional Requirements

#### Public Availability

- **FR-001**: The system MUST be reachable at a stable public URL over HTTPS without
  any local setup by the visitor.
- **FR-002**: The public URL MUST serve the chat interface and the agent endpoints
  from a single origin (same-origin), through one public entry point.
- **FR-003**: The agent backend and the internal scheduling service MUST NOT be
  directly reachable from the public internet; only the gateway may reach them.
- **FR-004**: The gateway MUST continue to enforce authentication, rate limiting, and
  unbuffered real-time streaming for agent traffic.

#### Persistence

- **FR-005**: Appointment, patient, doctor, time-slot, and payment data MUST be stored
  in a managed database whose contents survive service restarts and redeployments.
- **FR-006**: Conversation/thread state MUST persist across restarts of the agent
  backend, so a returning user sees prior messages.
- **FR-007**: On startup, the system MUST create required database structures if absent
  and seed baseline reference data exactly once, without duplicating data on repeated
  startups.
- **FR-008**: The scheduling service's data behavior (availability lookups, booking,
  cancellation, and the associated cache invalidation) MUST remain functionally
  equivalent to the pre-migration behavior.

#### Test Gate & Deployment

- **FR-009**: Every proposed change MUST automatically run the complete backend and
  agent test suites before it can be merged to the production branch.
- **FR-010**: A change with any failing test MUST be blocked from merging to the
  production branch.
- **FR-011**: Backend tests MUST run against a real instance of the production-class
  database engine (not an in-memory or file-based substitute), with each test
  isolating its own data so runs are deterministic.
- **FR-012**: Merging a passing change to the production branch MUST automatically
  build the deployable artifacts and update the running production system without
  manual intervention.
- **FR-013**: The deployment MUST result in the public URL serving the new version.

#### Configuration & Secrets

- **FR-014**: All credentials and environment-specific configuration MUST be supplied
  at runtime/CI from a secret store, never committed to the repository.
- **FR-015**: The repository MUST exclude secret files from version control and MUST
  provide an up-to-date example of all required configuration keys (without values).
- **FR-016**: A missing or invalid required secret MUST cause the affected service to
  fail fast with a clear diagnostic rather than start in a degraded state.

#### Local Parity

- **FR-017**: A single command MUST still bring up the full system locally for
  development, with local stand-ins for the managed dependencies, preserving
  developer parity with production.

#### Observability & Documentation

- **FR-018**: When observability is configured, production conversations MUST produce
  viewable traces that include the agent's tool calls.
- **FR-019**: Project documentation MUST present the production URL, the current
  build/test status, and a record of the architectural decisions made for this phase.

### Key Entities *(include if feature involves data)*

- **Appointment**: A booking linking a patient, a doctor, and a time slot; central
  domain record that MUST persist durably.
- **Patient / Doctor / Time Slot / Payment**: Supporting scheduling records that move
  from the local file store to the managed database with equivalent relationships.
- **Conversation Thread**: The persisted state of a chat session (its message history
  and checkpoints) that MUST survive agent restarts.
- **Deployable Artifact**: A versioned, built package of a service that is produced on
  a passing change and promoted to production.
- **Secret / Configuration Value**: A named credential or setting injected at runtime,
  managed outside the codebase.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor with only the public URL can complete a full
  scheduling conversation (text and audio) end to end, with no local setup.
- **SC-002**: After a backend restart or redeploy, 100% of previously created
  appointments remain retrievable and an in-progress conversation thread still shows
  its prior messages.
- **SC-003**: A change containing a failing test is blocked from reaching the
  production branch 100% of the time; a change with passing tests can merge.
- **SC-004**: A merge to the production branch results in the public URL serving the
  new version with no manual deployment steps.
- **SC-005**: The complete automated suite (all backend and agent tests) runs on every
  proposed change and passes before deployment.
- **SC-006**: No secret value is present anywhere in the repository history added by
  this feature; every required configuration key is documented by example.
- **SC-007**: Backend services have zero direct public network routes; all public
  access is via the single gateway, verified by attempting direct access.
- **SC-008**: A production conversation produces a viewable trace including tool calls.
- **SC-009**: The single local startup command still brings up a working end-to-end
  system, preserving developer parity.

## Assumptions

- Required third-party accounts and credentials (managed hosting, managed Postgres
  with two logical databases — one for application data and one for agent state —
  managed Redis, the agent platform license/tracing keys, a container registry, and
  the existing model-provider key) are obtained before execution; all are expected to
  fit within free tiers for this phase.
- The agent's graph definition does not need behavioral changes; persistence is
  provided by running it on the managed agent-server image, which supplies the
  database-backed checkpointer and streaming infrastructure.
- The existing gateway is retained and evolved into the single public reverse proxy;
  it is not replaced.
- Migrating the data layer from the synchronous file-based store to the managed
  Postgres engine is part of this phase and is the largest single effort.
- The professional chat UI from the prior phase is the interface served in
  production; it is reconfigured to operate same-origin behind the gateway.
- The expected test counts are the current suites (backend and agent); the gate runs
  whatever the suites contain at deploy time.
- The following are explicitly **out of scope** for Phase 1 (deferred to later
  phases): infrastructure-as-code on other clouds; managed guardrails / PII controls /
  spend caps via an LLM gateway; advanced agent resilience (circuit breakers, input
  guardrails, structured logging with correlation IDs).
