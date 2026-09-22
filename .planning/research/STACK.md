# Stack Research

**Domain:** Multi-agent LLM pipeline (LangGraph) behind a task-queue-backed FastAPI service, generating and executing Python/Go code
**Researched:** 2026-09-22
**Confidence:** MEDIUM (core integration facts verified against official docs via Context7; sandboxing/websocket-bridging/monorepo patterns are community-practice, verify at implementation time)

This file assumes all "locked" decisions from PROJECT.md (Python 3.14, uv, LangGraph, OpenAI API, taskiq+Redis, PostgreSQL, Garage, FastAPI+WebSocket, React+TS, Docker Compose, subprocess execution) as given. It focuses on **how to wire them together** and the specific gotchas of doing so.

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

```bash
# Core (run from the relevant workspace member, e.g. packages/worker)
uv add langgraph langgraph-checkpoint-postgres "psycopg[binary,pool]" \
       taskiq taskiq-redis taskiq-fastapi \
       openai pydantic tenacity orjson uvloop

# API package
uv add fastapi "uvicorn[standard]" "redis[hiredis]"

# Garage / S3 client
uv add aioboto3

# Dev
uv add -D pytest pytest-asyncio
```

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

**If structuring the repo as api / worker / shared-agents-and-tools packages (this project's shape):**
- Use a **uv workspace**: one root `pyproject.toml` with `[tool.uv.workspace] members = ["packages/*"]`, and one `pyproject.toml` per member (`packages/api`, `packages/worker`, `packages/agentcore` or similar name for the shared LangGraph graph/tools/schemas package).
- Cross-package dependency: in `packages/api/pyproject.toml` and `packages/worker/pyproject.toml`, declare `agentcore` as a normal dependency, then add `[tool.uv.sources] agentcore = { workspace = true }` so uv resolves it to the local path instead of trying to fetch it from PyPI.
- A **single shared `uv.lock`** lives at the workspace root — this is a core reason to use workspaces here: LangGraph/Postgres/OpenAI/taskiq versions can't silently drift between the api process and the worker process.
- **One shared virtualenv** is created at the root by `uv sync`; all workspace members become importable from it. This matters directly for this project: the FastAPI process and the taskiq worker process both need to construct/inspect the *same* LangGraph graph definition (for the checkpoint schema and for local dev where both might run in one venv), so they must resolve to the identical `agentcore` package, not two independently-installed copies.
- Because Python's dependency resolution is workspace-wide (unlike Cargo), don't expect the workspace to let api and worker have deliberately conflicting versions of a shared dependency — if a future need arises for that, that's a signal to split into fully separate repos/deployments rather than fight the workspace model.

**If the correction/review loop must survive a worker crash/restart mid-run (this project's checkpoint requirement):**
- Persist the LangGraph checkpoint after every superstep (this is `AsyncPostgresSaver`'s default behavior once wired in — no extra flag needed) so a task that dies mid-review-loop can resume from its last completed node rather than restarting the whole pipeline.
- Resuming is done by re-invoking the graph with the **same `thread_id`** in `config["configurable"]`; LangGraph will pick up from the latest persisted checkpoint. Map your own `task_id` (Postgres task-state row's PK) 1:1 to LangGraph's `thread_id` so a taskiq retry of the same task naturally resumes rather than restarts.
- taskiq itself does not know about LangGraph checkpoints — the resiliency contract is: taskiq re-delivers/retries the *task* (via broker-level retry/ack semantics), and LangGraph's checkpointer makes that re-delivery cheap by resuming mid-graph instead of from scratch. Keep the taskiq task body idempotent at the "wrapper" level (re-invoke the graph with the same thread_id) rather than trying to make taskiq aware of graph-internal progress.

**If bridging taskiq worker progress to a WebSocket without polling (this project's `/events` requirement):**
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

---
*Stack research for: AlgoRunner (multi-agent LangGraph pipeline + taskiq/Redis + Postgres + FastAPI/WebSocket + subprocess code execution)*
*Researched: 2026-09-22*
