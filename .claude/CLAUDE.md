<!-- GSD:project-start source:PROJECT.md -->

## Project

**AlgoRunner**

Production-ready multi-agent system that takes a text description of a LeetCode-style algorithmic problem (English or Russian) and produces a LeetCode-editorial-style article in Russian: one or more solution approaches (e.g. brute-force and optimized), each with explanation, Python code, Go code, and asymptotic complexity. Built for students and developers preparing for technical interviews.

**Core Value:** Correctness of the generated solution — verified by actually executing the generated Python and Go code against generated (or provided) tests — matters more than explanation quality or speed.

### Constraints

- **Tech stack**: Python 3.14, LangGraph, OpenAI API (model configurable via env/config, with optional per-agent model overrides) — fixed by product owner
- **Package manager**: `uv` — fixed
- **Task queue**: taskiq + Redis (not Celery — too heavyweight; not ARQ — unsupported/unmaintained) — fixed
- **Database**: PostgreSQL — task state (source of truth) + LangGraph checkpoint storage
- **Artifact storage**: Garage (S3-compatible) for intermediate agent artifacts (analysis, solutions, review history, tests)
- **Frontend**: React + TypeScript, included in v1 (not deferred)
- **Deployment**: Docker Compose for this milestone; Kubernetes explicitly deferred
- **Type safety**: maximum feasible in Python (even though CI/lint tooling enforcement is deferred)
- **Architecture style**: simple modular architecture (not DDD/clean architecture) — explicit product-owner preference
- **Code execution**: Python via subprocess, Go via compile+run — both without sandboxing in v1
- **Language**: input text in English or Russian; output (editorial) always in Russian

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `langgraph` | latest 1.0.x line (`1.0.3`+ per Context7 registry as of research date) | Agent orchestration StateGraph | Already locked; 1.0 line is the current stable major, checkpoint API (`langgraph-checkpoint` v4.x) is what `langgraph-checkpoint-postgres` v3.1.2 targets |
| `langgraph-checkpoint-postgres` | `3.1.2` (requires `langgraph-checkpoint>=4.1.0,<5.0.0`) | PostgreSQL-backed checkpointer for StateGraph | Official first-party checkpointer package; only supported way to persist LangGraph state to Postgres |
| `psycopg[binary,pool]` (Psycopg 3) | `>=3.2.0` | Postgres driver under the checkpointer | `langgraph-checkpoint-postgres` depends on `psycopg>=3.2.0` and `psycopg-pool>=3.2.0` directly — do not bring in psycopg2 or asyncpg for this piece, it's psycopg3-only |
| `taskiq` | latest (`0.11.x`+ line) | Async task queue core (broker/worker framework) | Already locked; native `async def` task support, FastAPI-shaped lifespan integration, and per-task timeout labels are exactly what this project's node-graph-in-a-task model needs |
| `taskiq-redis` | latest | Redis broker + result backend implementations for taskiq | Provides `RedisStreamBroker` (acks, durable — recommended default), `ListQueueBroker` (simpler, no acks), and `PubSubBroker` (broadcast); provides `RedisAsyncResultBackend` |
| `openai` (Python SDK) | `>=1.68` (v1 line current at research date; v2 exists but confirm before adopting) | LLM calls with Structured Outputs | `client.chat.completions.parse(response_format=PydanticModel)` is the first-party, actively maintained path for schema-constrained inter-node contracts |
| `fastapi` | latest | REST + WebSocket API | Already locked; use `lifespan` context manager (not deprecated `@app.on_event`) to start/stop the taskiq broker client and Postgres/Redis connection pools |
| `pydantic` | v2.x | Schemas for OpenAI structured outputs, LangGraph state, and FastAPI request/response models | One schema library end-to-end: state, inter-node contracts, and API models all share the same validation semantics |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `psycopg-pool` | `>=3.2.0` (pulled in transitively) | `AsyncConnectionPool` for `AsyncPostgresSaver` | Production: open one pool per worker process at startup (taskiq `WORKER_STARTUP` event / FastAPI `lifespan`), pass to `AsyncPostgresSaver(pool)` rather than a single ad-hoc connection — a pooled connection also skips an internal asyncio.Lock the single-connection path needs, per LangGraph's own source comments |
| `redis` (redis-py, `redis.asyncio`) | latest | Direct Redis client for pub/sub bridging to WebSocket | Needed alongside `taskiq-redis` if you implement the FastAPI↔worker progress bridge yourself (see Architecture note below); `redis.asyncio.Redis.pubsub()` is the async API to subscribe from a WebSocket handler |
| `boto3` or `aioboto3` | latest | Garage (S3-compatible) client | Garage speaks the S3 API; `aioboto3` avoids blocking the FastAPI/taskiq event loop, plain `boto3` is fine if artifact I/O happens in a thread/process pool |
| `taskiq-fastapi` | latest | Wires taskiq's dependency-injection (`TaskiqDepends`) into the same DI patterns as FastAPI | Optional but reduces boilerplate if worker tasks need FastAPI-style dependency injection (DB sessions, settings) |
| `orjson` | latest | Fast JSON (already a transitive dep of `langgraph-checkpoint-postgres`) | Reuse it directly for serializing large agent artifacts before writing to Garage instead of stdlib `json` |
| `tenacity` | latest | Retry/backoff for OpenAI calls and malformed-structured-output retries | `chat.completions.parse()` does NOT retry automatically on `LengthFinishReasonError`/refusal/validation failure — wrap the call in `tenacity.retry` with a check on `message.refusal`/`message.parsed is None` |
| `uvloop` | latest | Faster asyncio event loop | taskiq auto-installs uvloop's policy if it's present in the environment — install it in the worker image for a "free" perf win, no code change needed |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` workspaces (`[tool.uv.workspace]`) | Multi-package monorepo (api / worker / shared agents-and-tools package) | See "Stack Patterns by Variant" below — this is the recommended uv-native structure for exactly this kind of split |
| `taskiq worker` CLI | Runs the worker process(es) | Key flags for this project: `--workers N` (process count), `--max-async-tasks` (concurrency per process — cap this since each LangGraph run holds an OpenAI connection + subprocess handles), `--max-tasks-per-child` (recycle worker processes periodically — cheap insurance against leaked subprocess/fd state from code execution tools) |

## Installation

# Core (run from the relevant workspace member, e.g. packages/worker)

# API package

# Garage / S3 client

# Dev

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `RedisStreamBroker` (taskiq-redis) | `ListQueueBroker` or `PubSubBroker` | `ListQueueBroker` if you don't need delivery acknowledgement and want the simplest possible setup; `PubSubBroker` only if you specifically want at-most-once broadcast semantics (not appropriate as the main task broker here — use it, if at all, only for the progress-event side-channel, not for dispatching the actual solve task) |
| `client.chat.completions.parse()` (Chat Completions API) | `client.responses.parse(text_format=...)` (Responses API) | If the project later adopts OpenAI's newer Responses API (multi-turn state, built-in tool use) — Context7 docs show `responses.parse()` as the equivalent structured-output path there. Chat Completions is fine and currently more universally documented/stable for this use case |
| Direct `redis.asyncio` pub/sub for WebSocket bridging | Dedicated pub/sub broker library (e.g. `broadcaster`) | If you want less custom glue code and are fine with an extra dependency; direct `redis.asyncio` gives more control over message shape (status enum transitions) and avoids pulling in a library whose primary use case is chat-style broadcasting |
| `psycopg` (v3) for the checkpointer | `asyncpg` | Never for the checkpointer itself — `langgraph-checkpoint-postgres` is hard-pinned to psycopg3's API (row_factory, autocommit). You may still use `asyncpg` elsewhere in the app (e.g. via `taskiq-postgres[asyncpg]` if you ever move the broker itself onto Postgres) without conflict, since it's a separate connection pool |
| `uv` workspace (single repo, single lockfile) | Separate repos/pyproject per service with git submodules or a published internal package | Only if api/worker/shared genuinely need independent release cadences or separate CI pipelines; for a solo-maintainer greenfield project a single workspace is strictly simpler |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Calling `subprocess.run()` (blocking) directly inside an `async def` taskiq task | taskiq async tasks execute on the worker's shared asyncio event loop; a blocking call stalls every other task queued to that worker process until it returns — directly undermines the "worker stays responsive" assumption behind async taskiq | `asyncio.create_subprocess_exec(...)` + `await asyncio.wait_for(proc.communicate(), timeout=...)`, or push truly CPU-bound work (Go compilation) to taskiq's `ProcessPoolExecutor` path for sync functions |
| Manually opening a bare `psycopg.connect(DB_URI)` and passing it straight to `PostgresSaver`/`AsyncPostgresSaver` | Missing `autocommit=True` silently fails to persist `.setup()`'s table creation; missing `row_factory=dict_row` causes a `TypeError: tuple indices must be integers or slices, not str` the first time a checkpoint is read back — this is a documented, easy-to-hit footgun in the official README | Either use `AsyncPostgresSaver.from_conn_string(DB_URI)` (handles both flags internally) or explicitly pass `autocommit=True, row_factory=dict_row` (`from psycopg.rows import dict_row`) when constructing connections/pools yourself |
| `resource.setrlimit(RLIMIT_FSIZE, (0, 0))` as a "block all file writes" control for the Python code executor | Widely reported gotcha: it makes the kernel SIGXFSZ-kill the process on ANY write to a regular file, including things you don't expect (e.g. inherited stderr going to a log file) — this produces confusing false "crashes" that look like the generated code failed, when actually your sandboxing killed it | Use a dedicated, fresh temp directory per execution + `RLIMIT_CPU`/`RLIMIT_AS`/`RLIMIT_NOFILE`/`RLIMIT_NPROC` limits instead; treat "no writing outside temp dir" as a policy enforced by running in an unwritable-elsewhere temp sandbox dir, not via FSIZE=0 |
| Relying on `subprocess.run(..., timeout=N)` alone to bound generated-code execution time | `timeout` on `subprocess.run`/`Popen.communicate` kills the direct child but **does not** reliably reach grandchildren processes the child may have spawned (relevant for Go: `go run`/`go build` may fork sub-tools) — orphaned processes can keep running past your timeout and hold resources | Launch with `start_new_session=True` (POSIX: `os.setsid`) to put the process in its own process group, then on timeout signal the whole group (`os.killpg`) with SIGTERM, wait briefly, then SIGKILL if still alive |
| Treating `chat.completions.parse()` as retry-safe by default | The SDK raises `LengthFinishReasonError`/`ContentFilterFinishReasonError` on truncation/filtering, and returns `message.parsed=None` + `message.refusal` set on a model refusal — none of these are retried by the SDK itself | Wrap the call with explicit retry logic (e.g. `tenacity`) that inspects `message.refusal` / catches these exceptions and retries with a repair prompt or backoff, bounded by the project's own `max_iterations` correction-loop concept |
| ARQ | Already excluded per project constraints (unmaintained) — noted here only to confirm the research agrees with the lock | `taskiq` (already chosen) |
| Celery | Already excluded per project constraints (too heavyweight for this scope: separate broker protocol assumptions, less natural asyncio-native fit) | `taskiq` (already chosen) |

## Stack Patterns by Variant

- Use a **uv workspace**: one root `pyproject.toml` with `[tool.uv.workspace] members = ["packages/*"]`, and one `pyproject.toml` per member (`packages/api`, `packages/worker`, `packages/agentcore` or similar name for the shared LangGraph graph/tools/schemas package).
- Cross-package dependency: in `packages/api/pyproject.toml` and `packages/worker/pyproject.toml`, declare `agentcore` as a normal dependency, then add `[tool.uv.sources] agentcore = { workspace = true }` so uv resolves it to the local path instead of trying to fetch it from PyPI.
- A **single shared `uv.lock`** lives at the workspace root — this is a core reason to use workspaces here: LangGraph/Postgres/OpenAI/taskiq versions can't silently drift between the api process and the worker process.
- **One shared virtualenv** is created at the root by `uv sync`; all workspace members become importable from it. This matters directly for this project: the FastAPI process and the taskiq worker process both need to construct/inspect the *same* LangGraph graph definition (for the checkpoint schema and for local dev where both might run in one venv), so they must resolve to the identical `agentcore` package, not two independently-installed copies.
- Because Python's dependency resolution is workspace-wide (unlike Cargo), don't expect the workspace to let api and worker have deliberately conflicting versions of a shared dependency — if a future need arises for that, that's a signal to split into fully separate repos/deployments rather than fight the workspace model.
- Persist the LangGraph checkpoint after every superstep (this is `AsyncPostgresSaver`'s default behavior once wired in — no extra flag needed) so a task that dies mid-review-loop can resume from its last completed node rather than restarting the whole pipeline.
- Resuming is done by re-invoking the graph with the **same `thread_id`** in `config["configurable"]`; LangGraph will pick up from the latest persisted checkpoint. Map your own `task_id` (Postgres task-state row's PK) 1:1 to LangGraph's `thread_id` so a taskiq retry of the same task naturally resumes rather than restarts.
- taskiq itself does not know about LangGraph checkpoints — the resiliency contract is: taskiq re-delivers/retries the *task* (via broker-level retry/ack semantics), and LangGraph's checkpointer makes that re-delivery cheap by resuming mid-graph instead of from scratch. Keep the taskiq task body idempotent at the "wrapper" level (re-invoke the graph with the same thread_id) rather than trying to make taskiq aware of graph-internal progress.
- The community-standard shape for Celery/taskiq + FastAPI + WebSocket (validated across multiple independent sources, not official docs — verify at implementation time) is: API writes task row + enqueues → worker executes, and **after each LangGraph status transition** (e.g. entering `reviewing`, `correcting`) writes the new status to Postgres (source of truth, matches this project's design) **and** `PUBLISH`es a small JSON message to a Redis Pub/Sub channel keyed by `task_id` → the FastAPI WebSocket handler for that `task_id` does `redis.asyncio.Redis.pubsub(); await pubsub.subscribe(f"task:{task_id}:events")` and forwards each message to the connected client as it arrives.
- This avoids polling Postgres from the WebSocket handler entirely; Postgres remains authoritative for "what is the current state if I reconnect / GET the task," Redis Pub/Sub is purely a low-latency fan-out mechanism, not a store (a client that connects the WebSocket after a status transition already happened simply won't see that specific event — it should first do a "sync" read of current status from the `GET` endpoint/Postgres, then attach the WebSocket for subsequent transitions only).
- This can reuse the very same LangGraph node-boundary hooks that update Postgres task state — i.e. a small helper called at the start/end of each graph node (or via a LangGraph node "wrapper"/light custom callback) that does both writes, so there's exactly one place that defines "what a status transition is."

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `langgraph-checkpoint-postgres==3.1.2` | `langgraph-checkpoint>=4.1.0,<5.0.0`, `psycopg>=3.2.0`, `psycopg-pool>=3.2.0`, `orjson>=3.11.5` | Pin ranges are enforced by the package itself; let `uv` resolve within them rather than hand-pinning tighter |
| Python 3.14 | `psycopg` (3.x) | Confirmed: psycopg3 has added Python 3.14 support (verify exact minor version at implementation time — check psycopg's release notes for the specific 3.14-compatible release) |
| Python 3.14 | `taskiq` / `taskiq-postgres` | `taskiq-postgres` explicitly lists Python 3.14 support; core `taskiq`/`taskiq-redis` had no reported 3.14 incompatibilities found, but **verify at implementation time** by running `uv add` and checking for resolution failures, since this stack is bleeding-edge (Python 3.14 released 2025) |
| Python 3.14 | `langgraph` | LangGraph's own changelog confirms Python 3.13 compatibility explicitly; no explicit 3.14 statement was found in this research pass — **flag as verify-at-implementation-time**: run the actual `uv sync` in a 3.14 environment early (Phase 1) as a smoke test before deep investment, and have a documented fallback (pin to 3.13 for the interpreter, or wait for an upstream LangGraph release note) if it fails |
| `openai` Python SDK | v1.x vs v2.x lines | Context7 registry lists both `v1.105.0`-era and `v2.8.1`/`v2.11.0` versions as current; v2 introduces the newer Responses-API-first surface. Since this project uses per-agent configurable models via Chat Completions-style structured outputs, **pin explicitly and verify `client.chat.completions.parse()` still exists unchanged in whichever major you land on** — don't let `uv add openai` float across a major version boundary silently |

## Sources

- `/langchain-ai/langgraph` (Context7, official GitHub repo docs: `libs/checkpoint-postgres/README.md`, `libs/checkpoint/README.md`, `libs/sdk-py/MIGRATION.md`, `libs/prebuilt/README.md`, `libs/checkpoint-postgres/pyproject.toml`, `libs/checkpoint-postgres/langgraph/store/postgres/aio.py`) — checkpointer setup, `thread_id`/`checkpoint_id` resume mechanics, `interrupt()`/`Command(resume=...)`. Confidence: MEDIUM (official source, pulled via Context7 aggregation).
- `/openai/openai-python` (Context7, `helpers.md` from official repo) — `chat.completions.parse()`, refusal/parsed handling, `LengthFinishReasonError`/`ContentFilterFinishReasonError`, Responses API `text_format` equivalent. Confidence: MEDIUM.
- `/websites/developers_openai_api` (Context7, OpenAI docs site: structured-outputs and function-calling guides) — strict-mode schema constraints (`additionalProperties: false`, all fields required, optional-as-nullable pattern), supported JSON Schema subset. Confidence: MEDIUM.
- `/taskiq-python/taskiq` and `/taskiq-python/taskiq-redis` (Context7, official repo docs: `README.md`, `docs/guide/getting-started.md`, `docs/guide/cli.md`, `docs/guide/state-and-deps.md`, `docs/framework_integrations/taskiq-with-fastapi.md`, `receiver/receiver.py`) — FastAPI lifespan wiring, per-task timeout labels, sync-task executor choice (Thread vs Process pool), `RedisStreamBroker`/`ListQueueBroker`/`PubSubBroker` choices, `RedisAsyncResultBackend` config, worker CLI concurrency flags. Confidence: MEDIUM.
- Web search (multiple independent sources, LOW confidence individually, cross-corroborated where noted — verify specifics at implementation time): LangGraph async cancellation/timeout GitHub discussions (`langchain-ai/langgraph` discussions #6163, #1601, issue #8842); Python subprocess resource-limiting practices (`luminousmen.com/post/python-resource-limitation`, `healeycodes.com/running-untrusted-python-code`, `chs.us` sandboxing post); Go untrusted-build isolation (`pandastack.ai` blog on sandboxing Go builds); FastAPI+Celery/taskiq+WebSocket+Redis pub/sub bridging pattern (multiple blog/Medium/GitHub examples, no single canonical official doc); `uv` workspace monorepo guides (`docs.astral.sh/uv/concepts/projects/workspaces/` is the one **official** source among these — treat it as MEDIUM, the rest as LOW/community-practice); Python 3.14 compatibility claims for psycopg3/taskiq-postgres (PyPI package pages, psycopg release notes).
- `docs.astral.sh/uv/concepts/projects/workspaces/` — official `uv` documentation on workspace members, shared lockfile, `[tool.uv.sources] pkg = { workspace = true }`. Confidence: MEDIUM-HIGH (official docs, reached via web search rather than Context7 in this pass — re-verify exact syntax at implementation time).

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

## Repository Rules

This section is hand-authored and must remain outside all GSD-managed blocks. It survives GSD regeneration and is the canonical source for repository rules.

**INFRA-05 Compliance:** This file (`.claude/CLAUDE.md`) is the repository's working rules document. The repository intentionally has no root `CLAUDE.md` file (user decision, overriding D-16's default layout). All working rules, conventions, and documentation links are here and in the referenced docs.

### Layout

```
.
├── src/algorunner/              Backend: agents, graph, schemas, storage, API, worker
├── frontend/                    React + TypeScript + Vite web UI
├── tests/                       Pytest backend tests (async, session loop, Postgres+Redis)
├── docs/
│   ├── architecture/            Service topology, data paths, module map
│   ├── development/             Testing guide, code conventions
│   ├── product/                 PRD (user stories)
│   └── plans/                   Implementation plan and milestones
├── scripts/                     Live probes (verify_phase*.py) and gates (check_docs.py)
├── docker/                      Dockerfiles and nginx config
├── docker-compose.yml           7 services: postgres, redis, garage, api, worker, frontend, nginx
├── .env.example                 Reference environment (copy to .env, add OPENAI_API_KEY)
├── pyproject.toml               Dependencies, pytest config
├── DEFERRED.md                  Acknowledged out-of-scope features
└── README.md                    Quickstart and docs index
```

### Everyday Commands

```bash
# Setup
uv sync                                           # Install dependencies
docker compose up -d postgres redis garage        # Start test infra
docker compose -p algorunner up -d --build        # Full stack in a worktree

# Frontend
npm --prefix frontend ci                          # Install dependencies
npm --prefix frontend run dev                     # Dev server at localhost:5173 (proxied to api:8000)
npm --prefix frontend run build                   # Vite production build
npm --prefix frontend test                        # Unit tests (vitest, node environment)
npm --prefix frontend run test:live               # Integration tests (needs api/worker running)

# Backend
pytest                                            # Full test suite (requires postgres/redis)
pytest tests/api/test_events_ws.py                # Single test file

# Live probes (see DEFERRED.md, testing.md for details)
uv run python scripts/verify_phase3_live.py       # Backend submit/status/result workflow
uv run python scripts/verify_phase4_live.py       # WebSocket streaming and gateway
uv run python scripts/verify_executor_isolation.py # Process group signal handling

# Docker & Compose
docker compose up -d --build                      # Start full stack (api, worker, frontend, nginx)
docker compose -p algorunner up -d                # Isolated worktree stack
docker compose down                               # Shut down
```

### Backend Rules (D-14)

1. **Async-only I/O**: All database, Redis, HTTP, subprocess operations are async. Never call blocking I/O inside `async def` functions.
2. **SQL with `%s` placeholders**: Every SQL query uses `%s` parameter binding, never f-strings or concatenation.
3. **Pydantic at every boundary**: API requests/responses, LangGraph state, OpenAI Structured Outputs, and storage contracts all use Pydantic v2.
4. **Status transitions through storage writers**: Status changes only flow through `storage/tasks.py` functions. After Postgres commit, publish to Redis Pub/Sub.
5. **Never-raise side channels**: WebSocket handlers and subscriptions never raise `Exception`; they log and return. They never swallow `CancelledError`.
6. **Structured TaskError codes**: Errors use a code enum (ANALYSIS_FAILED, CODE_EXECUTION_FAILED, etc.) and message string.
7. **One logger per module**: Each module has `logger = logging.getLogger(__name__)`.
8. **Settings from `.env.example` and env vars**: No hardcoded config. All runtime values come from environment or `config.py`.
9. **Per-agent model overrides**: Each agent can override its model via `{AGENT_NAME}_MODEL` env var.
10. **Module docstrings cite decisions**: Every module documents which design decisions (D-01, D-02, etc.) shaped it.

For the long form, see [docs/development/conventions.md](../docs/development/conventions.md) (Backend section).

### Frontend Rules (D-14)

1. **File layout**: `pages/` for screens, `components/` for reusable views, `lib/` and `api/` for pure logic with colocated tests.
2. **Naming**: PascalCase for React components (`CodeBlock.tsx`), camelCase for utilities and modules (`parseEditorial.ts`).
3. **TypeScript strict mode**: `strict: true`, no `any`, narrow `unknown` with guards.
4. **Type mirrors in `api/types.ts`**: Backend Pydantic schemas are manually mirrored in TypeScript. Keep them in sync with Python.
5. **`as const` unions, not enums**: Use `const TaskStatuses = [...] as const` instead of TS enum.
6. **Context + useReducer for state**: Global task state lives in React Context with a reducer. No Redux, Zustand, or other state library.
7. **Native fetch and WebSocket**: No axios, React Query, or socket.io. Use native APIs with simple wrapper functions.
8. **Tailwind utilities only**: All styling is Tailwind utility classes. No custom CSS files except `index.css` (imports only).
9. **Russian UI text**: All user-facing text in the UI is in Russian. Comments and code are English.
10. **CodeBlock: the only raw-HTML sink**: Only `components/CodeBlock.tsx` uses `dangerouslySetInnerHTML` (for highlight.js output).

For the long form, see [docs/development/conventions.md](../docs/development/conventions.md) (Frontend section).

### Documentation Index

Complete documentation set with cross-references:

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Product summary, quickstart, tests overview, docs index, unsandboxed-code warning |
| [docs/product/prd.md](../docs/product/prd.md) | User stories, acceptance criteria, product scope (Phase 1) |
| [docs/architecture/architecture.md](../docs/architecture/architecture.md) | Service topology, data paths, module map, deployment instructions |
| [docs/architecture/agents.md](../docs/architecture/agents.md) | LLM agent nodes: input, process, output per agent |
| [docs/architecture/workflow.md](../docs/architecture/workflow.md) | LangGraph state machine: node order, edges, fan-out/join logic |
| [docs/architecture/data-model.md](../docs/architecture/data-model.md) | Pydantic schemas: task, problem, approach, solution, execution, editorial |
| [docs/development/testing.md](../docs/development/testing.md) | Backend test fixtures, async patterns, WebSocket testing; frontend unit and integration tests; live probes |
| [docs/development/conventions.md](../docs/development/conventions.md) | Backend code style (async, SQL, Pydantic, status transitions, logging); frontend file layout, naming, state management |
| [docs/plans/implementation-plan.md](../docs/plans/implementation-plan.md) | 7-phase roadmap with per-phase scope, dependencies, and success criteria |
| [DEFERRED.md](../DEFERRED.md) | Acknowledged out-of-scope features (auth, sandboxing, Kubernetes, search, etc.) with rationale and estimated phase |

### Gate Script

Run [`scripts/check_docs.py`](../scripts/check_docs.py) to verify INFRA-05 compliance:

```bash
uv run python scripts/check_docs.py
```

Checks:
1. All INFRA-05 paths (architecture/*, development/*, product/prd.md, plans/implementation-plan.md), DEFERRED.md, and README.md exist and are non-empty.
2. `.claude/CLAUDE.md` has a "## Repository Rules" heading outside all GSD markers, mentioning INFRA-05.
3. No root `CLAUDE.md` exists.
4. Every relative Markdown link in the docs set resolves.
5. Every docker-compose.yml top-level service is named in architecture.md.
6. Total docs size is 30–80 KB (target ~40–60 KB).

Exit 0 and print `DOCS_OK` on success.
