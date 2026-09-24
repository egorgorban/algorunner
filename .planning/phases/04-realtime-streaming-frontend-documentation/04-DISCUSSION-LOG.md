# Phase 4 Discussion Log

**Date:** 2026-09-25  
**Participants:** User (product owner), Claude (builder)  
**Format:** Structured area-by-area discussion with multiSelect area selection, then 4 questions per area.

---

## Area Selection

**Question:** Which areas matter most for Phase 4 implementation?

**Options presented:**
1. WebSocket & status streaming
2. React UI architecture & UX
3. Documentation structure
4. Deployment & serving

**User selection:** All 4 areas selected.

---

## Area 1: WebSocket & Status Streaming

### Q1: Status writes — who updates task.status in Postgres on each phase transition?

**Options:**
- Worker writes immediately
- API polls & writes
- Worker publishes, API relays ✓ **Selected**

**Notes:** Worker publishes events to Redis pub/sub (fast, real-time), API relays to WebSocket clients. Postgres writes happen separately (eventual consistency). Decouples notification (Redis) from authoritative store (Postgres).

### Q2: Reconnection behavior — what does a WebSocket client connecting after task progress see?

**Options:**
- Current state snapshot + new events ✓ **Selected**
- Full event replay from start
- Postgres sync + new events

**Notes:** API sends current status/result on connect, then streams only new transitions. Simplest for client. Satisfies API-05 (client connecting after task progress immediately sees current state).

### Q3: Event message schema — what does each WebSocket status-transition message contain?

**Options:**
- Minimal (status + timestamp) ✓ **Selected**
- Rich context (status, timestamp, approach/iteration, error)
- Full task state snapshot

**Notes:** Each event: `{status, timestamp}`. UI accumulates to build history. Smallest payload. Postgres query provides richer detail if needed.

### Q4: Status taxonomy — how granular should the WebSocket stream be?

**Options:**
- All ROADMAP statuses (14 total) ✓ **Selected**
- Grouped (8-10 statuses)
- High-level milestones (5-6)

**Notes:** Full ROADMAP status sequence streamed: queued, analyzing_problem, designing_solution, generating_code, generating_tests, executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial, completed, failed. Provides detailed progress visibility.

---

## Area 2: React UI Architecture & UX

### Q1: Frontend bundler & build setup

**Options:**
- Vite ✓ **Selected**
- Create React App
- Next.js

**Notes:** Vite chosen for modern tooling, fast dev server, small production bundle. Separate build step in Docker (multi-stage).

### Q2: State management for task + UI state

**Options:**
- React Context + useReducer ✓ **Selected**
- Zustand
- Redux/RTK

**Notes:** Built-in to React, no extra deps. TaskContext holds (task state, status, result, events history) and reducer handles (SUBMIT_TASK, UPDATE_STATUS, SET_RESULT, ADD_EVENT, CLEAR).

### Q3: Problem input form — how should users submit problem text + examples?

**Options:**
- Textarea + manual example list ✓ **Selected**
- Textarea + file upload
- Rich editor with example inline editing

**Notes:** Textarea for problem text, dynamic list of example input/output pairs (add/remove buttons). Direct, uncluttered UX.

### Q4: Layout — how to present clarification prompt + live status + final editorial?

**Options:**
- Modal clarification + full-page editorial ✓ **Selected**
- Sidebar layout
- Tabs/Accordion

**Notes:** Focused UX. Problem→Submit→Status→Clarification(modal)→Editorial (full page). Keeps attention on one task at a time.

---

## Area 3: Documentation Structure

### Q1: Content depth — how detailed per doc?

**Options:**
- Terse & practical ✓ **Selected**
- Rich with examples & visuals
- Comprehensive

**Notes:** CLAUDE.md (working rules), PRD (user stories + AC), architecture (boxes + arrows + decision log), development (test patterns), plan (milestone roadmap). ~40-60KB total. No exhaustive API spec, no formal design system, no benchmarks.

### Q2: CLAUDE.md scope — how to handle working rules for backend + frontend?

**Options:**
- Update existing CLAUDE.md ✓ **Selected**
- Keep CLAUDE.md for backend, frontend rules in docs/development
- Split into CLAUDE-backend.md + CLAUDE-frontend.md

**Notes:** Extend existing CLAUDE.md to include frontend conventions (React component structure, naming, Vite config, state patterns). Single source of truth for all working rules.

### Q3: Deferred items tracking — how to capture ideas that don't fit v1?

**Options:**
- Dedicated DEFERRED.md ✓ **Selected**
- "Future Ideas" subsection in each doc
- Inline [FUTURE] markers only

**Notes:** Centralized DEFERRED.md file listing all acknowledged-but-out-of-scope ideas (auth, sandboxing, Kubernetes, observability, evaluation, retention policy, cross-task memory, search, filters, a11y, mobile-responsive). Each idea gets brief description + estimated phase/effort.

### Q4: Documentation file structure — exact layout and naming

**Options:**
- Strict ROADMAP spec
- Flexible ✓ **Selected**
- Hierarchical by concern

**Notes:** Default layout (docs/product/prd.md, docs/architecture/architecture.md, docs/development/{testing,conventions}.md, docs/plans/implementation-plan.md, DEFERRED.md) but allow consolidation. Flexibility as long as intent remains clear and discoverable.

---

## Area 4: Deployment & Frontend Serving

### Q1: Frontend artifact location in the deployed system

**Options:**
- Bundled with API image
- Separate frontend container
- API + frontend services in Compose with nginx ✓ **Selected**

**Notes:** Both services in docker-compose.yml with nginx reverse proxy at port 80. Routes `/api/*` → api:5000, `/` → frontend:3000. Production-ready, separate concerns, slightly more ops but simpler than API-bundled for this phase.

### Q2: Frontend build pipeline

**Options:**
- Manual Vite build, commit dist/
- Docker multi-stage build ✓ **Selected**
- Separate CI step with artifact storage

**Notes:** Dockerfile stage 1: `npm run build`. Stage 2: copy dist/. Clean, self-contained, reproducible. No manual `npm run build` + commit distraction.

### Q3: Frontend environment config — how should frontend learn the API endpoint?

**Options:**
- Baked into build
- Runtime from API endpoint ✓ **Selected**
- nginx substitution

**Notes:** Frontend fetches `GET /api/config` on load to learn API base URL and WebSocket URL. Enables same image to deploy to multiple environments without rebuilding. Adds one async request at startup, acceptable tradeoff.

### Q4: docker-compose.yml changes — how to organize with frontend added?

**Options:**
- Single extended docker-compose.yml ✓ **Selected**
- Separate overlay file
- docker-compose.prod.yml for prod

**Notes:** Extend existing docker-compose.yml to include `frontend` and `nginx` services (now 7 services total). Single source of truth, simpler operations for v1.

---

## Decision Rollup

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Status writes | Worker publishes to Redis, API relays | Real-time notification + eventual consistency |
| Reconnection | Current state snapshot + new events | API-05 compliance, simple client logic |
| Event schema | Minimal (status + timestamp) | Smallest payload |
| Status granularity | All 14 ROADMAP statuses | Detailed progress visibility |
| Bundler | Vite | Modern, fast, small bundle |
| State management | React Context + useReducer | Built-in, no deps, adequate |
| Input form | Textarea + manual example list | Simple, direct UX |
| Layout | Modal clarification + full-page editorial | Focused, sequential |
| Doc depth | Terse & practical | 40-60KB, covers essentials |
| CLAUDE.md scope | Update existing (add frontend rules) | Single source of truth |
| Deferred tracking | Dedicated DEFERRED.md | Centralized, discoverable |
| Doc structure | Flexible (defaults + consolidation OK) | Intent-driven, not rigid |
| Frontend serving | API + frontend + nginx in Compose | Production-ready, separate services |
| Build pipeline | Docker multi-stage | Deterministic, reproducible |
| Env config | Runtime from /api/config | Multi-environment deployable |
| Compose structure | Single extended docker-compose.yml | Simplicity for v1 |

---

## Deferred Ideas Noted

- Authentication & user accounts (future phase)
- Sandboxed code execution
- Resource limits
- Kubernetes deployment
- Observability & cost tracking
- Evaluation framework & benchmark dataset
- Search & filtering
- Retention & lifecycle policy
- Markdown rendering
- Mobile-responsive optimization
- Accessibility (a11y)

All captured in 04-CONTEXT.md deferred section for downstream reference.
