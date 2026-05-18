# Feature Specification: Professional Chat UI with Audio Support

**Feature Branch**: `003-professional-chat-ui`

**Created**: 2026-05-16

**Status**: Accepted — US3 (parallel operation) formally waived; see Decision Record below

**Input**: User description: "Build a professional chat UI using the LangChain agent-chat-ui (ready-made interface), adding audio upload and microphone support. Run as a second interface alongside the existing agent-ui, then progressively replace it. Connect directly to the existing LangGraph dev server. Rapid prototype delivery."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Professional Chat with Scheduling Agent (Priority: P1)

A patient opens the new professional chat interface and converses in text with
the AgendAI scheduling agent. The interface feels polished and production-ready —
not a developer prototype — and delivers the same scheduling capabilities as today
but with a trustworthy visual experience that instills confidence in the patient.

**Why this priority**: The primary value delivered is a professional visual identity
for the chat interaction. Text chat is already functional; elevating the UI is the
core goal and is required before any audio extension is useful.

**Independent Test**: Navigate to the new UI URL, start a conversation asking to
schedule a medical appointment, complete the full scheduling flow, and confirm that
a confirmation appears — all without touching the existing agent-ui.

**Acceptance Scenarios**:

1. **Given** a patient opens the new chat URL, **When** the page loads, **Then** a
   professional chat interface appears with the AgendAI branding, an input field,
   and a send button — no raw JSON or debug output visible.
2. **Given** a patient types a scheduling request, **When** they submit it, **Then**
   the agent replies in real time (streamed), and the reply is rendered as formatted
   text (not raw markdown).
3. **Given** a patient completes a scheduling flow, **When** the agent confirms the
   appointment, **Then** the confirmation is clearly displayed and the conversation
   history remains accessible in the same session.

---

### User Story 2 - Audio Input via Microphone or File Upload (Priority: P2)

A patient can send an audio message to the scheduling agent either by recording
directly in the browser via the microphone or by uploading an audio file. The agent
processes the audio and replies as it does for text messages. This mirrors the audio
capability already present in the existing agent-ui.

**Why this priority**: Audio input differentiates AgendAI for patients who prefer
voice interaction or are less comfortable typing. It is the primary feature gap
between the existing simple UI and the new professional one.

**Independent Test**: Open the new UI, click the microphone icon, record a short
scheduling request, submit it, and receive a text reply from the agent — or
alternatively upload an audio file and observe the same flow.

**Acceptance Scenarios**:

1. **Given** a patient is on the new chat interface, **When** they click the
   microphone button, **Then** the browser requests microphone permission and
   begins recording with a visible recording indicator.
2. **Given** a patient has finished recording, **When** they click stop/send,
   **Then** the audio is submitted to the agent and a reply arrives within a
   reasonable wait time (same as text).
3. **Given** a patient clicks the file upload button, **When** they select a
   supported audio file, **Then** the file is submitted and the agent replies
   as if a voice message was sent.
4. **Given** a patient is using a browser that does not support microphone access,
   **When** they open the audio panel, **Then** only the file upload option is
   shown and a clear message explains the limitation.

---

### User Story 3 - Parallel Operation and Progressive Transition (Priority: P3)

The new professional UI runs on a separate port or path alongside the existing
agent-ui without disrupting it. The old agent-ui is decommissioned only after
the team validates that the new UI passes all success criteria (SC-001–SC-005).
No existing user or workflow is broken during the transition period.

**Why this priority**: Operational safety. The existing agent-ui must remain
functional as a fallback while the new UI is being validated.

**Independent Test**: With both UIs running simultaneously, complete a scheduling
session on each one and confirm both work end-to-end. Then stop the old UI and
confirm the new one continues to work unaffected.

**Acceptance Scenarios**:

1. **Given** both UIs are running, **When** a user opens the old UI URL, **Then**
   it continues to function exactly as before.
2. **Given** both UIs are running, **When** a user opens the new UI URL, **Then**
   the new professional interface loads and connects to the agent.
3. **Given** the new UI has been validated, **When** the old UI is stopped, **Then**
   the new UI operates independently with no errors or broken references.

---

### Edge Cases

- What happens when the agent server is unavailable? The UI MUST display a
  user-friendly connection error, not a blank screen or raw stack trace.
- What happens when the patient uploads an unsupported audio format? The UI MUST
  reject the file before submission and display a clear error listing supported formats.
- What happens when microphone permission is denied by the user? The UI MUST
  fall back gracefully to the file upload option without crashing.
- What happens when the audio file exceeds a reasonable size limit? The UI MUST
  reject it client-side with a clear message before any upload attempt.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The new UI MUST connect to the existing LangGraph agent server without
  requiring changes to the agent or API services.
- **FR-002**: The new UI MUST stream agent responses in real time, displaying each
  token or chunk as it arrives.
- **FR-003**: The new UI MUST render agent replies as formatted text (supporting
  bold, lists, and line breaks) rather than raw strings.
- **FR-004**: The new UI MUST provide a microphone recording button inline in the
  message input bar; tapping it begins recording and a second tap stops and submits
  the audio.
- **FR-005**: The new UI MUST provide a file-attach icon inline in the message input
  bar that opens a file picker accepting at minimum `.mp3`, `.wav`, and `.webm` audio
  formats.
- **FR-006**: The new UI MUST display a clear error state when the agent is
  unreachable, with a retry affordance.
- **FR-007**: The new UI MUST run on a separate port or path from the existing
  agent-ui so both can operate simultaneously during the transition period.
- **FR-008**: The new UI MUST preserve conversation history for the duration of
  the browser session. Persistence across page refreshes via browser storage is
  acceptable and desirable for the MVP.
- **FR-009**: Audio recording MUST be disabled gracefully on browsers without
  microphone API support, falling back to file upload only.
- **FR-010**: The new UI MUST carry AgendAI branding (name, colour theme) giving
  a professional medical-service aesthetic.
- **FR-011**: All patient-facing text (labels, placeholders, error messages, buttons)
  MUST be written in Brazilian Portuguese (pt-BR).

### Key Entities

- **Conversation**: A session-scoped sequence of human and agent messages,
  including text and audio turns.
- **Message**: A single turn in the conversation — either a patient input
  (text string or audio blob) or an agent reply (text, possibly streamed).
- **AudioInput**: A captured or uploaded audio payload submitted in place of
  a text message; processed server-side into a transcript and response.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A patient with no prior experience can complete a full appointment
  scheduling flow in the new UI within 3 minutes on their first attempt.
- **SC-002**: Audio messages (microphone or upload) are submitted and a reply is
  received within the same perceived time window as equivalent text messages.
- **SC-003**: Both UIs operate simultaneously for at least one full business day
  without either crashing or interfering with the other.
- **SC-004**: The new UI is assessed as visually more professional than the existing
  agent-ui by the team before go-live (informal review).
- **SC-005**: All conversation flows that work in the existing agent-ui also work
  in the new UI — zero scheduling-flow regressions.

## Decision Record

### US3 Waiver — Parallel Operation Formally Skipped (2026-05-17)

**Decision**: US3 (parallel operation of `agent-ui` on port 3001 alongside `agent-ui-pro` on port 3002) was **formally waived** by team decision after implementation review.

**Rationale**: The legacy `agent-ui` (Next.js custom build, port 3001) was removed from `docker-compose.yml` and its directory deleted. `agent-ui-pro` was validated as a complete functional replacement covering all user stories from US1 and US2. The parallel period was skipped because:
- `agent-ui-pro` passed all functionality tests from the original `agent-ui`
- No rollback requirement existed for the technical challenge scope
- Maintaining two UIs in parallel added operational complexity without benefit

**Consequence**: SC-003 ("both UIs operate simultaneously for two weeks") and T021/T022 are closed as **N/A — waived**. The old `agent-ui` is no longer available or maintained.

---

## Clarifications

### Session 2026-05-16

- Q: How should the agent-chat-ui be integrated? → A: Clone the repo locally as a new service directory (`agent-ui-pro/`); audio support customized directly in that local copy.
- Q: Where should audio controls live in the UI? → A: Inline in the message input bar — mic icon and file-attach icon beside the text field.
- Q: In which language should the new UI's patient-facing text be written? → A: Portuguese (pt-BR) — all labels, placeholders, and error messages in Brazilian Portuguese.
- Q: Should conversation history survive a page refresh? → A: Persistence via browser storage is acceptable and desirable for MVP; ephemeral-only requirement relaxed.
- Q: What triggers decommissioning the old agent-ui? → A: Team sign-off after the new UI passes all success criteria (SC-001–SC-005).

## Assumptions

- The existing LangGraph dev server (port 8123 / nginx proxy on 8080) remains
  running and reachable; no changes to the agent or API are required for this feature.
- The agent-chat-ui repo (github.com/langchain-ai/agent-chat-ui) will be cloned
  locally and added as a new service directory (e.g., `agent-ui-pro/`) within the
  project. Audio support will be customized directly in this local copy.
- The audio capabilities from the existing agent-ui (microphone capture + file upload)
  will be extracted or replicated as a self-contained component embeddable in the
  new interface.
- The new UI will be served on a different port (e.g., 3002) during the parallel
  operation period; the project's container configuration will be updated accordingly.
- Supported audio formats are those already accepted by the existing agent pipeline
  (at minimum `.mp3`, `.wav`, `.webm`).
- No new authentication or login is required; access control is handled at the
  proxy/agent layer as it is today.
- Mobile responsiveness is desirable but not a hard requirement for this iteration;
  the primary target is desktop browsers.
