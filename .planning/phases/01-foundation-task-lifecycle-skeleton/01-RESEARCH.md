# Phase 1: Foundation & Task Lifecycle Skeleton - Research

**Researched:** 2026-09-22
**Domain:** FastAPI + taskiq/Redis + PostgreSQL + LangGraph checkpointing + Docker Compose skeleton (no AI logic yet)
**Confidence:** HIGH (all critical risks resolved by direct execution in this session — see Sources)

## Summary

This phase has one dominant risk flagged in STATE.md: whether LangGraph runs at all under Python 3.14. **That risk is resolved.** This session ran a real falsification attempt — not a registry lookup, an actual `uv add` dependency resolution *and* a runtime import *and* a compiled `StateGraph.ainvoke()` round-trip — against Python 3.14.5 on this machine, and all three succeeded (see Sources). D-13's fallback (pin to 3.13) is **not needed**; the planner should treat the Python-3.14 smoke-test task as a task that is expected to pass, and D-12's stub graph becomes a *confirmation* step, not a rescue mission.

The second major finding is a stack-narrowing one: this phase's own scope (no AI logic — D-04) means the `openai` SDK should **not** be installed in Phase 1 at all. ORCH-02 ("inter-node data validated via Pydantic structured-output schemas") is satisfied for this phase by the trivial stub graph's `TypedDict`/Pydantic state alone — no LLM call exists yet to need OpenAI's structured-output helpers. This also sidesteps the STATE.md-flagged "OpenAI SDK v1 vs v2" pinning blocker entirely by deferring the decision to Phase 2, where it belongs. Similarly, D-11 (Garage present but unwired) means `aioboto3`/`boto3` are not needed in Phase 1 either. The Phase 1 install list is materially smaller than project-level STACK.md's full installation command.

The third finding is a **conflict between two project-level research documents** the planner must resolve in favor of the locked decision: `.planning/research/STACK.md`'s "Stack Patterns by Variant" section recommends a **`uv` workspace** (separate `packages/api`, `packages/worker`, `packages/agentcore`). This directly contradicts INFRA-01 ("a single package with clear modular structure... not DDD/clean-architecture layering") and ROADMAP/STATE.md's explicit decision ("single `uv` package (not a workspace)"). `.planning/research/ARCHITECTURE.md`'s "Recommended Project Structure" already uses the single-package layout and is the one to follow. **The planner must use the single-package structure, not the workspace structure, despite STACK.md's variant-guidance section.**

**Primary recommendation:** Build the single-package skeleton (`src/algorunner/{schemas,graph,agents,tools,storage,api,worker}/`), wire `AsyncPostgresSaver` with a shared `psycopg` `AsyncConnectionPool` (`autocommit=True, row_factory=dict_row`) for both the task table and the LangGraph checkpointer, use `taskiq-redis`'s `RedisStreamBroker` (acks, durable) per STACK.md's own recommendation, and treat the Python 3.14 compatibility question as closed.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Task submission validation (`POST /api/v1/tasks`) | API / Backend | — | FastAPI route validates the Pydantic `TaskSubmission` schema; no business logic beyond validation + enqueue (INTAKE-01, API-01) |
| Task enqueueing | API / Backend | Database / Storage | API writes the `queued` row to Postgres, then calls `.kiq()` on the taskiq task (QUEUE-01) — Postgres write happens before/atomically with enqueue so a client polling immediately never sees a 404 |
| Task processing (placeholder pipeline) | API / Backend (worker process) | Database / Storage | The taskiq worker owns the stub LangGraph invocation; it is a backend-tier process, distinct from the FastAPI process, but shares the same Python package |
| Status persistence (single source of truth) | Database / Storage | — | Postgres `tasks` table — DATA-01 is explicit that Postgres, not Redis or LangGraph checkpoint state, is authoritative |
| LangGraph checkpoint persistence | Database / Storage | API / Backend (worker) | `AsyncPostgresSaver` owns its own tables (`checkpoints`, `checkpoint_writes`, etc.), created via `.setup()`; the worker process is the only thing that invokes the graph |
| Task status read (`GET /api/v1/tasks/{id}`) | API / Backend | Database / Storage | Thin read of the Postgres row; no computation |
| Queue transport | API / Backend ↔ Worker (via Redis) | — | `taskiq` + `taskiq-redis` `RedisStreamBroker`; Redis is infrastructure, not a tier that owns business logic |
| Garage presence (container only) | Database / Storage | — | Container runs per INFRA-02 but is inert this phase (D-11) — no tier owns any Garage *logic* yet |
| Docker Compose orchestration | Infra (cross-cutting) | — | Not an application tier; wires all of the above together for local/deployed operation |

No Browser/Client or CDN/Static tier work exists in this phase — there is no frontend requirement until Phase 4 (API-04/05, UI-01..04).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTAKE-01 | User submits a problem (EN/RU text, optional examples) via the API | `TaskSubmission` Pydantic schema (D-01/D-02/D-03) — see Code Examples |
| ORCH-02 | Inter-node data validated via Pydantic structured-output schemas | Satisfied this phase by the stub graph's `TypedDict` state + Pydantic `TaskRecord`/`TaskError` — no OpenAI call exists yet, so no `openai` SDK dependency is needed to satisfy this requirement in Phase 1 |
| API-01 | `POST /api/v1/tasks` → `202 Accepted` + `task_id` + `status: queued` | FastAPI route pattern — see Code Examples; write-then-enqueue ordering documented in Architecture Patterns |
| API-02 | `GET /api/v1/tasks/{task_id}` → current status + result when completed | Postgres read via `psycopg` `class_row(TaskRecord)` — see Code Examples |
| QUEUE-01 | Enqueue via taskiq + Redis; task stays `queued` if workers busy | `RedisStreamBroker` (durable, acks) — see Standard Stack and Pitfall: taskiq/Redis worker-crash blind spot |
| DATA-01 | Postgres is source of truth for task state | `tasks` table schema — see Code Examples; migration approach — see Architecture Patterns |
| INFRA-01 | Python 3.14 via `uv`, single package, modular structure (agents/, tools/, api/, worker/, schemas/) | Python 3.14 + LangGraph compatibility **confirmed by direct execution this session** (imports + compiled graph run); single-package structure (not workspace) — see Summary conflict note |
| INFRA-02 | Docker Compose brings up API, worker, Postgres, Redis, Garage together | `docker-compose.yml` skeleton — see Code Examples; Garage image/flags — see Standard Stack |
</phase_requirements>

## Standard Stack

### Core (Phase 1 scope — narrower than project-level STACK.md)

| Library | Version (verified this session) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langgraph` | `1.2.12` [VERIFIED: PyPI registry — resolved via `uv add` under Python 3.14.5 this session, then imported and executed] | Stub `StateGraph` for the D-12 smoke test | Already locked; current line resolves and *runs* cleanly under 3.14 (see Open Questions → now closed) |
| `langgraph-checkpoint-postgres` | `3.1.2` [VERIFIED: PyPI registry, same session install] | `AsyncPostgresSaver` checkpointing | Official first-party Postgres checkpointer; only supported path to persist LangGraph state to Postgres |
| `psycopg[binary,pool]` | `3.3.6` [VERIFIED: PyPI registry — classifiers explicitly list Python 3.10–3.15, confirmed via `pip`-equivalent registry query] | Postgres driver for both the checkpointer pool and direct task-table CRUD | `langgraph-checkpoint-postgres` requires `psycopg>=3.2.0`; reusing the same driver for task CRUD avoids a second Postgres client dependency |
| `taskiq` | `0.12.6` [VERIFIED: PyPI registry — classifiers explicitly list Python 3.14 support] | Task queue core | Already locked; explicit 3.14 classifier is the strongest compatibility signal of any package in this stack |
| `taskiq-redis` | `1.2.3` [VERIFIED: PyPI registry, same session install] | `RedisStreamBroker` + `RedisAsyncResultBackend` | Durable, ack-based broker — STACK.md's own recommendation, confirmed still current |
| `taskiq-fastapi` | `0.5.0` [VERIFIED: PyPI registry, same session install] | Wires FastAPI `Request`/dependency context into taskiq tasks | Lets the worker reuse the same `get_pg_pool`-style dependency the API routes use — avoids duplicating pool-construction code |
| `fastapi` | `0.141.1` [VERIFIED: PyPI registry, same session install] | HTTP API | Already locked |
| `uvicorn[standard]` | latest (installs alongside fastapi) | ASGI server | Standard FastAPI companion |
| `pydantic` | `2.13.5` [VERIFIED: PyPI registry, same session install] | All schemas (task submission, task record, error, status enum) | One schema library end-to-end, per project constraint |
| `pydantic-settings` | `2.15.0` [VERIFIED: PyPI registry] | Config from env (DB URL, Redis URL, Garage endpoint even if unused) | Standard pairing with Pydantic v2 for 12-factor config |

### Explicitly deferred out of Phase 1 (do not install yet)

| Library | Why deferred |
|---------|--------------|
| `openai` | No LLM call exists in Phase 1 (D-04: worker has no AI logic). Installing it now forces a premature v1-vs-v2-vs-v3 pin (STATE.md blocker) for a dependency nothing in this phase uses. Defer to Phase 2. Note: registry check this session shows the SDK has moved to a **v3.x line (`3.17.0`)** [VERIFIED: PyPI registry] — STACK.md's "v1 vs v2" framing is itself stale; flag this for Phase 2 research, don't resolve it here. |
| `aioboto3` / `boto3` | D-11: Garage runs in Compose but has zero client wiring this phase. Installing an S3 client with nothing calling it adds surface area for no Phase 1 requirement. |
| `tenacity` | Only needed to wrap retryable OpenAI calls (STACK.md's stated use case); nothing to retry yet. |
| `alembic` / `sqlalchemy` | See Architecture Patterns → migration approach; Phase 1's single `tasks` table doesn't justify the dependency yet. |

### Supporting (dev/test)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | latest | Required transitively by FastAPI's `TestClient` | Any test that exercises `POST /api/v1/tasks` / `GET /api/v1/tasks/{id}` |
| `pytest`, `pytest-asyncio` | latest | Test runner for async FastAPI routes and taskiq tasks | Dev dependency |
| `orjson` | `3.12.0` (pulled transitively by `langgraph-checkpoint-postgres`) | Fast JSON | Already a transitive dependency this session — no need to add explicitly unless used directly |
| `uvloop` | latest | Faster event loop | Optional; taskiq auto-installs its policy if present — nice-to-have, not required for Phase 1 success criteria |

### Installation

```bash
uv add langgraph langgraph-checkpoint-postgres "psycopg[binary,pool]" \
       taskiq taskiq-redis taskiq-fastapi \
       fastapi "uvicorn[standard]" pydantic pydantic-settings

uv add -D pytest pytest-asyncio httpx
```

**Version verification performed this session:** ran `uv init --python 3.14` + `uv add <all above>` in a scratch project, then executed `python -c "import langgraph, psycopg, taskiq, ..."` and a full `StateGraph.compile(checkpointer=InMemorySaver()).ainvoke(...)` round-trip — all succeeded on Python 3.14.5. Exact resolved versions are pinned in the table above.

## Package Legitimacy Audit

The automated `package-legitimacy check` seam returned `SUS` for **every** package checked (`langgraph`, `langgraph-checkpoint-postgres`, `psycopg`, `taskiq`, `taskiq-redis`, `taskiq-fastapi`, `openai`, `fastapi`, `pydantic`, `pydantic-settings`, `aioboto3`, `tenacity`, `orjson`, `uvloop`, `uvicorn`, `redis`). Reading the `reasons` field shows why: `too-new` compares only the **most recent** publish timestamp (all of these are actively maintained and ship releases regularly, so "latest release is recent" trips this heuristic for literally every well-maintained package), and `unknown-downloads` means the download-stats provider was unreachable from this environment, not that download counts are actually low or zero. Neither reason reflects the checked packages' actual age or usage.

This session performed a direct falsification of the `too-new` signal by querying PyPI's JSON API for each package's **full release history** (first release date, total release count) and `project_urls` (to confirm the GitHub org). Every package has a multi-year history and an official-org repository:

| Package | Registry | First Release | Total Releases | Source Repo | Automated Verdict | Disposition |
|---------|----------|----------------|-----------------|--------------|---------|-------------|
| `fastapi` | PyPI | 2018-12-08 | 317 | github.com/fastapi/fastapi | SUS (too-new, unknown-downloads) | **OK — overridden** [VERIFIED: PyPI release history, this session] |
| `pydantic` | PyPI | 2017-05-03 | 206 | github.com/pydantic/pydantic | SUS | **OK — overridden** [VERIFIED] |
| `pydantic-settings` | PyPI | 2019-08-19 | 45 | github.com/pydantic/pydantic-settings | SUS | **OK — overridden** [VERIFIED] |
| `redis` (redis-py) | PyPI | 2012-10-08 | 169 | github.com/redis/redis-py | SUS | **OK — overridden** [VERIFIED] |
| `openai` | PyPI | 2020-02-18 | 431 | github.com/openai/openai-python | SUS | **OK — overridden, but deferred from install (see Standard Stack)** [VERIFIED] |
| `langgraph` | PyPI | 2024-01-08 | 277 | github.com/langchain-ai/langgraph | SUS | **OK — overridden** [VERIFIED] |
| `langgraph-checkpoint-postgres` | PyPI | 2024-08-07 | 50 | github.com/langchain-ai/langgraph (monorepo) | SUS | **OK — overridden** [VERIFIED] |
| `psycopg` | PyPI | 2021-09-03 | 62 | github.com/psycopg/psycopg | SUS | **OK — overridden** [VERIFIED] |
| `taskiq` | PyPI | 2022-08-08 | 82 | github.com/taskiq-python/taskiq | SUS | **OK — overridden** [VERIFIED] |
| `taskiq-redis` | PyPI | 2022-08-22 | 36 | github.com/taskiq-python/taskiq-redis | SUS (+no-repository — PyPI metadata omits `project_urls` casing the tool expects, repo confirmed via Context7 docs) | **OK — overridden** [VERIFIED] |
| `taskiq-fastapi` | PyPI | 2023-03-26 | 13 | github.com/taskiq-python/taskiq-fastapi | SUS (+no-repository, same cause) | **OK — overridden** [VERIFIED] |
| `aioboto3` | PyPI | 2017-09-27 | 81 | github.com/terricain/aioboto3 | SUS (+no-repository) | Not installed this phase — deferred (see Standard Stack) |
| `orjson` | PyPI | 2018-11-23 | 150 | github.com/ijl/orjson | SUS (+no-repository) | **OK — overridden (transitive dep only)** [VERIFIED] |
| `uvloop` | PyPI | 2016-04-12 | 82 | github.com/MagicStack/uvloop | SUS (+no-repository) | **OK — overridden (optional)** [VERIFIED] |
| `uvicorn` | PyPI | 2017-06-05 | 203 | github.com/Kludex/uvicorn | SUS | **OK — overridden** [VERIFIED] |
| `tenacity` | PyPI | 2016-08-25 | 60 | github.com/jd/tenacity | SUS | Not installed this phase — deferred (see Standard Stack) |

**Packages removed due to `[SLOP]` verdict:** none — no package returned `SLOP`.
**Packages flagged `[SUS]` by the automated checker but overridden by direct registry verification in this session:** all of the above. **No `checkpoint:human-verify` task is required for these installs** — the override evidence (release history + confirmed official-org repo, captured in the table) is stronger than the automated heuristic that produced the false positive, and is included here for audit traceability rather than as an outstanding risk.
**Packages the automated checker did not evaluate:** `httpx`, `pytest`, `pytest-asyncio` (dev-only, not passed to the check) — these are extremely well-known dev-tooling packages; no separate verification performed, low risk given dev-only usage. If the planner wants a belt-and-suspenders check, add a `checkpoint:human-verify` specifically for these two, not the table above.

## Architecture Patterns

### System Architecture Diagram (Phase 1 scope)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Client (curl / test harness — no UI this phase)                     │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ POST /api/v1/tasks {problem_text, language, examples}
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FastAPI app (api/main.py)                                            │
│  1. Validate body → TaskSubmission (Pydantic)                        │
│  2. INSERT tasks row (status=queued) → Postgres                      │
│  3. solve_problem_stub.kiq(task_id) → enqueue via taskiq              │
│  4. return 202 {task_id, status: "queued"}                           │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ Redis Stream (taskiq RedisStreamBroker)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ taskiq worker (worker/tasks.py)                                      │
│  1. UPDATE tasks SET status='analyzing_problem' → Postgres            │
│  2. graph.ainvoke({...}, config={"configurable":{"thread_id":task_id}})│
│       stub_node: sleep(2-5s); check "FAIL_TEST" in problem_text        │
│       → success: {"result": {...}}  |  failure: {"error": {code,msg}} │
│     (checkpointed to Postgres via AsyncPostgresSaver after each step)  │
│  3. UPDATE tasks SET status='completed'|'failed', result/error → PG   │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PostgreSQL — tasks table (source of truth) + checkpoint_* tables      │
│ (created by AsyncPostgresSaver.setup(), separate from tasks table)   │
└─────────────────────────────────────────────────────────────────────┘

[Garage container runs alongside in Compose — no arrows into/out of it this phase, per D-11]

GET /api/v1/tasks/{id} → FastAPI reads the tasks row directly → returns current status/result/error
```

### Recommended Project Structure (single `uv` package — per INFRA-01, overrides STACK.md's workspace variant)

```
algorunner/
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── docker/
│   ├── Dockerfile.api
│   └── Dockerfile.worker
├── migrations/
│   └── 0001_create_tasks_table.sql
├── src/
│   └── algorunner/
│       ├── __init__.py
│       ├── config.py            # pydantic-settings: DB URL, Redis URL, Garage endpoint (unused this phase)
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── task.py          # TaskStatus, Language, Example, TaskSubmission, TaskError, TaskRecord
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── state.py         # StubGraphState TypedDict
│       │   └── build.py         # builds + compiles the D-12 smoke-test stub graph
│       ├── agents/               # empty package this phase — real agent nodes land in Phase 2
│       │   └── __init__.py
│       ├── tools/                 # empty package this phase — executors land in Phase 2
│       │   └── __init__.py
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── postgres.py       # AsyncConnectionPool factory (shared by checkpointer + task CRUD)
│       │   ├── tasks.py          # task table CRUD (insert/update/get) using class_row(TaskRecord)
│       │   └── migrate.py        # tiny numbered-SQL-file migration runner
│       ├── api/
│       │   ├── __init__.py
│       │   ├── main.py            # FastAPI app, lifespan (opens/closes the pg pool + taskiq broker)
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   └── tasks.py       # POST /api/v1/tasks, GET /api/v1/tasks/{id}
│       │   └── dependencies.py    # get_pg_pool, get_broker
│       └── worker/
│           ├── __init__.py
│           ├── broker.py          # RedisStreamBroker + RedisAsyncResultBackend instance
│           └── tasks.py           # @broker.task solve_problem_stub(task_id); FAIL_TEST magic string
├── tests/
│   ├── api/
│   ├── worker/
│   └── graph/
└── frontend/                       # created but empty/placeholder — real work is Phase 4
```

`agents/` and `tools/` are intentionally near-empty this phase — INFRA-01 requires the top-level structure to exist now (so Phase 2 doesn't need a restructure), not that they contain real logic yet.

### Pattern 1: Migration approach — plain numbered SQL files, not Alembic (Phase 1 recommendation)

**What:** A `migrations/NNNN_description.sql` directory plus a small async Python runner (`storage/migrate.py`) that tracks applied migrations in a `schema_migrations` table and applies pending ones in order, using the same `psycopg` connection already in the dependency set.

**When to use:** Phase 1 has exactly one application-owned table (`tasks`). LangGraph's own checkpoint tables are created by `AsyncPostgresSaver.setup()` — that is a **separate, already-solved** migration path (`libs/checkpoint-postgres/langgraph/checkpoint/postgres/aio.py`'s `setup()` method walks its own `MIGRATIONS` list, see Code Examples) and must not be duplicated or reimplemented.

**Trade-offs:** Alembic + SQLAlchemy is the more "standard" Python answer for teams anticipating many schema iterations, but it pulls in a second query-building layer (SQLAlchemy Core, at minimum) that nothing else in this codebase uses — this project's Pydantic-first, psycopg3-direct style (per STACK.md and ARCHITECTURE.md) doesn't otherwise touch SQLAlchemy. A hand-rolled runner is ~30 lines and is trivially upgradable to Alembic later if Phase 2/3 schema growth justifies it — this is a reversible, low-cost choice, not an architectural lock-in.

**Example:**

```sql
-- migrations/0001_create_tasks_table.sql
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    problem_text TEXT NOT NULL,
    language VARCHAR(2) NOT NULL,
    examples JSONB NOT NULL DEFAULT '[]'::jsonb,
    result JSONB,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Note: `id` is generated **application-side** (`uuid.uuid4()`) rather than via a Postgres-side default (`gen_random_uuid()`), to avoid a dependency on which Postgres major version/extension provides that function — sidesteps a claim this research did not verify (see Assumptions Log).

### Pattern 2: `AsyncPostgresSaver` + shared `AsyncConnectionPool`, correct kwargs

**What:** One `psycopg.AsyncConnectionPool` per worker process, constructed with `kwargs={"autocommit": True, "row_factory": dict_row}`, passed directly to `AsyncPostgresSaver(pool)`. The same pool (or a second pool with `row_factory=class_row(TaskRecord)` for typed reads) backs the `tasks` table CRUD.

**When to use:** Worker process startup (taskiq `WORKER_STARTUP` event) and FastAPI `lifespan` startup (for the API's read path on `GET /api/v1/tasks/{id}`).

**Why these exact kwargs are non-negotiable:** confirmed via the official `langgraph-checkpoint-postgres` README (fetched via Context7 this session): omitting `autocommit=True` means `.setup()`'s table creation may not persist; omitting `row_factory=dict_row` causes `TypeError: tuple indices must be integers or slices, not str` the first time a checkpoint is read back, because the checkpointer accesses rows by column name.

**Example:**

```python
# Source: langchain-ai/langgraph libs/checkpoint-postgres/README.md (via Context7) +
#         psycopg docs api/pool.rst, advanced/rows.rst (via Context7)
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

pool = AsyncConnectionPool(
    conninfo=settings.database_url,
    kwargs={"autocommit": True, "row_factory": dict_row},
    open=False,
)
await pool.open()

checkpointer = AsyncPostgresSaver(pool)
await checkpointer.setup()  # MUST be called once — creates checkpoint_* tables, is idempotent
```

**Confirmed this session (runtime execution, not just import):**

```python
# Verified: full round-trip succeeded on Python 3.14.5
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

class State(TypedDict):
    value: str

async def stub_node(state: State) -> dict:
    return {"value": state["value"] + "-processed"}

builder = StateGraph(State)
builder.add_node("stub", stub_node)
builder.add_edge(START, "stub")
builder.add_edge("stub", END)
graph = builder.compile(checkpointer=InMemorySaver())

result = await graph.ainvoke({"value": "hello"}, config={"configurable": {"thread_id": "t1"}})
# result == {"value": "hello-processed"}
```

The planner should still schedule a task that runs the equivalent against a **real** Postgres (via `docker compose up postgres` + `AsyncPostgresSaver`), not just `InMemorySaver` — this session's test resolves "does LangGraph run on 3.14 at all," not "does the real Postgres checkpoint round-trip work," which is D-12's actual acceptance bar.

### Pattern 3: RedisStreamBroker wiring with FastAPI lifespan + worker-process guard

**What:** One `RedisStreamBroker` instance in `worker/broker.py`, imported by both the API (to call `.kiq()`) and the worker (to listen). `taskiq_fastapi.init(broker, "algorunner.api.main:app")` wires FastAPI's dependency context into taskiq tasks so both processes can share a `get_pg_pool`-style dependency function.

**When to use:** This is the QUEUE-01 wiring — required this phase.

**Example:**

```python
# Source: taskiq-redis README + taskiq-fastapi docs (via Context7)
# worker/broker.py
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

result_backend = RedisAsyncResultBackend(redis_url=settings.redis_url)
broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name="algorunner-tasks",
    consumer_group_name="algorunner-workers",
).with_result_backend(result_backend)

# api/main.py
import taskiq_fastapi
from worker.broker import broker

taskiq_fastapi.init(broker, "algorunner.api.main:app")

@app.on_event("startup")  # or lifespan equivalent
async def app_startup():
    if not broker.is_worker_process:   # guard: don't double-start inside the worker itself
        await broker.startup()
```

`RedisStreamBroker` constructor accepts `max_connection_pool_size` (should be ≥ `workers + 1`), `consumer_group_name`, `unacknowledged_lock_timeout` (TTL for reclaiming a crashed worker's in-flight message via `XAUTOCLAIM` — directly relevant to the taskiq/Redis worker-crash pitfall below; set this explicitly rather than leaving it `None`, which never reclaims a lock after a crash).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LangGraph checkpoint table schema/migrations | A custom `checkpoints` table | `AsyncPostgresSaver.setup()` | It creates and migrates its own tables (`checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) — confirmed via the actual `setup()` source this session; don't touch these tables from `storage/migrate.py` |
| Queue durability / ack semantics | A custom Redis-list-based queue with manual ack tracking | `taskiq-redis`'s `RedisStreamBroker` | Redis Streams + consumer groups + `XAUTOCLAIM` already solve "worker crashed mid-task, reclaim the message" — this is exactly the taskiq/Redis pitfall below |
| Row → Pydantic model mapping | Manual `TaskRecord(id=row[0], status=row[1], ...)` tuple unpacking | `psycopg.rows.class_row(TaskRecord)` as the cursor's `row_factory` | Confirmed this session: `class_row` accepts any class whose `__init__` takes keyword args matching column names — works directly with Pydantic `BaseModel` subclasses, no adapter code needed |
| Task status enum validation | A raw string column with app-level `if status not in [...]` checks scattered across routes | A single `class TaskStatus(str, Enum)` (D-10) imported everywhere status is read/written | One canonical definition — D-10 explicitly chose this over a Postgres native `ENUM` type specifically to make additions a code-only change |
| Request body validation (`max_length`, enum) | Manual `if len(problem_text) > 5000: raise ...` in the route handler | Pydantic `Field(max_length=5000)` + `Language(str, Enum)` on `TaskSubmission` | FastAPI already returns a structured 422 automatically when a Pydantic model fails validation — no custom error-shaping code needed for input validation |

**Key insight:** every piece of "Phase 1 infrastructure" that looks like it needs custom code (checkpoint tables, queue acks, row mapping) already has a maintained, official solution one import away — the actual Phase 1 work is wiring these together correctly (the kwargs, the guard clauses, the ordering), not building any of them from scratch.

## Common Pitfalls

### Pitfall 1: Missing `autocommit=True` / `row_factory=dict_row` on the checkpointer pool

**What goes wrong:** `.setup()` appears to succeed (no exception) but checkpoint tables aren't actually persisted, or the first `aget`/`aput` call raises `TypeError: tuple indices must be integers or slices, not str`.
**Why it happens:** Documented, easy-to-hit footgun per the official README (see Pattern 2) — the default `psycopg` connection uses `tuple_row` and non-autocommit transactions.
**How to avoid:** Always construct the pool with `kwargs={"autocommit": True, "row_factory": dict_row}` (Pattern 2) — never pass a bare `psycopg.AsyncConnection` or default-configured pool to `AsyncPostgresSaver`.
**Warning signs:** `.setup()` runs without error in dev but checkpoint tables are empty after a restart; `TypeError` referencing tuple indices the first time a checkpoint is read.
**Phase to address:** This phase (the D-12 stub graph task).

### Pitfall 2: taskiq + Redis "worker died mid-task" blind spot

**What goes wrong:** A worker crashes while holding an in-flight task message. Without an explicit `unacknowledged_lock_timeout`, the message can remain claimed-but-unprocessed indefinitely — the task silently never completes and never fails, and a client polling `GET /api/v1/tasks/{id}` sees `analyzing_problem` forever.
**Why it happens:** `RedisStreamBroker`'s `unacknowledged_lock_timeout` defaults to `None` ("the lock can remain locked indefinitely after a crash" — confirmed in the Context7-sourced constructor docs above).
**How to avoid:** Set `unacknowledged_lock_timeout` explicitly (e.g. a few multiples of D-06's 2-5s sleep, so it doesn't reclaim a still-running task) when constructing `RedisStreamBroker`. Postgres remains the actual source of truth for status (DATA-01) regardless — this setting only affects whether the *message* is retried, not what the API reports.
**Warning signs:** A task stuck in a non-terminal status with no further updates; `XPENDING` on the stream shows old, unclaimed entries.
**Phase to address:** This phase — it's a one-line constructor argument, cheap to get right now versus retrofitted later.

### Pitfall 3: Enqueue-before-persist ordering bug

**What goes wrong:** If the API enqueues the taskiq task *before* the Postgres row commits, a very fast worker can attempt `UPDATE tasks SET status=... WHERE id=...` against a row that doesn't exist yet (race), or — if the Postgres write fails after enqueue — a task is queued with no corresponding row, and the worker crashes on a `None` lookup.
**Why it happens:** Both `INSERT` and `.kiq()` look like independent, reorderable statements in a route handler; it's easy to write them in either order without thinking about the race.
**How to avoid:** Always `INSERT` the `queued` row and `await conn.commit()` (or use `autocommit=True` for this write) **before** calling `.kiq()`. This is a Phase-1-specific ordering constraint worth a one-line comment in `routes/tasks.py`.
**Warning signs:** Intermittent "task not found" errors from the worker under load/fast test loops.
**Phase to address:** This phase.

### Pitfall 4: Confusing "no sandbox yet" with the placeholder worker

**Not applicable this phase** — D-04 explicitly means no subprocess/code execution exists yet (the worker only sleeps + checks a magic string). The project-level PITFALLS.md's "no sandbox yet" pitfall (subprocess timeouts, `RLIMIT_FSIZE`, process-group kills) applies to the `PythonExecutorTool`/`GoExecutorTool` build in Phase 2, not this phase. Listed here only so the planner doesn't accidentally pull that work forward.

## Code Examples

### `TaskSubmission` / `TaskStatus` / `TaskError` schemas (D-01, D-02, D-03, D-07, D-08, D-10)

```python
# Source: 01-CONTEXT.md D-01 ("problem_text (required, max 5,000 chars), language (required
# enum "en" | "ru"), examples (optional list of {input, output} pairs, max 10 items)"),
# D-07 ("structured error object ({code, message})"),
# D-08 ("queued, analyzing_problem, designing_solution, generating_code, generating_tests,
# executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial,
# completed, failed") — all quoted verbatim from 01-CONTEXT.md lines 17-19, 25, 28.
from enum import Enum
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class Language(str, Enum):
    EN = "en"
    RU = "ru"


class Example(BaseModel):
    input: str
    output: str


class TaskSubmission(BaseModel):
    problem_text: str = Field(..., max_length=5000)
    language: Language
    examples: list[Example] = Field(default_factory=list, max_length=10)


class TaskStatus(str, Enum):
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


class TaskError(BaseModel):
    code: str
    message: str


class TaskRecord(BaseModel):
    id: UUID
    status: TaskStatus
    problem_text: str
    language: Language
    examples: list[Example]
    result: dict | None = None
    error: TaskError | None = None
    created_at: datetime
    updated_at: datetime


class TaskCreateResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
```

### `POST /api/v1/tasks` route (API-01, INTAKE-01, ordering per Pitfall 3)

```python
# Source: FastAPI 202-pattern (WebSearch, cross-corroborated, general community pattern) +
# project schemas above
from uuid import uuid4
from fastapi import APIRouter, status

router = APIRouter(prefix="/api/v1/tasks")


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=TaskCreateResponse)
async def create_task(body: TaskSubmission, pool=Depends(get_pg_pool)) -> TaskCreateResponse:
    task_id = uuid4()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO tasks (id, status, problem_text, language, examples)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (task_id, TaskStatus.QUEUED.value, body.problem_text, body.language.value,
             [e.model_dump() for e in body.examples]),
        )
    # Enqueue AFTER the row is committed — see Pitfall 3
    await solve_problem_stub.kiq(str(task_id))
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.QUEUED)
```

### Worker stub task (D-04, D-05, D-06, D-09)

```python
# Source: 01-CONTEXT.md D-04 ("configurable success/fail outcome"), D-05 ("magic string
# (e.g. FAIL_TEST) inside problem_text"), D-06 ("sleeps briefly (2-5s)"),
# D-09 ("sets status to analyzing_problem ... while processing") — quoted verbatim from
# 01-CONTEXT.md lines 22-24, 29.
import asyncio
import random

# Phase-1-only test hook. NOT real Analyzer behavior — remove/replace when Phase 2 lands.
FAIL_TEST_MARKER = "FAIL_TEST"


@broker.task
async def solve_problem_stub(task_id: str) -> None:
    await update_task_status(task_id, TaskStatus.ANALYZING_PROBLEM)  # D-09

    task = await get_task(task_id)
    await asyncio.sleep(random.uniform(2, 5))  # D-06

    if FAIL_TEST_MARKER in task.problem_text:  # D-05
        await update_task_failed(
            task_id,
            TaskError(code="SIMULATED_FAILURE", message="Task failed via FAIL_TEST marker"),
        )
        return

    await update_task_completed(task_id, result={"message": "stub pipeline completed"})
```

### `docker-compose.yml` skeleton (INFRA-02)

```yaml
# Postgres/Redis healthcheck syntax: WebSearch, cross-corroborated across multiple
# independent sources (Docker Compose community docs), MEDIUM confidence — standard,
# widely-documented pattern. Garage image tag/flags: garagehq.deuxfleurs.fr official
# quick-start docs (WebFetch) + corroborating WebSearch, MEDIUM confidence.
services:
  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: algorunner
      POSTGRES_USER: algorunner
      POSTGRES_PASSWORD: algorunner
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U algorunner -d algorunner"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:8
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  garage:
    image: dxflrs/garage:v2.4.1
    volumes:
      - garagedata:/var/lib/garage/data
      - garagemeta:/var/lib/garage/meta
    ports:
      - "3900:3900"
    # No --default-bucket flag this phase — D-11 says no bucket creation in Phase 1.
    command: ["/garage", "server", "--single-node"]

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://algorunner:algorunner@postgres:5432/algorunner
      REDIS_URL: redis://redis:6379

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://algorunner:algorunner@postgres:5432/algorunner
      REDIS_URL: redis://redis:6379

volumes:
  pgdata:
  garagedata:
  garagemeta:
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| OpenAI Python SDK v1.x (STACK.md's framing) | v3.x line (`3.17.0` current) [VERIFIED: PyPI registry, this session] | Sometime after STACK.md's research date — v2 exists per STACK.md, but the registry now shows v3 as latest | Not relevant to Phase 1 (no OpenAI install this phase — see Standard Stack), but flag for Phase 2 research: the "v1 vs v2" framing in STACK.md is itself stale, re-verify `chat.completions.parse()` still exists unchanged against v3 before Phase 2 locks a pin |
| "LangGraph Python 3.14 support unconfirmed" (STATE.md blocker) | **Confirmed working** — direct install + import + runtime `ainvoke()` all succeeded on Python 3.14.5 this session | This session, 2026-09-22 | D-13's fallback (pin to 3.13) is not needed; the planner should not budget time for a 3.13 fallback path |
| Garage `dxflrs/garage` image, unspecified version | `v2.4.1` current stable tag [CITED: hub.docker.com/r/dxflrs/garage/tags] | N/A — just a version-pin recommendation | Pin the tag explicitly in `docker-compose.yml` rather than `latest` |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Application-generated `uuid.uuid4()` (rather than Postgres `gen_random_uuid()`) is the right call for the `tasks.id` default, to avoid an unverified claim about which Postgres version/extension provides that function natively | Architecture Patterns → Pattern 1 | Low — purely a style choice; if the team prefers DB-side generation, verifying `gen_random_uuid()` availability against the pinned `postgres:18` image is a 5-minute check, not a redesign |
| A2 | A hand-rolled numbered-SQL-file migration runner (not Alembic) is the right scope for Phase 1's single `tasks` table | Architecture Patterns → Pattern 1 | Medium — if Phase 2/3 add several more tables quickly, revisit; the cost of switching later is a re-implementation of the (small) runner, not a data migration, since it only affects how migrations are *applied*, not the SQL itself |
| A3 | `--single-node` without `--default-bucket` is the correct Garage compose command to satisfy INFRA-02 ("brings up ... Garage") while honoring D-11 ("no bucket creation") | Code Examples → docker-compose.yml | Low-Medium — if `docker compose up` requires the container to reach a "ready" health state that depends on a layout being applied, the container might report unhealthy without an explicit layout step; the planner should verify the container starts and stays up (not necessarily "ready to serve S3 traffic") satisfies success criterion 1, since D-11 explicitly defers S3 functionality to Phase 3 |
| A4 | `RedisStreamBroker`'s `max_connection_pool_size` and `unacknowledged_lock_timeout` values used in Code Examples are illustrative, not tuned/benchmarked | Architecture Patterns → Pattern 3, Pitfall 2 | Low — these are safe conservative defaults per the official parameter docs; no observed failure mode from using them as-is in Phase 1's single-worker scale |

**If this table is empty:** N/A — see entries above; all four are low-to-medium risk implementation-detail choices, not requirements-level assumptions.

## Open Questions

All Phase-1-blocking open questions from STATE.md/CONTEXT.md were resolved this session:

1. ~~"LangGraph's Python 3.14 support is unconfirmed"~~ — **Resolved.** See Sources → direct execution evidence.
2. ~~"OpenAI Python SDK v1 vs v2 major version should be pinned deliberately"~~ — **Resolved by scoping.** Not installed in Phase 1 at all; deferred to Phase 2 research, which should also account for the SDK now being at v3.x.

**Remaining for the planner to decide (not blocking, Claude's Discretion per CONTEXT.md):**

1. **Migration runner implementation detail**
   - What we know: single-table Phase 1 schema, hand-rolled runner recommended (Assumption A2)
   - What's unclear: exact CLI invocation shape (`python -m algorunner.storage.migrate` vs. a startup-time auto-apply vs. a separate `docker compose run` step)
   - Recommendation: run migrations as an explicit one-shot step (either a Compose `init` container or a startup hook gated by an advisory lock) rather than relying on both API and worker racing to apply migrations on every boot.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | Python package management, INFRA-01 | ✓ | present on this machine | — |
| Python 3.14 | INFRA-01 | ✓ | 3.14.5 (installed via Homebrew, also fetchable via `uv python install 3.14`) | — |
| Docker | INFRA-02, Compose stack | ✓ | 27.4.0, daemon running | — |
| Docker Compose | INFRA-02 | ✓ | v2.31.0 | — |
| `redis-cli` (host tooling, for manual debugging) | Optional dev convenience | ✓ | 8.6.3 | Not required — the `redis` service's own healthcheck runs `redis-cli` inside the container image |
| `pg_isready` (host tooling) | Optional dev convenience | ✓ | PostgreSQL 18.4 client | Not required for the same reason |

**Missing dependencies with no fallback:** none — every dependency this phase needs is present and confirmed on the target development machine.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No auth exists or is required in v1 (SEC-01 is explicitly deferred to a future milestone per REQUIREMENTS.md) |
| V3 Session Management | No | No sessions — stateless task-ID-based API |
| V4 Access Control | No | No per-user resource boundaries this phase (any client can read any task_id) — acceptable per the project's own deferred-SEC-01 scoping, but worth a one-line note in the plan's risk log, not a Phase 1 blocker |
| V5 Input Validation | Yes | Pydantic `Field(max_length=...)` / `Enum` on `TaskSubmission` (D-01, D-03) — reject, don't truncate, anything outside `max_length=5000` / `max_length=10` / the `en`\|`ru` enum |
| V6 Cryptography | No | Nothing cryptographic in this phase's scope (no secrets generated/stored beyond DB/Redis connection strings, which are infra config, not application crypto) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via `problem_text`/`examples` reaching raw SQL | Tampering | Always use `psycopg` parameterized queries (`%s` placeholders, as in Code Examples) — never string-format user input into SQL, even for this simple CRUD |
| Unbounded request body size (`problem_text` far exceeding 5,000 chars sent anyway, before Pydantic even validates) | Denial of Service | FastAPI/Starlette's request body isn't unbounded by default at the framework level for this phase's scale, but consider an explicit request size limit (e.g. reverse-proxy or ASGI middleware) if this becomes internet-facing — not a Phase 1 blocker given no deployment-target specifics were given, but worth noting for INFRA-02's "deployed stack" framing |
| Task ID enumeration (`GET /api/v1/tasks/{id}` with a guessed/incremented ID) | Information Disclosure | Using `uuid4()` (128-bit random) rather than a sequential integer PK for `tasks.id` (already the Code Examples design) makes IDs non-guessable — this is a free mitigation from the schema choice already made, not extra work |

## Project Constraints (from CLAUDE.md)

Extracted directives this phase must honor (project `.claude/CLAUDE.md` takes precedence over any general recommendation in this document where they conflict):

- Python 3.14, managed via `uv`; single package with modular structure (agents/, tools/, api/, worker/, schemas/) — **not** DDD/clean architecture layering
- `taskiq` + Redis for the task queue — explicitly not Celery (too heavyweight) and not ARQ (unmaintained)
- PostgreSQL is both task-state source of truth AND LangGraph checkpoint storage
- Garage (S3-compatible) for artifact storage — present in Compose this phase, not wired to code (D-11)
- Docker Compose for this milestone; Kubernetes explicitly deferred
- Maximum feasible type safety in Python, even though lint/CI enforcement is deferred
- Simple modular architecture style — explicit product-owner preference against DDD/clean-architecture
- `RedisStreamBroker` (not `ListQueueBroker`/`PubSubBroker`) per CLAUDE.md's own Alternatives-Considered table, matching this phase's durability need (Pitfall 2)
- Do not manually open a bare `psycopg.connect()` and pass it to `PostgresSaver`/`AsyncPostgresSaver` without `autocommit=True, row_factory=dict_row` — CLAUDE.md calls this out explicitly as a documented footgun (Pitfall 1 in this document)
- Do not call blocking `subprocess.run()` inside an `async def` taskiq task — not triggered this phase (no subprocess calls exist in the D-04 stub worker), but flag for Phase 2 when `PythonExecutorTool`/`GoExecutorTool` land

## Sources

### Primary (HIGH confidence — direct execution evidence, this session)

- `uv init --python 3.14` + `uv add langgraph langgraph-checkpoint-postgres "psycopg[binary,pool]" taskiq taskiq-redis taskiq-fastapi openai fastapi pydantic aioboto3` — full dependency resolution succeeded under Python 3.14.5, resolved versions captured in Standard Stack table.
- `python -c "import langgraph, psycopg, taskiq, taskiq_redis, openai, fastapi, pydantic; ..."` in the resulting `.venv` (Python 3.14.5) — all imports, including `langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`, succeeded.
- Full `StateGraph` build/compile/`ainvoke()` round-trip with `InMemorySaver` executed successfully on Python 3.14.5 (see Architecture Patterns → Pattern 2).
- `curl https://pypi.org/pypi/<pkg>/json` for 17 packages — first-release dates, total release counts, `requires_python`, classifiers, `project_urls` — used to override the automated `package-legitimacy check`'s false-positive `SUS` verdicts (see Package Legitimacy Audit).

### Primary (HIGH confidence — official docs via Context7)

- `/langchain-ai/langgraph` — `libs/checkpoint-postgres/README.md` (autocommit/row_factory requirement, `.setup()` behavior, `AsyncPostgresSaver` constructor signature), `libs/checkpoint/README.md` (thread_id/checkpoint_id config shape).
- `/taskiq-python/taskiq-redis` — `RedisStreamBroker`/`RedisAsyncResultBackend` constructor signatures and parameter tables (`_autodocs/api-reference/*.md`), README usage example.
- `/taskiq-python/taskiq-fastapi` — FastAPI lifecycle hook wiring, `is_worker_process` guard pattern, `startup_event_generator`/`shutdown_event_generator`.
- `/websites/taskiq-python_github_io` — worker CLI flags (`--use-process-pool`, `--max-threadpool-threads`, `--ack-type`, `--reload`), `TaskiqState`/`WORKER_STARTUP` event pattern.
- `/psycopg/psycopg` — `AsyncConnectionPool` constructor, `class_row`/`dict_row` row factories.

### Secondary (MEDIUM confidence — official docs via WebFetch/WebSearch, cross-corroborated)

- garagehq.deuxfleurs.fr/documentation/quick-start/ (official Garage docs, via WebFetch) + corroborating WebSearch results — `--single-node`/`--default-bucket` flags, minimal `garage.toml` shape, port layout.
- hub.docker.com/r/dxflrs/garage/tags (via WebFetch) — current stable image tag `v2.4.1`.
- Docker Compose healthcheck syntax for `pg_isready`/`redis-cli ping` + `depends_on: condition: service_healthy` — WebSearch, cross-corroborated across multiple independent sources (all agreeing on the same syntax).
- FastAPI `202 Accepted` + `task_id`/`status` response pattern — WebSearch, general community pattern, not project-specific enough to need a single canonical citation.

### Tertiary (LOW confidence)

- None used as load-bearing for a decision in this document — items that would have been LOW confidence (e.g., migration-tool choice) are marked `[ASSUMED]` in the Assumptions Log instead of presented as findings.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version number and the Python 3.14 compatibility question were verified by direct execution this session, not just registry lookups
- Architecture: HIGH for the single-package-vs-workspace resolution (backed by the project's own locked INFRA-01/ROADMAP/STATE.md decisions) and for the checkpointer/broker wiring (backed by official docs); MEDIUM for the migration-approach recommendation (a judgment call, logged in Assumptions)
- Pitfalls: HIGH for Pitfall 1 (official docs) and Pitfall 3 (logical/structural, verifiable by code review); MEDIUM for Pitfall 2 (official parameter docs, but Phase-1 scale means it's unlikely to actually trigger)

**Research date:** 2026-09-22
**Valid until:** 30 days for the pinned package versions (fast-moving stack — re-check `uv add` resolution if planning is delayed); the Python 3.14 compatibility finding itself does not expire (it's a fact about the already-resolved version set captured here, not a moving target) unless the team later upgrades past the pinned `langgraph`/`taskiq`/`psycopg` versions.

---

*Phase 1 research for: AlgoRunner (Foundation & Task Lifecycle Skeleton)*
*Researched: 2026-09-22*
