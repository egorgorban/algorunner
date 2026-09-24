# Phase 4: Realtime Streaming, Frontend & Documentation - Context

**Gathered:** 2026-09-25
**Status:** Ready for research & planning

<domain>
## Phase Boundary

This phase completes the user-facing product: live WebSocket event streaming of task progress, React + TypeScript web UI for the full interaction cycle (submit → clarify → view editorial), and comprehensive documentation set. The backend pipeline (Phases 1-3) is complete; Phase 4 wraps it in UX and docs.

Requirements: API-04, API-05, UI-01, UI-02, UI-03, UI-04, INFRA-05 (documentation).

Not in this phase: Authentication, sandboxed execution, resource limits, Kubernetes, observability tooling, evaluation framework, cross-task memory. All deferred to future milestones.

</domain>

<decisions>
## Implementation Decisions

### Carried forward from Phase 3 (not re-discussed)
- Postgres is the authoritative store for task state (Phase 3 D-13); WebSocket is a live event channel, not the store.
- Editorial is structured JSON, not Markdown; UI renders it (Phase 3 D-11, D-12).
- Code in the editorial is verbatim from execution; UI never rewrites it (Phase 3 D-12).
- Minimal intermediate artifacts visible in the API response; heavy data lives in Garage (Phase 3 D-13).

### WebSocket Architecture & Real-Time Events

- **D-01: Status write flow** — Worker publishes status transitions to Redis pub/sub on each LangGraph node boundary. API listens to Redis pub/sub and relays messages to WebSocket clients. Postgres status writes happen separately (eventual consistency). This decouples the real-time notification (Redis, fast) from the authoritative store (Postgres, slower).

- **D-02: Reconnection & current-state snapshot** — A WebSocket client connecting to `WS /api/v1/tasks/{id}/events` receives a current-state snapshot immediately (task status, result if completed), then streams only new transitions afterward. This satisfies API-05 (client connecting after task progress immediately sees current state). Snapshot content: task status, timestamps, completion result if any.

- **D-03: Event message format (minimal)** — Each WebSocket event is: `{status: string, timestamp: ISO8601}`. No context fields (approach index, iteration count, error detail). UI accumulates messages to build history. Rationale: smallest payload, Postgres query handles richer detail if needed.

- **D-04: Full status taxonomy** — WebSocket streams all ROADMAP statuses (analyzing_problem, designing_solution, generating_code, generating_tests, executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial, completed, failed). Provides detailed progress visibility without overwhelming the UI.

- **D-05: Redis pub/sub channel naming** — Worker publishes to `task:{task_id}:status`. API subscribes to this channel and forwards messages to the WebSocket handler for that task_id. Garage key paths already include task_id, so task-scoped routing is natural.

### React UI Architecture

- **D-06: Frontend bundler — Vite** — Fast dev server, small production bundle, modern tooling, native ES modules. Separate build step in Docker (multi-stage). Sufficient for SPA; no need for SSR (Next.js) or CRA overhead.

- **D-07: State management — React Context + useReducer** — Built-in to React, no external dependencies. Define a `TaskContext` holding (task state, current status, result, events history) and a reducer for (SUBMIT_TASK, UPDATE_STATUS, SET_RESULT, ADD_EVENT, CLEAR). Simple and adequate for this scale.

- **D-08: Problem input form — Textarea + manual example list** — Textarea for problem text (English or Russian), dynamic list of example input/output pairs (add/remove buttons). No file upload, no rich editor. Direct and uncluttered.

- **D-09: UI layout — Modal clarification + full-page editorial** — User journey: submit form → status page (WebSocket live updates) → if clarification needed, modal prompts for answer → after completion, full-page editorial view with collapsible approaches and code. Keeps focus and avoids overwhelming the screen at any one step.

- **D-10: Code display library — Highlight.js or Prism.js** — Syntax highlighting for Python/Go code blocks. Copy-to-clipboard button on each block. Prism is lighter; Highlight.js is more widely used. Choose Highlight.js for this phase.

- **D-11: Styling approach — TailwindCSS** — Utility-first CSS framework. Pairs well with Vite and React. Fast iteration, consistent design, no custom CSS files.

- **D-12: API client library — fetch API + context** — No need for axios or React Query at this scale. Use native `fetch` in the context reducer; wrap with error handling. For WebSocket, native `WebSocket` API.

### Documentation

- **D-13: Documentation depth — Terse & practical** — CLAUDE.md (working rules, conventions), PRD (user stories, acceptance criteria), architecture summary (high-level boxes + decision log, no full UML), development guide (testing patterns, code style), implementation plan (milestone/task breakdown). No exhaustive API spec, no design system formal doc, no performance benchmarks. ~40-60KB total.

- **D-14: CLAUDE.md scope — Update existing** — Extend the backend CLAUDE.md to include frontend conventions (React component structure, naming, Vite config, state patterns). Single source of truth for all working rules, not split files.

- **D-15: Deferred ideas tracking — Dedicated DEFERRED.md** — Centralized file listing all acknowledged-but-out-of-scope ideas (auth, sandboxing, Kubernetes, observability, evaluation framework, retention policy, cross-task memory, search, filters, user accounts). Each idea gets a brief description and estimated phase/effort level. Prevents ideas from being scattered or lost.

- **D-16: Documentation file structure — Flexible with defaults** — Default layout: `CLAUDE.md` (root), `docs/product/prd.md`, `docs/architecture/architecture.md`, `docs/development/testing.md` & `conventions.md`, `docs/plans/implementation-plan.md`, `DEFERRED.md`. Authors can consolidate (e.g., combine architecture files, merge testing into conventions) as long as the intent remains clear and discoverable.

- **D-17: Documentation generation** — Written manually by Claude during Phase 4 planning and execution. No automated docs-from-code tooling.

### Frontend Deployment & Build

- **D-18: Frontend artifact location — API + frontend + nginx in docker-compose.yml** — Single extended docker-compose.yml with 7 services (api, worker, postgres, redis, garage, frontend, nginx). nginx at port 80 acts as reverse proxy: `/api/*` → api:5000, `/` → frontend:3000. Simpler operations than separate compose files; all-in-one for v1.

- **D-19: Build pipeline — Docker multi-stage** — Vite build happens in Docker Dockerfile stage 1, output `dist/` copied to stage 2 (final frontend image). No manual `npm run build` + commit dist/. Clean, reproducible, dev-friendly (local dev uses Vite dev server, Docker build is deterministic).

- **D-20: Frontend environment config — Runtime from API endpoint** — Frontend fetches `GET /api/config` on load to learn the API base URL and WebSocket URL. Enables the same frontend image to deploy to multiple environments (dev, staging, prod) without rebuilding. Adds one async request at startup.

- **D-21: docker-compose.yml consolidation** — Extend the existing single docker-compose.yml (currently api, worker, postgres, redis, garage from Phases 1-3) to include `frontend` (Vite dev or nginx for prod) and `nginx` services. No separate compose overlays for v1. Rationale: simplicity, single source of truth for deployment.

### Claude's Discretion

- Redis pub/sub error handling: reconnection logic, message ordering guarantees, lag/buffering.
- Exact `task:status` event schema in Redis pub/sub (JSON serialization).
- WebSocket handler connection limits, session timeout, reconnection backoff.
- React Context reducer action types and payload shapes.
- Highlight.js theme and configuration (dark/light mode).
- TailwindCSS config (color palette, component classes, responsive breakpoints).
- Vite config (build output, environment variables, dev server proxy for API calls).
- Dockerfile multi-stage for frontend (Node image version, build optimizations, final image size).
- nginx config (reverse proxy rules, caching headers, static asset serving).
- `/api/config` endpoint response schema (base URL, WebSocket URL, feature flags if any).
- Exact file names and structure inside `docs/` (PascalCase vs snake_case, README nesting).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & requirements
- `.planning/PROJECT.md`: core value, constraints, key decisions
- `.planning/REQUIREMENTS.md`: API-04, API-05, UI-01..04, INFRA-05 (docs)
- `.planning/ROADMAP.md` §Phase 4: goal and success criteria

### Prior phase decisions
- `.planning/phases/03-multi-approach-editorial-persistence/03-CONTEXT.md`: D-11..D-21 (editorial JSON, Postgres result shape, Garage artifact keys)
- `.planning/phases/02-verified-single-solution-core-pipeline/02-CONTEXT.md`: corrections/clarification mechanics that UI must display
- `.planning/REQUIREMENTS.md` §API & Realtime: API-04, API-05 definitions

### Architecture & tech choices
- `.planning/research/STACK.md`: Redis pub/sub patterns, Vite + TypeScript setup, TailwindCSS + Highlight.js
- `interview.md`: original product-owner vision for user-facing UX

### Phase 3 artifacts (live proof)
- `.planning/phases/03-multi-approach-editorial-persistence/03-VERIFICATION.md`: what Phase 3 proved (editorial JSON structure, Garage persistence, parallel approaches)

</canonical_refs>

<code_context>
## Existing Code Insights

### Backend assets (reuse in Phase 4 API)
- `src/algorunner/schemas/task.py`: Task model with status enum (extend with new API-04/API-05 endpoints if needed).
- `src/algorunner/api/routes.py`: existing `POST /api/v1/tasks`, `GET /api/v1/tasks/{id}`, `POST /api/v1/tasks/{id}/clarification`. Phase 4 adds `WS /api/v1/tasks/{id}/events` and `GET /api/config`.
- `src/algorunner/worker/tasks.py`: where status transitions happen in LangGraph node boundaries. Phase 4 must inject Redis publish calls here.
- `src/algorunner/config.py`: `redis_url`, `api_base_url` (add if not present) — used by frontend to construct WebSocket URL.

### Frontend structure (new)
- `frontend/src/` — main React source.
  - `frontend/src/App.tsx` — root component.
  - `frontend/src/context/TaskContext.tsx` — React Context + useReducer for task state.
  - `frontend/src/pages/` — ProblemInput.tsx, StatusView.tsx, EditorialView.tsx, ClarificationModal.tsx.
  - `frontend/src/components/` — reusable (CodeBlock.tsx with Highlight.js, ExampleList.tsx, StatusIndicator.tsx).
  - `frontend/src/api.ts` — fetch() wrappers for API calls and WebSocket client.
  - `frontend/src/index.css` — TailwindCSS imports.
- `frontend/vite.config.ts` — proxy dev server API calls to `http://localhost:5000/api`.
- `frontend/Dockerfile` — multi-stage (build stage: `npm run build`, final stage: nginx).
- `frontend/.env.production` — stub (API base URL will be fetched at runtime).

### Integration points
- `docker-compose.yml`: add `frontend` service (Vite dev or built via Dockerfile), `nginx` service.
- `Dockerfile.api`: no changes (backend unaffected).
- `src/algorunner/api/main.py` (FastAPI app): add `GET /api/config`, add CORS headers if needed, WebSocket handler at `/api/v1/tasks/{id}/events`.
- `src/algorunner/worker/tasks.py`: inject Redis publish on status transition (after writing Postgres, publish to `task:{task_id}:status`).

### Patterns from Phase 2-3
- One node → one bounded action (LLM call, tool, or state transition). WebSocket event is a thin wrapper around status writes.
- Structured schemas validate data. Define StatusEvent Pydantic model for events (even if minimal).
- Error handling: network/Redis errors don't crash the worker; they log and continue. Frontend reconnects gracefully.

</code_context>

<specifics>
## Specific Ideas

- User typically interacts: paste problem → see live status updating → if clarification, answer immediately in modal → view final editorial with all approaches.
- Status indicator on the live page can be as simple as a badge (queued, analyzing, solving, executing, reviewing, writing, completed) with elapsed time. No progress bar needed.
- Code blocks in the editorial should be full-width for readability. Syntax highlighting via Highlight.js with a dark-mode theme.
- The clarification modal should be dismissible only by submitting an answer or (optionally) skipping (depends on whether skip is UX-friendly).
- Example management in the input form: start with one empty example pair, add/remove buttons. Validation: both input and output are required if an example is present.
- The editorial display should collapse/expand each approach, showing intuition → algorithm → Python code → Go code → complexity → notes in sequence. Makes long articles scannable.

</specifics>

<deferred>
## Deferred Ideas

- **Authentication & user accounts** — v1 is stateless per-task. Multi-user, session management, saved history deferred to Phase 5.
- **Sandboxed code execution** — Docker sandbox / isolated execution service for generated Python/Go. v1 uses plain subprocess; sandboxing is a known security hardening, tracked but not built now.
- **Resource limits on execution** — CPU/RAM/time/network/filesystem quotas. Deferred alongside sandboxing.
- **Kubernetes deployment** — v1 ships on Docker Compose; Kubernetes is a later infrastructure milestone.
- **Observability & cost tracking** — Structured logging beyond basics, Prometheus, OpenTelemetry, LangSmith tracing, token cost tracking. Deferred to Phase 5.
- **Evaluation framework & benchmark dataset** — No existing dataset; system relies on LLM capability for v1. Evaluation tooling deferred.
- **Search & filtering** — Full-text search over past editorials, filter by difficulty/tags. Deferred to multi-user phase.
- **Retention & lifecycle policy** — Garage artifact retention (cleanup, expiration). v1 keeps artifacts forever; retention policy deferred.
- **Markdown rendering** — Editorial could be Markdown (Pandoc-convertible); v1 is JSON for UI flexibility. Markdown export deferred.
- **Mobile-responsive optimization** — v1 targets desktop/tablet. Mobile responsive polish deferred to UX phase.
- **Accessibility (a11y)** — ARIA labels, keyboard navigation, screen-reader testing. Deferred to accessibility phase.

</deferred>

