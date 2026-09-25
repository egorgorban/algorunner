# Architecture: AlgoRunner

## Purpose & Core Value

AlgoRunner is a production-ready multi-agent system that transforms a free-text algorithmic problem description (English or Russian) into a comprehensive LeetCode-editorial-style article in Russian. The system analyzes the problem, generates 1+ solution approaches with Python and Go implementations, executes them against tests for correctness, refines them through a review loop, and presents everything in a well-structured editorial. **Correctness of the generated solution—verified by executing Python and Go code against actual tests—matters more than explanation quality or speed.**

## Service Architecture

The system comprises 7 containerized services orchestrated by Docker Compose:

| Service | Port | Role |
|---------|------|------|
| **nginx** | 80 | Reverse proxy: `/api/*` → api:8000, `/` → frontend:3000 |
| **frontend** | 3000 (internal) | React + TypeScript web UI |
| **api** | 8000 | FastAPI REST/WebSocket server |
| **worker** | (no host port) | Async task executor (taskiq consumer) |
| **postgres** | 5432 | Tasks table, LangGraph checkpoint storage, persistent state-of-truth |
| **redis** | 6379 | taskiq broker (RedisStreamBroker) + Pub/Sub for real-time events |
| **garage** | 3900 | S3-compatible artifact storage (intermediate analysis, code, editorial) |

## Data Paths

### Submit Path (POST → Queued → Complete)

```
Browser/Client
    ↓
POST /api/v1/tasks
    ↓
API: insert Task row (status: queued)
    ↓
taskiq: enqueue via RedisStreamBroker
    ↓
Worker: dequeue + invoke LangGraph solve_problem_stub
    ↓
LangGraph: execute StateGraph with AsyncPostgresSaver checkpoints
    ├─ Analyzer node: parse problem + difficulty
    ├─ Strategist node: propose solution approaches
    └─ Per-approach branch (via Send):
       ├─ Solver: algorithm elaboration
       ├─ Code Generator: Python + Go
       ├─ Test Generator: test cases
       ├─ Python Executor: subprocess run + tests
       ├─ Go Executor: compile + run + tests
       └─ Reviewer: correctness + complexity + edge cases
    ├─ Correction loop (bounded by max_iterations)
    ├─ Editorial Writer: compose Russian article
    └─ Finalize: persist result to Postgres
    ↓
Garage: durably persist analysis, code, tests, review, editorial
    ↓
Postgres: update Task status (completed/failed), store result JSON
```

### Status Path (Status Write → Live Stream)

```
Worker: update Task.status in Postgres (on node boundary)
    ↓
Worker: publish StatusEvent to Redis pub/sub on task:{task_id}:status
    ↓
API: subscribe to task:{task_id}:status channel
    ↓
API: WebSocket relay → connected clients (immediate + future statuses)
    ↓
Browser: render live status badge
```

## Module Map

The `src/algorunner/` package is organized by responsibility (not by DDD layers):

```
src/algorunner/
├── agents/              # LLM-backed agent nodes
│   ├── problem_analyzer/
│   ├── solution_strategist/
│   ├── solver/
│   ├── code_generator/
│   ├── test_generator/
│   ├── reviewer/
│   └── editorial_writer/
├── tools/              # Deterministic execution tools (subprocess-based)
│   ├── python_executor/
│   ├── go_executor/
│   └── process.py
├── graph/              # LangGraph state graph definition
│   ├── build.py        # Parent graph (fan-out → join → finalize)
│   ├── approach.py     # Per-approach subgraph
│   ├── state.py        # GraphState, ApproachState
│   ├── routing.py      # Conditional edges
│   └── context.py      # PipelineContext, status emission
├── schemas/            # Pydantic models for validation
│   ├── task.py         # TaskStatus, TaskRecord
│   ├── problem.py      # ProblemAnalysis
│   ├── solution.py     # Approach, Solution
│   ├── execution.py    # ExecutionResult
│   ├── review.py       # ReviewResult
│   └── editorial.py    # Editorial, EditorialApproach
├── api/                # FastAPI app + routes
│   ├── main.py         # FastAPI app setup, lifespan
│   └── routes/
│       ├── tasks.py    # POST /api/v1/tasks, GET /api/v1/tasks/{id}
│       ├── clarification.py  # POST /api/v1/tasks/{id}/clarification
│       ├── events.py   # WS /api/v1/tasks/{id}/events
│       └── config.py   # GET /api/config
├── realtime/           # WebSocket event handling + Redis pub/sub
│   ├── events.py       # StatusEvent, subscription management
│   └── publisher.py    # After-commit status publish
├── worker/             # Background task execution
│   ├── broker.py       # taskiq broker setup + startup hook
│   └── tasks.py        # @broker.task decorated solve_problem_stub
├── storage/            # Data persistence
│   ├── postgres.py     # Connection pool, pool factory
│   ├── artifacts.py    # Garage S3 client + key builders
│   └── migrate.py      # Schema migrations + advisory lock
├── llm/                # LLM client factory + retry logic
│   ├── client_factory.py  # model_for, per-agent model config
│   └── retry.py        # Retry wrappers for timeouts + rate-limits
└── config.py           # Settings from environment variables
```

The frontend lives in a separate build context:
```
frontend/
├── src/
│   ├── App.tsx
│   ├── context/TaskContext.tsx
│   ├── pages/
│   ├── components/
│   ├── api.ts
│   └── index.css
├── vite.config.ts
├── Dockerfile
└── package.json
```

## Key Decisions

| Decision ID | Title | Rationale |
|-------------|-------|-----------|
| **D-01** | Postgres as single source of truth for task state | All state reads/writes go to Postgres; Redis pub/sub is a real-time notification channel, not the store. Ensures data survives broker restarts. |
| **D-02** | taskiq + RedisStreamBroker for task queue | Native asyncio integration, per-task timeout labels, message acknowledgement (prevents loss on worker crash). Simpler than Celery, more robust than ARQ. |
| **D-03** | LangGraph checkpoint resume by thread_id = task_id | One-to-one mapping: when a task is retried or resumed, re-invoke the same LangGraph graph with the same thread_id to pick up from the latest checkpoint instead of restarting. |
| **D-04** | Full status taxonomy (12 values) from Phase 1 | All statuses defined upfront (queued, analyzing_problem, designing_solution, generating_code, generating_tests, executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial, completed, failed) so UI has rich progress visibility. |
| **D-05** | Send fan-out per approach after Strategist | Multiple solution approaches run in parallel via LangGraph Send, then join. Isolation and per-approach timeout boundaries simplify reasoning about resource usage. |
| **D-06** | Editorial JSON with verbatim executed code | Code blocks in the editorial are copied verbatim from the executor output—no rewriting, no review-driven edits. This ensures the code shown was actually verified by execution. |
| **D-07** | Garage for intermediate artifact storage | S3-compatible object storage keeps intermediate products (analysis.json, solutions, tests, reviews, editorial.json) durably persisted without cluttering the Postgres result column. Keyed by task_id. |
| **D-08** | Publish-after-commit with subscribe-first relay | Worker publishes to Redis pub/sub only after Postgres commit. WebSocket client connects and subscribes before querying current state, ensuring no race between snapshot read and subscription. |
| **D-09** | Minimal WebSocket message (status + timestamp) | Each event is `{status: string, timestamp: ISO8601}`—no per-approach context. UI accumulates events to build history; Postgres query provides richer detail if needed. |
| **D-10** | nginx reverse proxy in docker-compose | Single HTTP gateway on port 80: `/api/*` proxies to api:8000 (with WebSocket upgrade), `/` proxies to frontend:3000. Simplifies browser CORS and client configuration. |
| **D-11** | Per-agent model override via config | Each agent reads its `{agent}_model` environment variable; falls back to `default_model` if not set. Enables cost optimization (cheap model for analysis/review, stronger for solving). |
| **D-12** | Unprivileged uid 65534 for code execution | Generated Python and Go code run as uid 65534 (nobody), rlimit-capped (CPU, memory, file descriptors), with an import denylist—not sandboxed, but guarded against obvious misuse. |

## Security Posture

**What v1 is NOT:**
- Generated code is **not sandboxed**. Python and Go subprocesses run with resource limits (CPU, memory, file descriptor count) and an import/module denylist, but as unsandboxed processes on the host.
- There is **no authentication**. Any caller with a task UUID can read or stream that task. Multi-tenant/user isolation is deferred (SEC-01).
- Database and Redis ports are **published to the host** in dev compose for convenience, unsuitable for production (SEC-02/SEC-03 harden this).

**What v1 guards against:**
- Process escape via resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NPROC, RLIMIT_NOFILE).
- Python import of dangerous modules (subprocess, socket, os, etc. on an allowlist).
- File writes outside the temp execution directory (runtime policy enforced by directory layout, not RLIMIT_FSIZE which can cause false "crashes").
- Whole-process-group kill on timeout (os.killpg to reach spawned grandchildren, not just direct child).

For hardening roadmap, see [DEFERRED.md](../../DEFERRED.md) (SEC-01, SEC-02, SEC-03).

## Deployment

**Local Development**
```bash
docker compose up
# Postgres: localhost:5432
# Redis: localhost:6379
# Garage: localhost:3900
# API: localhost:8000
# Frontend: localhost:3000 (via nginx at :80)
# nginx: localhost:80
```

**Configuration**
- `.env` file (or environment) provides:
  - `OPENAI_API_KEY` (required)
  - `DATABASE_URL` (default: postgres://algorunner:algorunner@localhost:5432/algorunner)
  - `REDIS_URL` (default: redis://localhost:6379)
  - Garage credentials (defaults: dev/test values in compose file)

**Schema Migrations**
- Postgres migrations run automatically on worker startup (run_migrations_with_lock).
- Advisory lock prevents concurrent migration races if multiple workers start simultaneously.

## Constraints

- **Language:** Input accepts English or Russian; output editorial is always Russian.
- **Code Execution:** Python via subprocess, Go via compile-then-run. Both without sandboxing in v1.
- **Time Budget:** 20-minute global timeout (configurable `global_timeout_s`); 4-minute editorial reserve.
- **Correction Loop:** Max 5 iterations (configurable `max_iterations`) before a failing solution terminates as FAILED.
- **Clarification:** Up to 2 interactive clarification rounds before the system picks a best guess (configurable `clarification_round_cap`).
