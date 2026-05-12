<!--
SYNC IMPACT REPORT
==================
Version change: (unversioned template) → 1.0.0
Modified principles: N/A (initial authoring)
Added sections:
  - Core Principles (I–V)
  - Technology & Integration Constraints
  - Development Workflow
  - Governance
Templates checked:
  - .specify/templates/plan-template.md ✅ (Constitution Check gate already present; no changes needed)
  - .specify/templates/spec-template.md ✅ (structure compatible; no changes needed)
  - .specify/templates/tasks-template.md ✅ (test discipline & observability tasks already included as optional; aligned)
Deferred TODOs:
  - None — all fields resolved from project context or today's date (2026-05-12).
-->

# AgendAI Constitution

## Core Principles

### I. AI-Assisted by Default

Every scheduling and agenda feature MUST leverage the Claude AI integration as its primary
intelligence layer. AI interactions MUST be predictable, deterministic for testing, and
observable through structured logging. Fallback behavior when AI is unavailable MUST be
explicitly designed — silent degradation is not acceptable. Prompts and model interactions
MUST be versioned alongside application code.

### II. User-Centric Scheduling

The system MUST prioritize clarity and minimal friction in all scheduling workflows.
Every user-facing interaction MUST be reachable within three actions from the main screen.
Features MUST be independently testable as standalone user journeys (see spec template).
Accessibility (WCAG 2.1 AA at minimum) is NON-NEGOTIABLE for any UI surface.

### III. Test-First (NON-NEGOTIABLE)

TDD is mandatory: tests MUST be written and reviewed by the developer before implementation
begins. The Red-Green-Refactor cycle is strictly enforced. No production code may exist
without a corresponding failing test that justified its creation. AI prompt logic MUST have
contract tests that verify response structure and boundary behavior.

### IV. Observability & Reliability

All AI interactions and scheduling operations MUST emit structured logs (JSON) with a
correlation ID, timestamp, operation name, and outcome. Errors MUST be surfaced with
actionable messages — stack traces are for logs, not users. The system MUST degrade
gracefully: if the AI service is unavailable, core scheduling MUST still function.
P95 latency for any user-initiated action MUST remain under 2 seconds.

### V. Simplicity & Maintainability

YAGNI strictly applies: implement only what the current user story requires. Abstractions
MUST be justified by eliminating actual duplication (three or more concrete instances),
not anticipated future need. Cyclomatic complexity per function MUST stay ≤ 10. Prefer
flat data structures; introduce nesting only when it maps directly to a domain concept.

## Technology & Integration Constraints

- **AI Runtime**: Claude API (Anthropic SDK) — model selection MUST use the latest stable
  Sonnet or Opus model; hard-coding deprecated model IDs is prohibited.
- **Prompt Caching**: All frequently reused system prompts MUST use Anthropic prompt caching
  to minimize cost and latency.
- **Language / Runtime**: TypeScript (Node.js ≥ 20) or Python ≥ 3.11 — decision to be
  finalised in the first feature's plan.md.
- **Storage**: Technology TBD per feature plan; any persistence layer MUST support
  offline-capable reads for calendar data.
- **Security**: API keys and secrets MUST never appear in source code or logs. Use
  environment variables and a secrets manager in production.

## Development Workflow

- All work MUST begin on a feature branch created via `/speckit-git-feature`; direct
  commits to `main` are prohibited.
- A passing spec (`spec.md`), plan (`plan.md`), and task list (`tasks.md`) MUST exist
  before implementation begins on any feature.
- Pull requests require at least one peer review and all automated checks passing before
  merge.
- Each PR description MUST include a "Constitution Check" section confirming compliance
  with Principles I–V, or documenting any justified exception (see Complexity Tracking
  in plan-template.md).
- Releases MUST be tagged with semantic versions; CHANGELOG entries are mandatory for
  every user-visible change.

## Governance

This constitution supersedes all other development practices. Amendments require:

1. A proposal describing the change and motivation.
2. Review and approval by at least one other contributor (or self-review with written
   rationale for solo projects).
3. A migration plan for any existing features affected by the change.
4. Version bump following semantic versioning rules (see below).

**Versioning policy**:
- MAJOR: Removal or backward-incompatible redefinition of a principle.
- MINOR: New principle, new mandatory section, or materially expanded guidance.
- PATCH: Clarifications, wording fixes, or non-semantic refinements.

All PRs and code reviews MUST verify compliance with this constitution. Unjustified
complexity MUST be flagged and resolved before merge, not deferred.

**Version**: 1.0.0 | **Ratified**: 2026-05-12 | **Last Amended**: 2026-05-12
