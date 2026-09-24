# Phase 4: Realtime Streaming, Frontend & Documentation - Research

**Researched:** 2026-09-25
**Domain:** FastAPI WebSocket + Redis Pub/Sub relay; React 19 + TypeScript + Vite 8 + Tailwind v4 SPA; nginx reverse proxy in Docker Compose; project documentation set
**Confidence:** HIGH (backend realtime, verified against installed code); MEDIUM (frontend stack, verified via registry + official docs); MEDIUM (Docker images, tags not pullable from this sandbox)

## Summary

The backend is ready for streaming, but it emits fewer statuses than the phase needs. The graph only emits 3 statuses in-graph: `designing_solution` (`graph/build.py:54`), `generating_code` (`graph/approach.py:252`) and `writing_editorial` (`agents/editorial_writer/node.py:122`). The worker writes `analyzing_problem`, `awaiting_clarification`, `completed` and `failed` directly. **`generating_tests`, `executing_tests`, `reviewing` and `correcting` are never emitted anywhere.** D-04 and API-04 need them, so the plan has to add emission points inside the per-approach subgraph. I confirmed in the installed LangGraph 1.2.12 source that a subgraph invoked from a node inherits the parent `Runtime.context` (`parent_runtime.merge(runtime)` → `context=other.context or self.context`). So `runtime.context.status_sink` can be reached from subgraph nodes with no extra plumbing.

The right shape for API-05 (no lost or stale events) is: **every Postgres status write returns its `updated_at` and then publishes `{type:"status", status, timestamp=updated_at}` to `task:{task_id}:status`.** The WebSocket handler **subscribes first, then reads the Postgres snapshot, sends it, and forwards only events whose timestamp is later than the snapshot's `updated_at`**. Postgres `now()` is the only clock and the write always happens before the publish. So any event with `timestamp <= snapshot.updated_at` is already reflected in the snapshot, and the race between snapshot and first event is closed deterministically. On `awaiting_clarification`, `completed` and `failed` events, the handler re-reads Postgres and sends a fresh snapshot, which carries `clarification_question`, `result` or `error`. On a terminal status it closes the socket with code 1000.

The frontend should be scaffolded from `create-vite@9.2.1`'s `react-ts` template (React 19, Vite 8, TypeScript ~6.0, `@vitejs/plugin-react` 6). Add Tailwind v4 through `@tailwindcss/vite` (CSS-first, no `tailwind.config.js`) and `highlight.js` 11 core with only `python` and `go` registered. Per the locked decisions there is no router, no state library and no HTTP client library. For documentation, write hand-authored content **outside** the GSD marker blocks in `.claude/CLAUDE.md`, because content inside `<!-- GSD:*-start/end -->` gets regenerated. Create all four `docs/architecture/*.md` files named in success criterion 3, even though D-16 allows consolidating them.

**Primary recommendation:** Build the backend realtime slice first (event schema → publish-on-write in `storage/tasks.py` → subgraph status wrappers → WS endpoint + `/api/config`, tested with a same-loop uvicorn fixture). Then the frontend, then nginx/compose, then docs. The UI only works once the event contract is stable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Carried forward from Phase 3 (not re-discussed)
- Postgres is the authoritative store for task state (Phase 3 D-13); WebSocket is a live event channel, not the store.
- Editorial is structured JSON, not Markdown; UI renders it (Phase 3 D-11, D-12).
- Code in the editorial is verbatim from execution; UI never rewrites it (Phase 3 D-12).
- Minimal intermediate artifacts visible in the API response; heavy data lives in Garage (Phase 3 D-13).

#### WebSocket Architecture & Real-Time Events

- **D-01: Status write flow** — Worker publishes status transitions to Redis pub/sub on each LangGraph node boundary. API listens to Redis pub/sub and relays messages to WebSocket clients. Postgres status writes happen separately (eventual consistency). This decouples the real-time notification (Redis, fast) from the authoritative store (Postgres, slower).

- **D-02: Reconnection & current-state snapshot** — A WebSocket client connecting to `WS /api/v1/tasks/{id}/events` receives a current-state snapshot immediately (task status, result if completed), then streams only new transitions afterward. This satisfies API-05 (client connecting after task progress immediately sees current state). Snapshot content: task status, timestamps, completion result if any.

- **D-03: Event message format (minimal)** — Each WebSocket event is: `{status: string, timestamp: ISO8601}`. No context fields (approach index, iteration count, error detail). UI accumulates messages to build history. Rationale: smallest payload, Postgres query handles richer detail if needed.

- **D-04: Full status taxonomy** — WebSocket streams all ROADMAP statuses (analyzing_problem, designing_solution, generating_code, generating_tests, executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial, completed, failed). Provides detailed progress visibility without overwhelming the UI.

- **D-05: Redis pub/sub channel naming** — Worker publishes to `task:{task_id}:status`. API subscribes to this channel and forwards messages to the WebSocket handler for that task_id. Garage key paths already include task_id, so task-scoped routing is natural.

#### React UI Architecture

- **D-06: Frontend bundler — Vite** — Fast dev server, small production bundle, modern tooling, native ES modules. Separate build step in Docker (multi-stage). Sufficient for SPA; no need for SSR (Next.js) or CRA overhead.

- **D-07: State management — React Context + useReducer** — Built-in to React, no external dependencies. Define a `TaskContext` holding (task state, current status, result, events history) and a reducer for (SUBMIT_TASK, UPDATE_STATUS, SET_RESULT, ADD_EVENT, CLEAR). Simple and adequate for this scale.

- **D-08: Problem input form — Textarea + manual example list** — Textarea for problem text (English or Russian), dynamic list of example input/output pairs (add/remove buttons). No file upload, no rich editor. Direct and uncluttered.

- **D-09: UI layout — Modal clarification + full-page editorial** — User journey: submit form → status page (WebSocket live updates) → if clarification needed, modal prompts for answer → after completion, full-page editorial view with collapsible approaches and code. Keeps focus and avoids overwhelming the screen at any one step.

- **D-10: Code display library — Highlight.js or Prism.js** — Syntax highlighting for Python/Go code blocks. Copy-to-clipboard button on each block. Prism is lighter; Highlight.js is more widely used. Choose Highlight.js for this phase.

- **D-11: Styling approach — TailwindCSS** — Utility-first CSS framework. Pairs well with Vite and React. Fast iteration, consistent design, no custom CSS files.

- **D-12: API client library — fetch API + context** — No need for axios or React Query at this scale. Use native `fetch` in the context reducer; wrap with error handling. For WebSocket, native `WebSocket` API.

#### Documentation

- **D-13: Documentation depth — Terse & practical** — CLAUDE.md (working rules, conventions), PRD (user stories, acceptance criteria), architecture summary (high-level boxes + decision log, no full UML), development guide (testing patterns, code style), implementation plan (milestone/task breakdown). No exhaustive API spec, no design system formal doc, no performance benchmarks. ~40-60KB total.

- **D-14: CLAUDE.md scope — Update existing** — Extend the backend CLAUDE.md to include frontend conventions (React component structure, naming, Vite config, state patterns). Single source of truth for all working rules, not split files.

- **D-15: Deferred ideas tracking — Dedicated DEFERRED.md** — Centralized file listing all acknowledged-but-out-of-scope ideas (auth, sandboxing, Kubernetes, observability, evaluation framework, retention policy, cross-task memory, search, filters, user accounts). Each idea gets a brief description and estimated phase/effort level. Prevents ideas from being scattered or lost.

- **D-16: Documentation file structure — Flexible with defaults** — Default layout: `CLAUDE.md` (root), `docs/product/prd.md`, `docs/architecture/architecture.md`, `docs/development/testing.md` & `conventions.md`, `docs/plans/implementation-plan.md`, `DEFERRED.md`. Authors can consolidate (e.g., combine architecture files, merge testing into conventions) as long as the intent remains clear and discoverable.

- **D-17: Documentation generation** — Written manually by Claude during Phase 4 planning and execution. No automated docs-from-code tooling.

#### Frontend Deployment & Build

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

### Deferred Ideas (OUT OF SCOPE)

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
</user_constraints>

### CONTEXT.md factual corrections (verified against the repo this session)

The planner must use the verified values below. CONTEXT.md's `code_context` section has several errors:

| CONTEXT.md says | Actual (verified) | Source |
|---|---|---|
| nginx `/api/*` → `api:5000` (D-18) | API listens on **8000**: `- "8000:8000"`. Dockerfile CMD: `"--port", "8000"` | [VERIFIED: docker-compose.yml:54-55], [VERIFIED: docker/Dockerfile.api CMD line] |
| `src/algorunner/api/routes.py` | Routes live in `src/algorunner/api/routes/tasks.py` with `router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])` | [VERIFIED: src/algorunner/api/routes/tasks.py:12] |
| Status transitions happen in `worker/tasks.py` | Split: the worker writes `ANALYZING_PROBLEM` (tasks.py:171) plus terminal/pause states (tasks.py:76-93, 117-120, 152-154, 208-214). In-graph transitions go through `emit_status(ctx, …)` → `ctx.status_sink` → `_pg_status_sink` (tasks.py:59-73) | [VERIFIED: src/algorunner/worker/tasks.py] |
| `config.py`: `api_base_url` "add if not present" | Not present. Only `redis_url: str = "redis://localhost:6379"` exists | [VERIFIED: src/algorunner/config.py:15] |
| `03-VERIFICATION.md` is a canonical ref | **File does not exist.** Use `03-08-SUMMARY.md` and `scripts/verify_phase3_live.py` | [VERIFIED: ls of phase 03 dir] |
| All D-04 statuses flow today | Only `DESIGNING_SOLUTION`, `GENERATING_CODE` and `WRITING_EDITORIAL` are emitted in-graph. `GENERATING_TESTS`, `EXECUTING_TESTS`, `REVIEWING` and `CORRECTING` are **never emitted** | [VERIFIED: grep emit_status → build.py:54, approach.py:252, editorial_writer/node.py:122] |
| Problem form: textarea + examples (D-08) | `TaskSubmission` also **requires `language`** (`"en"`/`"ru"`). The form needs a language selector | [VERIFIED: src/algorunner/schemas/task.py:15-29] |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-04 | `WS /api/v1/tasks/{task_id}/events` streams status transitions in realtime | Pattern 1 (publish-on-write), Pattern 2 (subgraph status wrappers that add the 4 missing statuses), Pattern 3 (WS relay handler) |
| API-05 | A WS client connecting late immediately receives current state | Pattern 3: subscribe → snapshot → timestamp-dedupe; terminal/clarification snapshot refresh |
| UI-01 | Problem input form (text + optional examples) | Frontend Pattern 5 (form mirrors `TaskSubmission` limits + language selector) |
| UI-02 | Live pipeline status via the WS endpoint | Frontend Pattern 6 (`useTaskEvents` hook with reconnect/backoff, StrictMode-safe) |
| UI-03 | Clarification prompt when `awaiting_clarification` | Snapshot carries `clarification_question`; `POST /api/v1/tasks/{id}/clarification` (409 on race) |
| UI-04 | Final editorial per approach (explanation, Python/Go code, complexity, difficulty, tags, edge cases) | Editorial TS types mirror `schemas/editorial.py`; CodeBlock with hljs core; inline-backtick renderer |
| INFRA-05 | Full documentation set + dedicated deferred section | Docs section: file list per success criterion 3, CLAUDE.md marker-safe editing, DEFERRED.md |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.14, `uv`, LangGraph, OpenAI, taskiq + Redis, PostgreSQL, Garage: fixed. Do not add Celery/ARQ.
- **Frontend: React + TypeScript, included in v1**. Deployment: **Docker Compose only** (no Kubernetes).
- **Type safety: maximum feasible.** In TS this means `strict: true` and no `any` in the API/event contract types.
- **Architecture style: simple modular** (not DDD/clean). New backend code goes in plain modules (`api/`, `schemas/`, `storage/`, and a new small `realtime/` module is fine), with no repositories or service layers.
- **Never call blocking I/O inside async code** ("What NOT to Use"). Redis must use `redis.asyncio`, not sync `redis`.
- Postgres pool must keep `autocommit=True, row_factory=dict_row` (storage/postgres.py). Do not open a second bare connection.
- Every SQL uses `%s` placeholders (T-01-01, storage/tasks.py header).
- GSD workflow enforcement: file edits go through GSD commands. Content inside the `<!-- GSD:*-start … -->`/`<!-- GSD:*-end -->` blocks of `.claude/CLAUDE.md` is **regenerated by gsd-tools** (see Pitfall 9).
- Stack note (CLAUDE.md): "a client that connects the WebSocket after a status transition already happened … should first do a 'sync' read … then attach". Pattern 3 moves this sync read **server-side** (snapshot in-band), which satisfies both this note and D-02.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Status transition emission (all 12 statuses) | Worker (LangGraph nodes + worker task body) | API (clarification consume → `analyzing_problem`) | Transitions happen where the work happens; the API owns only the consume transition it already performs |
| Authoritative task state | Database (Postgres `tasks`) | — | Locked (Phase 3 D-13, DATA-01) |
| Live fan-out | Redis Pub/Sub (`task:{id}:status`) | — | Locked D-01/D-05; a fire-and-forget channel, not a store |
| Snapshot + relay + dedupe | API (FastAPI WS handler) | — | Only the API can combine a Postgres read with a Redis subscription atomically enough for API-05 |
| Runtime config (`GET /api/config`) | API | Browser | D-20 |
| Form validation (length/count limits) | API (Pydantic, authoritative) | Browser (mirrors for UX) | The server stays the trust boundary; client checks only give early feedback |
| Reconnect/backoff, event history, view switching | Browser | — | Pure client concerns |
| Syntax highlighting, prose rendering | Browser | — | Code is verbatim from Postgres `result.editorial` (Phase 3 D-12) |
| Static asset serving | CDN/Static (frontend container: nginx serving `dist/`) | — | D-18/D-19 |
| Reverse proxy, WS upgrade, security headers | Gateway nginx | — | D-18 |

## Standard Stack

### Core (backend, all already installed; no new Python dependencies needed)

| Library | Version (installed) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.141.1 | `@router.websocket` endpoint, `GET /api/config` | Already the API framework [VERIFIED: uv pip list] |
| `starlette` | 1.6.0 | `WebSocket`, `WebSocketDisconnect`, `HTTPConnection` | FastAPI's WS layer [VERIFIED: uv pip list] |
| `redis` (redis-py, `redis.asyncio`) | 8.1.0 | `publish` (worker + API), `pubsub()` subscriber (API) | Already a transitive dep of `taskiq-redis`. The planner should **declare it explicitly** in `pyproject.toml` because code now imports it directly [VERIFIED: uv pip list; probe below] |
| `uvicorn[standard]` | 0.53.0 | Serves WS through the `websockets` protocol impl. Sends WS pings every 20 s by default | `ws_ping_interval: 'float \| None' = 20.0` [VERIFIED: inspect of uvicorn.config.Config.__init__] |
| `websockets` | 16.1.1 | Client for live/integration WS tests | Already installed via `uvicorn[standard]`. Add to the `dev` group explicitly if tests import it [VERIFIED: uv pip list] |

Redis Pub/Sub probe, run this session against the running `redis:8` container with redis-py 8.1.0:
```
subscribers: 1 msg: {'type': 'message', 'pattern': None, 'channel': 'task:probe:status', 'data': '{"type":"status","status":"reviewing"}'}
```

### Core (frontend, new)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `create-vite` (scaffold only) | 9.2.1 | `react-ts` template | Official Vite scaffolder. Template pins listed below [VERIFIED: npm pack create-vite@9.2.1, template-react-ts/package.json] |
| `react`, `react-dom` | ^19.2.8 (resolves 19.3.0) | UI | Template pin [VERIFIED: npm registry] |
| `vite` | ^8.3.0 (8.3.1 latest) | Dev server + build | D-06. engines `node: '^20.19.0 \|\| >=22.12.0'` [VERIFIED: npm view] |
| `@vitejs/plugin-react` | ^6.1.1 | React fast refresh/JSX | Template pin. peer `vite: '^8.0.0'` [VERIFIED: npm view] |
| `typescript` | ~6.0.2 | Type-checking (`tsc -b`) | **Template pin. Do NOT take `latest` (7.0.2 is the native-Go port)**. Stay on the template's line [VERIFIED: npm view + template] |
| `tailwindcss` + `@tailwindcss/vite` | 4.3.3 | Styling (D-11) | v4 CSS-first: `@import "tailwindcss";` + Vite plugin. peer `vite: '^5.2.0 \|\| ^6 \|\| ^7 \|\| ^8'` [CITED: tailwindcss.com/docs installation via Context7] [VERIFIED: npm view] |
| `highlight.js` | 11.12.0 | Python/Go highlighting (D-10) | Use `highlight.js/lib/core` + `registerLanguage` for python/go only [CITED: github.com/highlightjs/highlight.js README via Context7] |

### Supporting (frontend, optional)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `vitest` | 5.0.1 | Unit tests of pure TS (reducer, inline-code parser, URL builder, hljs escaping) | Recommended. Node environment is enough, **no jsdom/RTL needed** for pure-function tests. engines `^22.12.0 \|\| ^24.0.0 \|\| >=26.0.0` [VERIFIED: npm view] |
| `@types/node` | ^24.13.3 | Template devDep (vite.config.ts types) | Comes with the template |

**Not recommended (keeps with D-07/D-12 minimalism):** react-router (use URL `?task=<id>` + state-driven views), axios/React Query, react-markdown (prose uses only backticks, see Pattern 8), jsdom/@testing-library (only needed for component tests, which this phase does not require).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-connection `redis.pubsub()` | One shared `psubscribe("task:*:status")` + in-process `asyncio.Queue` fan-out | Scales past ~hundreds of sockets with one Redis connection, but adds a background task, a registry and lifecycle bugs. v1 scale does not need it; record it in DEFERRED.md |
| Publish inside `storage/tasks.py` writers | Publish at each call site (worker, API) | More call sites means a missed transition becomes likely (there are ≥8 write sites). Centralizing makes "what is a status transition" defined in one place (CLAUDE.md stack note) |
| Frontend container = nginx serving `dist/` | `vite preview` / `serve` | `vite preview` is documented as not for production. nginx:alpine is tiny and handles SPA fallback |

**Installation:**
```bash
# Backend: make the already-locked transitive dep explicit (no version change)
uv add "redis>=8.1.0"
uv add --dev "websockets>=16.1.1"

# Frontend
npm create vite@9.2.1 frontend -- --template react-ts
cd frontend && npm install
npm install highlight.js@^11.12.0
npm install -D tailwindcss@^4.3.3 @tailwindcss/vite@^4.3.3 vitest@^5.0.1
# commit frontend/package-lock.json (Dockerfile uses `npm ci`)
```

## Package Legitimacy Audit

Seam: `gsd-tools query package-legitimacy check --ecosystem npm …` (run this session). Every `SUS` verdict has the sole reason `too-new`: the **latest release** is less than about 30 days old. The packages themselves are long-established (e.g. vite created 2020-04-21, ~131M weekly downloads; react created 2011, ~132M weekly downloads). None has a `postinstall` script (`npm view <pkg> scripts.postinstall` → empty for all).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| vite | npm | 6 yrs (8.3.1 published 2026-09-24) | ~131M/wk | github.com/vitejs/vite | SUS (too-new) | Flagged. Planner adds checkpoint:human-verify before `npm install` |
| react / react-dom | npm | 15 yrs (19.3.0 published 2026-09-09) | ~132M/wk | github.com/react/react | SUS (too-new) | Flagged, same checkpoint |
| @vitejs/plugin-react | npm | 5 yrs (6.1.1 published 2026-08-28) | high | github.com/vitejs/vite-plugin-react | SUS (too-new) | Flagged, same checkpoint |
| @types/react / @types/react-dom | npm | 10 yrs | high | DefinitelyTyped | SUS (too-new) | Flagged, same checkpoint |
| vitest | npm | 4.8 yrs (5.0.1 published 2026-09-15) | high | github.com/vitest-dev/vitest | SUS (too-new) | Flagged, same checkpoint |
| typescript | npm | 12+ yrs | very high | github.com/microsoft/TypeScript | OK | Approved (pin ~6.0.2) |
| tailwindcss / @tailwindcss/vite | npm | established | high | github.com/tailwindlabs/tailwindcss | OK | Approved |
| highlight.js | npm | 14 yrs | high | github.com/highlightjs/highlight.js | OK | Approved |
| @testing-library/react, jsdom | npm | established | high | — | SUS (too-new) | **Not recommended for this phase.** Omit |
| redis (PyPI) | PyPI | already in uv.lock | — | github.com/redis/redis-py | (in lockfile) | Approved: already resolved dependency |
| websockets (PyPI) | PyPI | already in uv.lock | — | github.com/python-websockets/websockets | (in lockfile) | Approved: already resolved dependency |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** vite, react, react-dom, @vitejs/plugin-react, @types/react, @types/react-dom, vitest. All are flagged only for "latest release is recent". **One** `checkpoint:human-verify` before the frontend `npm install` covers them all. Commit `package-lock.json` so the Docker build (`npm ci`) is reproducible.

## Architecture Patterns

### System Architecture Diagram

```
 Browser (React SPA)
   │  1. GET /api/config ───────────────────────────────┐
   │  2. POST /api/v1/tasks {problem_text,language,     │
   │        examples} → 202 {task_id,status:queued}     │
   │  3. WS /api/v1/tasks/{id}/events                   │
   ▼                                                    │
 nginx gateway :80 ── "/" ──► frontend (nginx, dist/, SPA fallback) :3000
   │ "/api/" (HTTP + WS Upgrade, proxy_read_timeout 1h)
   ▼
 FastAPI api :8000
   ├─ POST /tasks ──► storage.insert_task (PG) ──► taskiq .kiq(solve_problem) ──► Redis stream
   ├─ POST /tasks/{id}/clarification ──► storage.attempt_consume_clarification
   │                                      (PG UPDATE … RETURNING updated_at ──► PUBLISH analyzing_problem)
   └─ WS /tasks/{id}/events
        a. accept  b. SUBSCRIBE task:{id}:status  c. SELECT task (snapshot)
        d. send {type:"snapshot"} ── terminal? ──► close(1000)
        e. loop: message ─► ts <= last_ts? drop : send {type:"status"}
                 status ∈ {awaiting_clarification, completed, failed} ─► re-read PG ─► send snapshot
                 terminal ─► close(1000);  client disconnect ─► unsubscribe + aclose
                                   ▲
                                   │ Redis Pub/Sub  task:{id}:status  (JSON StatusEvent)
                                   │
 taskiq worker ── solve_problem / resume_task_with_clarification
   ├─ storage.update_task_status(ANALYZING_PROBLEM) ─► PG write ─► PUBLISH
   ├─ graph.ainvoke(context=PipelineContext(status_sink=_pg_status_sink))
   │    record_analysis ─► emit DESIGNING_SOLUTION
   │    run_approach (×N parallel) ─► emit GENERATING_CODE
   │       subgraph: solver/code_gen(iter>0) ─► CORRECTING   [NEW]
   │                 test_generator ─► GENERATING_TESTS        [NEW]
   │                 execute_python ─► EXECUTING_TESTS         [NEW]
   │                 reviewer ─► REVIEWING                     [NEW]
   │    editorial_writer ─► emit WRITING_EDITORIAL
   │    (every emit → _pg_status_sink → storage.update_task_status → PG write → PUBLISH)
   └─ _handle_result_or_pause ─► update_task_clarification / _completed / _failed ─► PG ─► PUBLISH
```

### Recommended Project Structure

```
src/algorunner/
├── realtime/                 # NEW: small module, no service layer
│   ├── __init__.py
│   ├── events.py             # StatusEvent, TaskSnapshotEvent (Pydantic), channel_for(task_id)
│   └── publisher.py          # get_publisher_redis() (lru_cache), publish_status() never raises
├── api/
│   ├── dependencies.py       # get_pg_pool(conn: HTTPConnection), get_redis(conn: HTTPConnection)
│   ├── main.py               # lifespan: + app.state.redis; include config + events routers
│   └── routes/
│       ├── tasks.py          # unchanged HTTP routes
│       ├── events.py         # NEW: @router.websocket("/{task_id}/events")
│       └── config.py         # NEW: GET /api/config
├── storage/tasks.py          # status writers: RETURNING updated_at + publish_status()
└── graph/approach.py         # status wrappers around subgraph nodes
frontend/
├── Dockerfile                # node build stage → nginx:alpine serving dist on :3000
├── nginx.conf                # SPA fallback for the frontend container
├── index.html
├── package.json / package-lock.json
├── vite.config.ts            # react() + tailwindcss(); dev proxy /api → :8000 (ws: true)
├── tsconfig*.json            # template + "strict": true
└── src/
    ├── main.tsx / App.tsx    # view switch: input | status | editorial
    ├── index.css             # @import "tailwindcss"; + hljs theme import
    ├── api/
    │   ├── types.ts          # TS mirrors of TaskRecord, Editorial, events (string-literal unions)
    │   ├── client.ts         # fetch wrappers (config, createTask, getTask, answerClarification)
    │   └── events.ts         # WS URL builder + message parsing/type guards
    ├── context/TaskContext.tsx   # Context + useReducer (D-07)
    ├── hooks/useTaskEvents.ts    # WS lifecycle, reconnect backoff, StrictMode-safe
    ├── pages/ ProblemInput.tsx, StatusView.tsx, EditorialView.tsx
    ├── components/ ClarificationModal.tsx, CodeBlock.tsx, ExampleList.tsx,
    │               StatusIndicator.tsx, InlineText.tsx
    └── lib/ statusLabels.ts (Russian labels), inlineCode.ts
docker/nginx/nginx.conf       # gateway: /api/ (HTTP+WS) → api:8000, / → frontend:3000
docs/ …                       # see Documentation section
DEFERRED.md
```

### Pattern 1: Publish-on-write (centralized status transitions)

**What:** Every function in `storage/tasks.py` that changes `status` gets `RETURNING updated_at`, then calls `publish_status(task_id, status, updated_at)` from `realtime/publisher.py`. The publisher never raises: it logs and returns, like the existing "Pattern 11" `emit_status`.
**Why this ordering:** Postgres is written **before** Redis. So any event a subscriber receives is already reflected in (or older than) a snapshot read taken after subscribing. The timestamp is the Postgres `updated_at`, which gives one clock for snapshot and events.
**Functions to change** [VERIFIED: src/algorunner/storage/tasks.py:43-131]: `update_task_status`, `update_task_completed`, `update_task_clarification`, `attempt_consume_clarification` (publish only when a row is returned), `update_task_failed`. **Not** `add_active_execution_seconds` (no status change) or `insert_task` (no subscriber can exist yet; the snapshot covers `queued`).
**D-01 compatibility:** Redis stays the fast notification path and Postgres the authoritative store. A publish failure never fails the Postgres write or the task. The status-publishing hooks sit on node boundaries through the existing `status_sink`.

```python
# src/algorunner/realtime/events.py  (discretion: exact schema)
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel
from algorunner.schemas.task import TaskRecord, TaskStatus

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED}
SNAPSHOT_REFRESH = {TaskStatus.AWAITING_CLARIFICATION, *TERMINAL}

def channel_for(task_id: UUID | str) -> str:
    return f"task:{task_id}:status"          # D-05 (locked)

class StatusEvent(BaseModel):                # D-03 + a `type` discriminator
    type: Literal["status"] = "status"
    status: TaskStatus
    timestamp: datetime                      # = tasks.updated_at of that write

class SnapshotEvent(BaseModel):              # D-02
    type: Literal["snapshot"] = "snapshot"
    task: TaskRecord
```

```python
# src/algorunner/realtime/publisher.py
import logging
from datetime import datetime
from functools import lru_cache
from uuid import UUID
import redis.asyncio as redis
from algorunner.config import settings
from algorunner.realtime.events import StatusEvent, channel_for
from algorunner.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

@lru_cache
def get_publisher_redis() -> redis.Redis:
    # Short timeouts: an unreachable Redis must never stall a worker node.
    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)

async def publish_status(task_id: UUID | str, status: TaskStatus, ts: datetime) -> None:
    try:
        event = StatusEvent(status=status, timestamp=ts)
        await get_publisher_redis().publish(channel_for(task_id), event.model_dump_json())
    except Exception as exc:  # never fail the task for a notification
        logger.warning("publish_status failed for %s (%s): %s: %s",
                       task_id, status.value, type(exc).__name__, exc)
```

```python
# storage/tasks.py: example transformation (keep %s placeholders)
async def update_task_status(pool, task_id: UUID, status: TaskStatus) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE tasks SET status = %s, updated_at = now() WHERE id = %s RETURNING updated_at",
            (status.value, task_id),
        )
        row = await cur.fetchone()          # pool row_factory is dict_row
    if row is not None:
        await publish_status(task_id, status, row["updated_at"])
```

### Pattern 2: Emit the 4 missing statuses from the per-approach subgraph

**What:** Wrap subgraph nodes in `build_approach_graph` with a thin status-emitting wrapper. Agent node signatures are `async def solver_node(state: ApproachState) -> dict` (state only) [VERIFIED: grep of agents/*/node.py], so the wrapper takes `runtime` and calls the node with `state`.
**Context propagation (verified):** `run_approach` calls `graph.ainvoke(branch_state)` without `context=`. LangGraph 1.2.12 merges the parent runtime: `runtime = parent_runtime.merge(runtime)`, and `merge` does `context=other.context or self.context` [VERIFIED: .venv/.../langgraph/pregel/main.py:3310-3325, langgraph/runtime.py:240-258]. `runtime.context` inside subgraph nodes is therefore the parent's `PipelineContext` (the existing `persist_iteration_node` already relies on this).

| Subgraph node | Emit before running | Rule |
|---|---|---|
| `solver` | `CORRECTING` | only when `state["iterations"] > 0` (reviewer increments `iterations`: `"iterations": state["iterations"] + 1` [VERIFIED: agents/reviewer/node.py:70]) |
| `code_generator` | `CORRECTING` if `iterations > 0`, else nothing (`GENERATING_CODE` already emitted by `run_approach`) | — |
| `test_generator` | `GENERATING_TESTS` | always |
| `execute_python` | `EXECUTING_TESTS` | always (skip `execute_go`: same status) |
| `reviewer` | `REVIEWING` | always |

```python
# graph/approach.py
from collections.abc import Awaitable, Callable
def _with_status(node: Callable[[ApproachState], Awaitable[dict]],
                 status_for: Callable[[ApproachState], TaskStatus | None]):
    async def wrapped(state: ApproachState, runtime: Runtime[PipelineContext]) -> dict:
        status = status_for(state)
        if status is not None:
            await emit_status(runtime.context, state["task_id"], status)
        return await node(state)
    wrapped.__name__ = getattr(node, "__name__", "wrapped")
    return wrapped
# builder.add_node("reviewer", _with_status(reviewer_node, lambda s: TaskStatus.REVIEWING))
```
**Consequence to document:** with N parallel approaches, the task-level status interleaves (branch 0 `reviewing`, branch 1 `generating_tests`, …). Postgres stores the last write. This is accepted: D-03 forbids approach-index context in events. The UI should show "latest status + history", not a monotonic progress bar.

### Pattern 3: WebSocket relay handler (API-04 + API-05)

```python
# src/algorunner/api/routes/events.py
import asyncio, logging
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from algorunner.realtime.events import (SNAPSHOT_REFRESH, TERMINAL, SnapshotEvent,
                                        StatusEvent, channel_for)
from algorunner.storage.tasks import get_task

router = APIRouter(prefix="/api/v1/tasks", tags=["events"])
logger = logging.getLogger(__name__)

@router.websocket("/{task_id}/events")
async def task_events(websocket: WebSocket, task_id: UUID) -> None:
    pool = websocket.app.state.pg_pool
    redis_client = websocket.app.state.redis
    await websocket.accept()
    async with redis_client.pubsub(ignore_subscribe_messages=True) as pubsub:
        await pubsub.subscribe(channel_for(task_id))          # 1. SUBSCRIBE FIRST
        task = await get_task(pool, task_id)                  # 2. THEN snapshot
        if task is None:
            await websocket.close(code=4404, reason="task not found")
            return
        await websocket.send_text(SnapshotEvent(task=task).model_dump_json())
        if task.status in TERMINAL:
            await websocket.close(code=1000)
            return
        last_ts = task.updated_at

        async def forward() -> None:
            nonlocal last_ts
            while True:
                msg = await pubsub.get_message(timeout=None)   # blocks; cancellable
                if msg is None:
                    continue
                try:
                    event = StatusEvent.model_validate_json(msg["data"])
                except ValidationError:
                    logger.warning("dropping malformed event on %s", channel_for(task_id))
                    continue
                if event.timestamp <= last_ts:                 # already in snapshot
                    continue
                last_ts = event.timestamp
                await websocket.send_text(event.model_dump_json())
                if event.status in SNAPSHOT_REFRESH:
                    fresh = await get_task(pool, task_id)
                    if fresh is not None:
                        await websocket.send_text(SnapshotEvent(task=fresh).model_dump_json())
                if event.status in TERMINAL:
                    await websocket.close(code=1000)
                    return

        async def drain_client() -> None:                     # detects disconnect
            while True:
                await websocket.receive_text()

        tasks = [asyncio.create_task(forward()), asyncio.create_task(drain_client())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                logger.warning("ws relay for %s ended: %r", task_id, exc)
                # Redis dropped etc.: close 1011 so the client reconnects and resyncs
                try: await websocket.close(code=1011)
                except RuntimeError: pass
```
Key points:
- `async with redis_client.pubsub()` guarantees unsubscribe and connection release on every exit path (`aclose` exists on redis-py 8.1.0 `PubSub`) [VERIFIED: introspection: `['aclose', 'close', 'reset', 'subscribe', 'unsubscribe', 'listen', '__aenter__']`].
- `get_message` signature: `(self, ignore_subscribe_messages: bool = False, timeout: float | None = 0.0)` [VERIFIED: inspect]. `timeout=None` blocks until a message arrives. `timeout=0.0` (the default) busy-polls, so never loop on the default.
- Use a **separate** Redis client for the API subscriber (`app.state.redis`) **without** `socket_timeout`. A socket read timeout would break a blocking `get_message(timeout=None)` on a quiet channel. The short-timeout client is the publisher's.
- Close codes: `4404` for unknown task (application range 4000-4999). `1000` normal after terminal. `1011` on server error so the client knows to reconnect.
- **Disconnect-safe even while nothing is published:** `drain_client` observes `WebSocketDisconnect` promptly.

### Pattern 4: Dependencies usable from WS routes

`get_pg_pool(request: Request)` [VERIFIED: src/algorunner/api/dependencies.py:5-6] **cannot be injected into a WebSocket route**. FastAPI only fills a `Request`-typed parameter when `isinstance(request, Request)` [VERIFIED: .venv/.../fastapi/dependencies/utils.py:709-714]:
```
    if dependant.http_connection_param_name:
        values[dependant.http_connection_param_name] = request
    if dependant.request_param_name and isinstance(request, Request):
        values[dependant.request_param_name] = request
```
Either retype the dependency to `conn: HTTPConnection` (works for both HTTP and WS; existing HTTP callers keep working) or read `websocket.app.state` directly as in Pattern 3. Add `app.state.redis = redis.Redis.from_url(settings.redis_url)` in `lifespan` and `await app.state.redis.aclose()` in its `finally`.

The body-size middleware (`@app.middleware("http")`) does not touch WS: Starlette `BaseHTTPMiddleware` passes non-http scopes straight through (`if scope["type"] != "http": await self.app(scope, receive, send); return`) [VERIFIED: .venv/.../starlette/middleware/base.py:102-104].

### Pattern 5: `GET /api/config` (D-20)

Return an explicit allow-listed schema. **Never** serialize `Settings` (it holds `openai_api_key`, Garage secrets [VERIFIED: config.py:20-27]).
```python
class ClientConfig(BaseModel):
    api_base_url: str = "/api/v1"          # relative → same-origin through nginx or Vite proxy
    ws_base_url: str | None = None          # None → client derives from window.location
    max_problem_chars: int = 5000           # mirrors TaskSubmission
    max_examples: int = 10
```
The frontend fetches `/api/config` (relative, same-origin) at startup. If `ws_base_url` is null it builds `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${api_base_url}/tasks/${id}/events`. Router mount: `APIRouter(prefix="/api")` with `@router.get("/config")` (not under `/api/v1`, per D-20).

### Pattern 6: Frontend WS hook (StrictMode-safe, reconnect + resync)

```ts
// src/hooks/useTaskEvents.ts: sketch
export function useTaskEvents(taskId: string | null, wsBase: string, dispatch: Dispatch<Action>) {
  useEffect(() => {
    if (!taskId) return;
    let socket: WebSocket | null = null;
    let attempt = 0;
    let stopped = false;               // StrictMode mounts/unmounts twice in dev
    let timer: number | undefined;
    const connect = () => {
      socket = new WebSocket(`${wsBase}/tasks/${taskId}/events`);
      socket.onopen = () => { attempt = 0; };
      socket.onmessage = (e) => {
        const msg = parseServerMessage(e.data);        // type guard, never `as any`
        if (!msg) return;
        if (msg.type === "snapshot") dispatch({ type: "SNAPSHOT", task: msg.task });
        else dispatch({ type: "STATUS_EVENT", event: msg });
      };
      socket.onclose = (e) => {
        if (stopped || e.code === 1000 || e.code === 4404) return;   // terminal / not found
        const delay = Math.min(1000 * 2 ** attempt++, 10_000);       // 1s,2s,4s… cap 10s
        timer = window.setTimeout(connect, delay);                   // new snapshot resyncs
      };
    };
    connect();
    return () => { stopped = true; window.clearTimeout(timer); socket?.close(1000); };
  }, [taskId, wsBase, dispatch]);
}
```
Reducer rules: `SNAPSHOT` replaces task state wholesale. `STATUS_EVENT` appends to history and sets `status` (dedupe consecutive identical statuses for display). When `status === "awaiting_clarification"` and `task.clarification_question` is set, open the modal. On `completed`, render `EditorialView` from `task.result`.

### Pattern 7: Clarification flow (UI-03)

- The question comes from the snapshot's `task.clarification_question`. The server re-sends the snapshot on the `awaiting_clarification` event (Pattern 3). A fallback is `GET /api/v1/tasks/{id}/clarification` → `{question}` (404 if not pending) [VERIFIED: api/routes/tasks.py:38-45].
- Submit: `POST /api/v1/tasks/{id}/clarification` body `{answer}` (`answer: str = Field(..., max_length=5000)` [VERIFIED: schemas/clarification.py:13-14]) → `202 {task_id, status: "analyzing_problem"}`. A 409 means "already answered or not awaiting" (e.g. a second tab): close the modal and rely on the stream.
- Can recur: `clarification_round_cap: int = 2` [VERIFIED: config.py:40]. The modal must reopen on a second `awaiting_clarification`.
- No backend "skip" exists. Recommend no skip button in v1 (the modal can be dismissed only by submitting).

### Pattern 8: Editorial rendering (UI-04)

TS types must mirror (verbatim values):
- `difficulty: Literal["easy", "medium", "hard"]` [VERIFIED: schemas/editorial.py:120]
- `ApproachRole = Literal["brute_force", "optimized", "alternative"]` [VERIFIED: schemas/solution.py:30] (note: the same line is duplicated at :26, harmless)
- `UnverifiedApproach.status: Literal["exhausted", "timed_out", "errored"]` [VERIFIED: schemas/editorial.py:106]
- `Editorial` fields: `problem_restatement: str`, `difficulty`, `tags: list[str]`, `approaches: list[EditorialApproach]`, `edge_cases: list[str]`, `unverified_approaches: list[UnverifiedApproach]` [VERIFIED: schemas/editorial.py:119-124]
- `EditorialApproach` fields: `approach_id, role, technique, title, bridge_from_previous (str|None), intuition, algorithm, code_python, code_go, complexity_time, complexity_space, complexity_justification, notes: list[str]` [VERIFIED: schemas/editorial.py:58-70]
- `result` (completed) = `{approaches: [...index], editorial?: Editorial, editorial_warnings: [...], artifact_keys: [...], artifacts_incomplete: bool}`, where `approaches` index items are `{approach_id, name, technique, role, status, iterations}` [VERIFIED: graph/build.py:118-147]. **`result.editorial` may be absent** on pre-Phase-3 rows ("Phase 4 UI must tolerate a missing result.editorial" [VERIFIED: graph/build.py:17-18]). Render a fallback message.
- `ApproachStatus = Literal["verified", "exhausted", "timed_out", "errored"]` [VERIFIED: schemas/outcome.py:15]
- Failed: `error: {code, message}` (`TaskError` [VERIFIED: schemas/task.py:52-56]).

Prose: the Writer is told to "Wrap identifiers and variable names in backticks" [VERIFIED: agents/editorial_writer/prompts.py system prompt]. Render prose as React text with `whitespace-pre-line`. Split on backticks into `<code>` elements (tiny pure function, unit-testable). **No `dangerouslySetInnerHTML` for prose.**

Code: `hljs.highlight(code, { language: "python" | "go" }).value` inside `useMemo`, injected into `<pre><code className="hljs">` via `dangerouslySetInnerHTML`. This is the only sanctioned innerHTML: hljs escapes the source text (add a vitest asserting `<script>` → `&lt;script&gt;`). The copy button uses `navigator.clipboard.writeText(code)` with the **raw** code string. Note that the Clipboard API requires a secure context; `http://localhost` qualifies, but a plain-HTTP non-localhost host does not, so fall back to a hidden textarea + `document.execCommand('copy')` or show "select manually" [ASSUMED].

### Pattern 9: nginx gateway + frontend container

```nginx
# docker/nginx/nginx.conf (gateway, port 80)
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
server {
  listen 80;
  client_max_body_size 128k;                 # API caps bodies at 100_000 bytes (main.py)
  location /api/ {
    proxy_pass http://api:8000;              # NOT 5000; see corrections table
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;                # tasks run up to global_timeout_s=1200
    proxy_send_timeout 3600s;
  }
  location / {
    proxy_pass http://frontend:3000;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
  }
}
```
nginx official docs: "By default, the connection will be closed if the proxied server does not transmit any data within 60 seconds. This timeout can be increased with the proxy_read_timeout directive. Alternatively, the proxied server can be configured to periodically send WebSocket ping frames" [CITED: nginx.org/en/docs/http/websocket.html]. Uvicorn already pings every 20 s (verified above). Setting `proxy_read_timeout` too is belt-and-braces.

Frontend container: stage 1 `node:24-alpine` (`npm ci && npm run build`), stage 2 `nginx:alpine` with `listen 3000; root /usr/share/nginx/html; location / { try_files $uri /index.html; }`. Cache headers: `location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }` (Vite hashes filenames under `assets/`) and `index.html` `no-cache` [ASSUMED: image tags; this sandbox could not reach the Docker registry].

Compose additions: `frontend` (build `./frontend`, no host port) and `nginx` (`image: nginx:alpine`, `ports: ["80:80"]`, mount `./docker/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro`, `depends_on: [api, frontend]`). Keep `api`'s `8000:8000` host port for dev/tests.

Vite dev proxy (local dev without Docker):
```ts
server: { proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true } } }
```
[CITED: vite.dev docs server.proxy via Context7]. Vite warns: "Vite does not check the origin of WebSocket requests before proxying. The proxy target is expected to check the `Origin` header". Do **not** set `rewriteWsOrigin`.

### Anti-Patterns to Avoid

- **Snapshot before subscribe.** A transition that lands between the read and the SUBSCRIBE is lost forever. Always SUBSCRIBE → read → send.
- **Publishing before the Postgres write.** Breaks the timestamp dedupe invariant and makes the terminal-snapshot re-read race (the result might not be committed yet).
- **Polling Postgres from the WS handler.** Explicitly rejected in CLAUDE.md stack notes. Redis is the live channel.
- **`get_message()` with the default `timeout=0.0` in a `while True`.** Busy loop at 100% CPU.
- **Sharing one `PubSub` object across WebSocket connections.** Not safe. One per connection (or the deferred shared-psubscribe design).
- **TS `enum` for statuses.** The template sets `"erasableSyntaxOnly": true` [VERIFIED: create-vite template tsconfig.app.json], which rejects `enum`. Use `as const` arrays + string-literal unions.
- **Rendering LLM prose with `dangerouslySetInnerHTML` / a markdown-to-HTML lib.** XSS vector. Use React text nodes.
- **Hand-editing inside `<!-- GSD:…-start -->` blocks of `.claude/CLAUDE.md`.** Overwritten on the next `generate-claude-md` (Pitfall 9).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Syntax highlighting | Regex tokenizer | `highlight.js/lib/core` + `python`, `go` languages | Escaping and tokenizer edge cases |
| WS keepalive through proxies | App-level heartbeat messages | uvicorn's built-in WS ping (20 s) + nginx `proxy_read_timeout` | Already there. Protocol pings are invisible to the app |
| Pub/Sub connection lifecycle | Manual subscribe/unsubscribe bookkeeping | `async with client.pubsub() as ps:` | Guarantees cleanup on cancellation |
| JSON event (de)serialization | `json.dumps(dict)` / manual parse | Pydantic `model_dump_json()` / `model_validate_json()` | ISO-8601 datetimes and enum validation for free, matching the project convention (ORCH-02) |
| CSS framework | Custom CSS files | Tailwind v4 utilities (D-11) | Locked |
| Routing library | react-router | `?task=<uuid>` via `URLSearchParams` + `history.replaceState`, view derived from state | Three views, no nested routes. A refresh re-attaches the WS (exercises API-05 for free) |

**Key insight:** Nearly all the realtime difficulty sits in ordering (subscribe vs snapshot vs write vs publish). Get that invariant right in Python, and the frontend becomes a dumb renderer of snapshot + deltas.

## Common Pitfalls

### Pitfall 1: Lost or stale events on late connect (API-05)
**What goes wrong:** The client shows `analyzing_problem` while the task is already `reviewing`, or misses `completed` and spins forever.
**Why:** Snapshot and subscription are not ordered; events carry no comparable timestamp.
**How to avoid:** Pattern 1 + Pattern 3 (write→publish; subscribe→snapshot; drop `ts <= last_ts`; snapshot refresh on clarification/terminal).
**Warning signs:** An integration test that publishes during the handler's snapshot read yields a missing or duplicated status.

### Pitfall 2: The four "missing" statuses
**What goes wrong:** Success criterion 1 fails. The UI jumps from `generating_code` straight to `writing_editorial`.
**How to avoid:** Pattern 2 wrappers. Add a graph test that runs the approach subgraph with a recording `status_sink` and asserts `GENERATING_TESTS`, `EXECUTING_TESTS`, `REVIEWING`, and `CORRECTING` (on a forced review failure) are all recorded. `tests/graph/test_correction_loop.py` already forces review failures.

### Pitfall 3: Testing WS with Starlette `TestClient` breaks the session-scoped pg pool
**What goes wrong:** Hangs or "attached to a different loop" errors.
**Why:** `TestClient` runs the ASGI app in a separate thread/event loop through an anyio portal [VERIFIED: .venv/.../starlette/testclient.py:19,117-118]. The project's `pg_pool` fixture is session-scoped on the pytest loop (`asyncio_default_fixture_loop_scope = "session"` [VERIFIED: pyproject.toml:42-43]). httpx `ASGITransport` (used by `app_client`) does not support WebSockets.
**How to avoid:** For integration tests, start `uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=<free port>, lifespan="off"))` as an `asyncio.create_task(server.serve())` **on the same loop**. Wait for `server.started`. Pre-set `app.state.pg_pool = pg_pool` and `app.state.redis = …` the way `app_client` does. Connect with `websockets.asyncio.client.connect`. Use `lifespan="off"` because the real lifespan's `finally` would `pool.close()` the shared memoized pool. Also unit-test the relay ordering logic with Redis + fake publishes.

### Pitfall 4: nginx kills idle WebSockets after 60 s
**What goes wrong:** Long LLM steps (reviewer or editorial calls can exceed 60 s) sever the socket. The client reconnects (fine), but logs fill with churn, or it breaks entirely if reconnect is buggy.
**How to avoid:** `proxy_read_timeout 3600s` + uvicorn's default 20 s pings (Pattern 9).

### Pitfall 5: `Request`-typed dependency in a WS route
See Pattern 4. Symptom: 403 or a validation error on WS handshake.

### Pitfall 6: React StrictMode double effects
**What goes wrong:** In dev, two sockets open, or the first socket's `onclose` schedules a reconnect after unmount, leaking sockets.
**How to avoid:** A `stopped` flag in effect cleanup (Pattern 6), and close with 1000 in cleanup.

### Pitfall 7: Parallel-branch status flip-flop
**What goes wrong:** Users read `reviewing → generating_tests` as a regression. Tests asserting monotonic status order become flaky.
**How to avoid:** Document it in `docs/architecture/workflow.md`. The UI shows latest status plus a deduped history list, not a strictly ordered stepper. Tests assert set membership, not order, for branch statuses.

### Pitfall 8: Publisher Redis client hanging the worker
**What goes wrong:** Redis down or DNS stall, and every `emit_status` blocks a node.
**How to avoid:** Set `socket_connect_timeout`/`socket_timeout` on the **publisher** client only, and catch all exceptions (Pattern 1). Do not set `socket_timeout` on the API subscriber client (Pattern 3).

### Pitfall 9: GSD-regenerated CLAUDE.md sections
**What goes wrong:** Frontend conventions written under `## Conventions` disappear on the next `/gsd-*` regeneration.
**Why:** `generate-claude-md` replaces everything between `<!-- GSD:{section}-start` and `<!-- GSD:{section}-end -->` for `project, stack, conventions, architecture, skills, workflow`. It **preserves content outside markers** (`before + newContent + after`). The conventions section is sourced from `.planning/codebase/CONVENTIONS.md` [VERIFIED: ~/.claude/gsd-core/bin/lib/profile-output.cjs:262-271, 374-377, 1002].
**How to avoid:** Add a hand-authored `## Repository Rules` section (backend + frontend conventions, doc index) **outside all GSD markers** in `.claude/CLAUDE.md`. Optionally also create `.planning/codebase/CONVENTIONS.md` so the managed section stops saying "Conventions not yet established".

### Pitfall 10: Form/server limit drift
**What goes wrong:** The UI allows 11 examples or 6000 chars and the user gets a raw 422.
**How to avoid:** Mirror `problem_text: str = Field(..., max_length=5000)`, `examples: list[Example] = Field(default_factory=list, max_length=10)`, and `language: Language` (`EN = "en"`, `RU = "ru"`) [VERIFIED: schemas/task.py:15-29]. Also render 422 `detail` messages readably. `Example` = `input: str`, `output: str`, `explanation: str | None = None` [VERIFIED: schemas/task.py:20-23]. Drop fully empty example rows before submit (D-specifics: both fields are required if a row is present).

## Code Examples

### Status taxonomy mirrored in TS (values verbatim from backend)
Backend source [VERIFIED: src/algorunner/schemas/task.py:38-49]:
```
    QUEUED = "queued"
    ANALYZING_PROBLEM = "analyzing_problem"
    DESIGNING_SOLUTION = "designing_solution"
    GENERATING_CODE = "generating_code"
    GENERATING_TESTS = "generating_tests"
    EXECUTING_TESTS = "executing_tests"
    REVIEWING = "reviewing"
    CORRECTING = "correcting"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    WRITING_EDITORIAL = "writing_editorial"
    COMPLETED = "completed"
    FAILED = "failed"
```
```ts
// frontend/src/api/types.ts
export const TASK_STATUSES = [
  "queued", "analyzing_problem", "designing_solution", "generating_code",
  "generating_tests", "executing_tests", "reviewing", "correcting",
  "awaiting_clarification", "writing_editorial", "completed", "failed",
] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];
export const TERMINAL: ReadonlySet<TaskStatus> = new Set(["completed", "failed"]);
```
`TaskRecord` fields to mirror [VERIFIED: src/algorunner/schemas/task.py:59-70]: `id: UUID`, `status: TaskStatus`, `problem_text: str`, `language: Language`, `examples: list[Example]`, `result: dict | None = None`, `error: TaskError | None = None`, `clarification_question: str | None = None`, `active_execution_seconds: float = 0.0`, `created_at: datetime`, `updated_at: datetime`.

### Tailwind v4 + hljs wiring
```ts
// vite.config.ts
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true, ws: true } } },
});
```
```css
/* src/index.css */
@import "tailwindcss";
@import "highlight.js/styles/github-dark.css";
```
```ts
// src/lib/highlight.ts
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import go from "highlight.js/lib/languages/go";
hljs.registerLanguage("python", python);
hljs.registerLanguage("go", go);
export const highlight = (code: string, language: "python" | "go"): string =>
  hljs.highlight(code, { language }).value;   // escaped HTML
```
Sources: [CITED: tailwindcss.com/docs installation], [CITED: highlight.js README "hljs.registerLanguage … hljs.highlight(…, {language}).value"]. The `github-dark.css` theme path is [ASSUMED]; check `node_modules/highlight.js/styles/` after install.

### Russian status labels (UI output language is Russian)
Put these in one `statusLabels.ts` map (e.g. `analyzing_problem: "Анализ задачи"`, `reviewing: "Ревью решения"`, `correcting: "Исправление"`, …). Exhaustiveness is enforced by typing it as `Record<TaskStatus, string>`.

## Documentation (INFRA-05)

Files required by success criterion 3 (create **all** of them. D-16 allows consolidation, but the success criterion enumerates each path and the verifier will check them literally):

| File | Content (terse, D-13) | Primary inputs |
|---|---|---|
| `.claude/CLAUDE.md` (hand-authored section outside markers) | Repo rules: layout, uv/npm commands, backend conventions (async-only I/O, `%s` SQL, Pydantic contracts, emit_status pattern), frontend conventions (component/file naming, Context+reducer, no `enum`, no innerHTML except hljs), doc index | Pitfall 9, this research |
| `docs/product/prd.md` | Problem, users, user stories + acceptance criteria per requirement group, out-of-scope, link to DEFERRED.md | REQUIREMENTS.md, PROJECT.md, interview.md |
| `docs/architecture/architecture.md` | Container boxes (nginx, frontend, api, worker, postgres, redis, garage), data flow, decision log (D-xx highlights from phases 1-4) | ROADMAP, phase CONTEXT files |
| `docs/architecture/agents.md` | Each agent node: purpose, input/output schema, model override setting (`problem_analyzer_model` … `reviewer_model` [VERIFIED: config.py:31-37]) | `src/algorunner/agents/*` |
| `docs/architecture/workflow.md` | Parent graph + approach subgraph, correction loop, clarification interrupt, budget/timeout, **status taxonomy and emit points**, WS event protocol (snapshot/status, close codes), flip-flop note | graph/build.py, graph/approach.py, this research |
| `docs/architecture/data-model.md` | `tasks` table (migrations 0001/0002), `result` JSON shape, `Editorial` schema, Garage key layout `tasks/{task_id}/analysis.json`, `tasks/{task_id}/approaches/{idx}/iter-{n}/{kind}.json`, `tasks/{task_id}/approaches/{idx}/summary.json`, `tasks/{task_id}/editorial.json` [VERIFIED: storage/artifacts.py:171,198,219,236], Redis channel `task:{task_id}:status`, LangGraph checkpoint tables | migrations/*.sql, schemas/*, storage/artifacts.py |
| `docs/development/testing.md` | pytest setup (docker compose deps, session loop scope), mock_openai fixtures, live probes (`scripts/verify_phase3_live.py`, new phase 4 probe), frontend `npm run build` / vitest | tests/conftest.py, pyproject.toml |
| `docs/development/conventions.md` | Code style details (can be the long form behind the CLAUDE.md summary) | — |
| `docs/plans/implementation-plan.md` | Milestone/phase/plan breakdown (phases 1-4 with plan lists) | ROADMAP.md, phase dirs |
| `DEFERRED.md` (root) | "Deferred / Future Scope" dedicated section: every CONTEXT deferred idea + v2 REQUIREMENTS (SEC-01..03, PLAT-01..03, PROD-01..04, EVAL-01..02) + shared-psubscribe WS fan-out, with brief description + estimated phase/effort | REQUIREMENTS.md v2, 04-CONTEXT deferred |

Also: `README.md` is currently **empty (0 bytes)** [VERIFIED: ls -la]. A short README (quickstart: `docker compose up`, open `http://localhost`, doc index) is cheap and expected. Recommend including it even though it is not listed.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@tailwind base; @tailwind components; @tailwind utilities;` + `tailwind.config.js` + PostCSS | `@import "tailwindcss";` + `@tailwindcss/vite` plugin, CSS-first `@theme` | Tailwind v4 | No config file, no PostCSS setup [CITED: tailwindcss.com upgrade guide] |
| Create React App | Vite `create-vite` templates | CRA deprecated | Locked D-06 |
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI (already used here) | Put redis client init in the existing lifespan |
| redis-py `PubSub.close()` | `aclose()` | redis-py 5.x+ | Use `async with` / `aclose` |
| nginx `proxy_http_version 1.1` required for WS | Default since nginx 1.29.7 per official doc comment | nginx 1.29.7 | Keep the directive anyway (harmless, works on older images) [CITED: nginx.org websocket doc] |
| TS `enum` | `as const` + unions (`erasableSyntaxOnly`) | TS 5.8+/template default | No enums in frontend code |

**Deprecated/outdated:** CLAUDE.md stack notes name the channel `task:{task_id}:events`. **D-05 locks `task:{task_id}:status`**, so use D-05.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Docker image tags `node:24-alpine`, `nginx:alpine` exist and Node 24 is the right LTS for the build stage (registry unreachable from this sandbox) | Pattern 9 | Build fails at `docker build`. Trivially fixed by retagging (e.g. `node:26-alpine`, which vitest/vite engines also allow) |
| A2 | `highlight.js/styles/github-dark.css` is the theme path in 11.12.0 | Code Examples | CSS import fails at build. Pick any file in `node_modules/highlight.js/styles/` |
| A3 | Clipboard API needs a secure context; `http://localhost` counts as secure | Pattern 8 | Copy button silently fails on a non-localhost HTTP deploy. Fallback covers it |
| A4 | TS ~6.0 template config lacks an explicit `"strict": true`, so it must be added for "maximum type safety" (whether 6.0 defaults strict on is unverified) | Standard Stack | None if added explicitly |
| A5 | Per-connection Pub/Sub (one Redis connection per open WS) is acceptable at v1 scale | Alternatives | Redis connection exhaustion under many viewers. Mitigate with a WS connection cap (Security) |
| A6 | Interpreting D-01 "Postgres status writes happen separately" as compatible with write-then-publish inside the same storage function (publish failure isolated) | Pattern 1 | If the user meant Redis-first publishing, the timestamp-dedupe invariant breaks. **Confirm with the user in plan-check** |

## Open Questions

1. **Root `CLAUDE.md` vs `.claude/CLAUDE.md`.**
   - What we know: INFRA-05 and success criterion 3 say `CLAUDE.md`. D-14 says "update existing" (the existing file is `.claude/CLAUDE.md`, which `config.json` sets as `claude_md_path`). D-16 lists "`CLAUDE.md` (root)".
   - Unclear: whether a verifier expects a repo-root file.
   - Recommendation: honor D-14 (single source of truth in `.claude/CLAUDE.md`, outside GSD markers) and state this path explicitly in the plan's must-haves. Ask the user once at plan-check. Do not create two diverging rule files.
2. **Should the WS endpoint enforce an Origin allowlist?**
   - What we know: no auth or cookies exist, so cross-site WS hijacking leaks only what `GET /tasks/{id}` already exposes to anyone holding the UUID.
   - Recommendation: add an optional `ws_allowed_origins: list[str]` setting (empty = allow all) and document it. Low effort, and it answers Vite's "target should check Origin" warning.
3. **`frontend` compose service in dev mode?** D-21 says "Vite dev or nginx for prod". Recommend the compose service is always the built nginx image; local dev runs `npm run dev` on the host against `api` on :8000.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Vite dev/build, vitest | ✓ | v26.7.0 (host) | Docker build stage uses its own Node |
| npm | frontend deps | ✓ | 11.19.0 | pnpm available (/opt/homebrew/bin/pnpm), but stick to npm for `npm ci` |
| Docker / Compose | 7-service stack, frontend image | ✓ | 27.4.0 / v2.31.0 | — |
| Redis (compose) | pub/sub, tests | ✓ running | redis:8 (`algorunner-redis-1` healthy) | — |
| Postgres (compose) | snapshot, tests | ✓ running | postgres:18 | — |
| Go | existing executor tests | ✓ | go1.26.3 | — |
| Docker Hub registry reachability | pulling node/nginx images | ✗ from this sandbox (`docker manifest inspect` failed for all tags) | — | Executor's normal environment. Verify at first `docker compose build` |

**Missing dependencies with no fallback:** none (registry reachability is a sandbox limitation, not a project blocker).

## Validation Architecture

Skipped: `workflow.nyquist_validation` is `false` in `.planning/config.json`. Minimal test guidance for the planner:
- Backend: pytest (existing, `asyncio_mode = "auto"`). New tests: `tests/realtime/test_publisher.py` (publish/no-raise), `tests/storage/…` (RETURNING + publish order), `tests/graph/test_status_emission.py` (4 new statuses), `tests/api/test_events_ws.py` (same-loop uvicorn fixture: snapshot-first, late connect, terminal close, 4404, dedupe), `tests/api/test_config.py` (no secret keys in payload).
- Frontend: `npm run build` (runs `tsc -b`) as the type gate, plus vitest for reducer, `inlineCode`, WS URL builder, and hljs escaping.
- Live: `scripts/verify_phase4_live.py` (submit → WS stream sees ≥1 intermediate status → terminal snapshot with `result.editorial`), plus a `checkpoint:human-verify` walkthrough of the UI at `http://localhost` (UI hint: yes; `ui_phase` is enabled, so a UI-SPEC may be produced by `/gsd-ui-phase`).

## Security Domain

`security_enforcement: true`, ASVS level 1, block on `high`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (deferred SEC-01) | Document in DEFERRED.md. UUID4 task IDs act as unguessable capabilities |
| V3 Session Management | no | No sessions or cookies |
| V4 Access Control | partial | Anyone with a task UUID can read or stream it. Accepted for v1 and documented |
| V5 Input Validation | yes | `task_id: UUID` path param (FastAPI rejects malformed); inbound WS client messages ignored (drained, never parsed); Redis payloads validated by `StatusEvent.model_validate_json`; form limits mirror Pydantic |
| V6 Cryptography | no | TLS termination is out of scope for local compose (document) |
| V12/V14 Config & Headers | yes | `/api/config` allow-list (no secrets); nginx `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; optional CSP `default-src 'self'; connect-src 'self' ws: wss:; style-src 'self'` (verify that Vite's prod build has no inline scripts before enabling) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS through LLM-authored prose or code in the editorial | Tampering / Elevation | React text nodes for prose; hljs-escaped HTML only for code; vitest proves `<script>` is escaped |
| WS connection flood (each holds a Redis connection + coroutine) | DoS | Cap concurrent WS connections in-process (counter/semaphore, e.g. 200 → close 1013 "try again later"); nginx `limit_conn` optional; close on terminal status |
| Cross-site WebSocket hijacking | Info disclosure | Low impact (no auth). Optional Origin allowlist (Open Q2) |
| Secrets leak through `/api/config` | Info disclosure | Explicit `ClientConfig` model, never `settings.model_dump()`; test asserts no `key`/`secret` fields |
| Redis channel injection (malformed publish) | Tampering | Relay validates each message against `StatusEvent`, drops invalid ones; Redis not exposed publicly in prod (compose publishes 6379 for dev only; document) |
| Oversized bodies through nginx | DoS | `client_max_body_size 128k` in front of the existing 100 KB app-level cap |

## Sources

### Primary (HIGH confidence, read or executed this session)
- Repo files: `src/algorunner/schemas/{task,editorial,clarification,solution,outcome}.py`, `api/{main,dependencies}.py`, `api/routes/tasks.py`, `worker/{tasks,broker}.py`, `graph/{build,approach,context,routing}.py`, `storage/{tasks,postgres,artifacts}.py`, `config.py`, `docker-compose.yml`, `docker/Dockerfile.api`, `migrations/*.sql`, `pyproject.toml`, `tests/conftest.py`
- Installed package source: langgraph 1.2.12 `pregel/main.py`, `runtime.py`; fastapi `dependencies/utils.py`; starlette `middleware/base.py`, `testclient.py`; redis-py 8.1.0 and uvicorn 0.53.0 via `inspect`
- Live probe: redis-py async pub/sub against running `redis:8`
- npm registry (`npm view`), `create-vite@9.2.1` tarball template, gsd-tools package-legitimacy seam
- `~/.claude/gsd-core/bin/lib/profile-output.cjs` (CLAUDE.md regeneration semantics)

### Secondary (MEDIUM, official docs via Context7/WebFetch)
- /websites/fastapi_tiangolo (WebSockets, Depends, WebSocketException)
- /redis/redis-py (asyncio pub/sub examples, aclose)
- /websites/tailwindcss (v4 Vite install, `@import "tailwindcss"`)
- /highlightjs/highlight.js (core + registerLanguage, security wiki)
- /vitejs/vite (server.proxy `ws: true`, Origin-check warning)
- nginx.org/en/docs/http/websocket.html (Upgrade/Connection map, 60 s read timeout)

### Tertiary (LOW)
- Docker image tags (A1), hljs theme filename (A2), Clipboard secure-context behavior (A3)

## Metadata

**Confidence breakdown:**
- Backend realtime design: HIGH. Every integration point was read in source; the LangGraph context propagation and FastAPI/Starlette WS behavior were verified in installed code; the Redis API was probed live.
- Frontend stack: MEDIUM-HIGH. Versions come from the registry and the official scaffold template. Patterns are standard, but the Tailwind v4 and hljs specifics are doc-cited, not executed.
- Deployment (nginx/Docker): MEDIUM. nginx directives are from official docs; image tags are unverified.
- Documentation plan: HIGH. The file list is taken literally from the success criterion; CLAUDE.md regeneration behavior was verified in gsd-tools source.

**Research date:** 2026-09-25
**Valid until:** 2026-10-25 (frontend packages move fast; re-check `npm view` versions if planning slips past this)
