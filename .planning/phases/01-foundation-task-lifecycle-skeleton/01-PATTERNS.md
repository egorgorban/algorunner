# Phase 1: Foundation & Task Lifecycle Skeleton - Pattern Map

**Mapped:** 2026-09-22
**Files analyzed:** 27
**Analogs found:** 0 / 27 (greenfield repository — see below)

## Greenfield Notice

This repository contains **no application source code**. `git ls-files` (excluding `.planning/` and `.claude/`) returns only `.gitignore` and `interview.md`. There is no `src/`, no existing Python/SQL/YAML/Dockerfile of any kind, and no prior commit that introduced application code. Every file listed below is a **first occurrence of its pattern in this codebase** — there is no closest analog to point to, tracked or otherwise (the tracked-source gate in Step 3 is moot here: nothing exists to gate).

Because the planner's downstream format expects "Closest Analog" and code excerpts, this document instead points each file at the **concrete code example already vetted in `01-RESEARCH.md` → Code Examples / Architecture Patterns**, quoting those exact blocks with line references into RESEARCH.md. These are not codebase analogs — they are the phase researcher's verified reference implementations (confirmed by direct execution against Python 3.14.5 this session per RESEARCH.md Sources). Treat every "Analog" cell below as `RESEARCH.md` (not a source file), and treat the whole of Phase 1 as establishing the patterns Phase 2+ will then have real analogs to copy from.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|-----------------|----------------|
| `pyproject.toml` | config | — | none | no analog (greenfield) |
| `docker-compose.yml` | config | — | none | no analog (greenfield) |
| `docker/Dockerfile.api` | config | — | none | no analog (greenfield) |
| `docker/Dockerfile.worker` | config | — | none | no analog (greenfield) |
| `migrations/0001_create_tasks_table.sql` | migration | batch | none | no analog (greenfield) |
| `src/algorunner/config.py` | config | — | none | no analog (greenfield) |
| `src/algorunner/schemas/task.py` | model | CRUD | none | no analog (greenfield) |
| `src/algorunner/graph/state.py` | model | event-driven | none | no analog (greenfield) |
| `src/algorunner/graph/build.py` | service | event-driven | none | no analog (greenfield) |
| `src/algorunner/storage/postgres.py` | service | CRUD | none | no analog (greenfield) |
| `src/algorunner/storage/tasks.py` | service | CRUD | none | no analog (greenfield) |
| `src/algorunner/storage/migrate.py` | utility | batch | none | no analog (greenfield) |
| `src/algorunner/api/main.py` | provider | request-response | none | no analog (greenfield) |
| `src/algorunner/api/routes/tasks.py` | controller | request-response | none | no analog (greenfield) |
| `src/algorunner/api/dependencies.py` | provider | request-response | none | no analog (greenfield) |
| `src/algorunner/worker/broker.py` | provider | pub-sub | none | no analog (greenfield) |
| `src/algorunner/worker/tasks.py` | controller | event-driven | none | no analog (greenfield) |
| `tests/api/test_tasks.py` | test | request-response | none | no analog (greenfield) |
| `tests/worker/test_tasks.py` | test | event-driven | none | no analog (greenfield) |
| `tests/graph/test_build.py` | test | event-driven | none | no analog (greenfield) |

## Pattern Assignments

### `src/algorunner/schemas/task.py` (model, CRUD)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Code Examples → `TaskSubmission` / `TaskStatus` / `TaskError` schemas" (RESEARCH.md lines 375-441)

**Core pattern** (RESEARCH.md lines 384-441): `Language(str, Enum)`, `Example(BaseModel)`, `TaskSubmission(BaseModel)` with `Field(..., max_length=5000)` and `Field(default_factory=list, max_length=10)`, `TaskStatus(str, Enum)` (D-10: plain-string column validated by app-level enum, all 12 statuses per D-08), `TaskError(BaseModel)` with `{code, message}` (D-07), `TaskRecord(BaseModel)` (full row shape incl. `result: dict | None`, `error: TaskError | None`), `TaskCreateResponse(BaseModel)`.

**Validation pattern:** Pydantic `Field(max_length=...)` + `Enum` membership does all input validation (D-03) — FastAPI auto-returns 422 on failure, no manual `if len(...)` checks needed (RESEARCH.md "Don't Hand-Roll" table, row 5).

**Note:** every field name/constraint here is locked by CONTEXT.md decisions D-01/D-02/D-03/D-07/D-08/D-10 — this is not a stylistic choice, follow verbatim.

---

### `src/algorunner/storage/postgres.py` (service, CRUD)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Architecture Patterns → Pattern 2: `AsyncPostgresSaver` + shared `AsyncConnectionPool`" (RESEARCH.md lines 243-293)

**Core pattern** (RESEARCH.md lines 256-269):
```python
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

**Non-negotiable kwargs (Pitfall 1, RESEARCH.md lines 345-351):** `autocommit=True, row_factory=dict_row` — omitting either causes silent checkpoint-persistence failure or a `TypeError: tuple indices must be integers or slices, not str` on first checkpoint read. Never pass a bare `psycopg.connect()` result to `AsyncPostgresSaver` (also called out in project CLAUDE.md's "What NOT to Use" table).

**Shared-pool note:** the same pool (or a second pool configured with `row_factory=class_row(TaskRecord)`) backs `storage/tasks.py`'s CRUD — don't construct a second ad-hoc connection path for task-table reads/writes.

---

### `src/algorunner/storage/tasks.py` (service, CRUD)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Don't Hand-Roll" table, row 3 (RESEARCH.md line 337) + `POST /api/v1/tasks` route example (RESEARCH.md lines 443-469)

**Core pattern:** use `psycopg.rows.class_row(TaskRecord)` as the cursor's `row_factory` for typed reads — "accepts any class whose `__init__` takes keyword args matching column names — works directly with Pydantic `BaseModel` subclasses, no adapter code needed" (RESEARCH.md line 337). Parameterized `%s` placeholders only, per Security Domain → SQL injection mitigation (RESEARCH.md line 638) — never string-format `problem_text`/`examples` into SQL.

**Insert pattern** (RESEARCH.md lines 457-465):
```python
async with pool.connection() as conn:
    await conn.execute(
        """
        INSERT INTO tasks (id, status, problem_text, language, examples)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (task_id, TaskStatus.QUEUED.value, body.problem_text, body.language.value,
         [e.model_dump() for e in body.examples]),
    )
```

**Ordering constraint (Pitfall 3, RESEARCH.md lines 361-367):** the `INSERT` (queued row) must commit **before** `.kiq()` enqueues the task — reversed order risks the worker racing a not-yet-committed row, or an orphaned queue message if the insert fails after enqueue. This applies equally to `update_task_status`/`update_task_completed`/`update_task_failed` helpers this file should expose (used by `worker/tasks.py`).

---

### `src/algorunner/graph/state.py` + `src/algorunner/graph/build.py` (service, event-driven)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Architecture Patterns → Pattern 2" runtime-verified example (RESEARCH.md lines 271-293)

**Core pattern** (RESEARCH.md lines 279-292, confirmed by direct execution on Python 3.14.5 this session):
```python
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
```

**Production deviation required:** swap `InMemorySaver()` for the real `AsyncPostgresSaver(pool)` from `storage/postgres.py` (D-12 — this is the actual acceptance bar, not the in-memory smoke test — RESEARCH.md line 295). `thread_id` in the `configurable` config must be set to the string form of `task_id`, establishing the 1:1 `task_id` ↔ `thread_id` mapping CLAUDE.md's "Stack Patterns by Variant" section requires for resumability.

**Purpose framing (D-12/D-13, CONTEXT.md lines 34, 77):** this graph is explicitly a Python 3.14/LangGraph compatibility smoke test, not functional pipeline logic — keep `stub_node` trivial (wraps the D-04–D-07 success/fail placeholder logic), don't over-build.

---

### `src/algorunner/api/routes/tasks.py` (controller, request-response)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Code Examples → `POST /api/v1/tasks` route" (RESEARCH.md lines 443-469) + "Don't Hand-Roll" table row 5

**Core pattern** (RESEARCH.md lines 454-469):
```python
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

**GET route:** RESEARCH.md line 41 specifies this as "a thin read of the Postgres row; no computation" via `class_row(TaskRecord)` — no separate example block exists in RESEARCH.md; build it as `SELECT * FROM tasks WHERE id = %s` mapped through `class_row(TaskRecord)`, returning 404 if no row (this shape is implied but not spelled out verbatim in RESEARCH.md — flag as first-occurrence, not extracted).

**Error handling pattern:** input validation errors are handled entirely by FastAPI's automatic 422 on Pydantic `TaskSubmission` failure (no custom try/catch needed — RESEARCH.md "Don't Hand-Roll" row 5). No other error-handling convention exists yet in this codebase; this file establishes it.

---

### `src/algorunner/worker/broker.py` (provider, pub-sub)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Architecture Patterns → Pattern 3: RedisStreamBroker wiring" (RESEARCH.md lines 297-329)

**Core pattern** (RESEARCH.md lines 308-327):
```python
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

**Non-default parameter required (Pitfall 2, RESEARCH.md lines 353-359):** must explicitly set `unacknowledged_lock_timeout` (e.g. a few multiples of the D-06 2-5s sleep) — default is `None`, meaning a crashed worker's claimed-but-unprocessed message never gets reclaimed via `XAUTOCLAIM`, and Postgres status silently never advances past `analyzing_problem`.

**FastAPI lifespan note:** CLAUDE.md's Stack section explicitly prefers `lifespan` context manager over the deprecated `@app.on_event`; RESEARCH.md's example uses `@app.on_event("startup")` for brevity — `api/main.py` should use the `lifespan` form instead, keeping the same `is_worker_process` guard logic.

---

### `src/algorunner/worker/tasks.py` (controller, event-driven)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Code Examples → Worker stub task" (RESEARCH.md lines 471-500)

**Core pattern** (RESEARCH.md lines 483-500):
```python
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

**Integration point:** this task body should also invoke `graph/build.py`'s compiled stub graph (D-12) — RESEARCH.md's worker example predates the graph-invocation wiring shown separately in the architecture diagram (RESEARCH.md lines 128-162): `graph.ainvoke({...}, config={"configurable":{"thread_id": task_id}})` sits between the status update and the sleep/fail-check, per the diagram's step 2. Merge both examples rather than treating them as alternatives.

**Constraint from CLAUDE.md:** do not call blocking `subprocess.run()` inside this `async def` task — not triggered yet (no subprocess in Phase 1's stub), but this file is the template Phase 2's `PythonExecutorTool`/`GoExecutorTool` invocation will extend, so keep it fully async now (`asyncio.sleep`, not `time.sleep`) to avoid establishing a blocking-call precedent.

---

### `migrations/0001_create_tasks_table.sql` (migration, batch)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Architecture Patterns → Pattern 1: Migration approach" (RESEARCH.md lines 216-241)

**Core pattern** (RESEARCH.md lines 227-239):
```sql
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

**Scope boundary:** do not touch/duplicate LangGraph's own `checkpoint_migrations`/`checkpoints`/`checkpoint_blobs`/`checkpoint_writes` tables — those are owned exclusively by `AsyncPostgresSaver.setup()` (RESEARCH.md "Don't Hand-Roll" row 1, line 335). `id` is generated application-side via `uuid.uuid4()`, not `gen_random_uuid()` (Assumption A1, RESEARCH.md line 588) — keep ID generation in Python, not SQL.

**Runner:** `storage/migrate.py` is a hand-rolled ~30-line numbered-file runner tracking a `schema_migrations` table (RESEARCH.md Pattern 1, lines 216-222) — explicitly not Alembic/SQLAlchemy for Phase 1's single-table scope.

---

### `docker-compose.yml` / `docker/Dockerfile.api` / `docker/Dockerfile.worker` (config)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` → "Code Examples → `docker-compose.yml` skeleton" (RESEARCH.md lines 502-574)

**Core pattern** (full block at RESEARCH.md lines 509-574): five services (`postgres:18`, `redis:8`, `dxflrs/garage:v2.4.1`, `api`, `worker`), Postgres/Redis with `healthcheck` + `depends_on: condition: service_healthy` gating the `api`/`worker` services. Garage runs `--single-node` with **no** `--default-bucket` flag (D-11 — present but unwired, RESEARCH.md line 539).

**Environment wiring:** `DATABASE_URL`/`REDIS_URL` passed as plain env vars matching the compose service DNS names (`postgres`, `redis`) — see block for exact connection strings.

---

### `src/algorunner/config.py` (config)

**Analog:** none (greenfield) — reference: `01-RESEARCH.md` Standard Stack table (RESEARCH.md line 63) names `pydantic-settings` for this purpose; no full code excerpt is given in RESEARCH.md for this specific file — first occurrence, not extracted verbatim. Build a `BaseSettings` subclass exposing `database_url`, `redis_url`, and a Garage endpoint setting (unused this phase per D-11, but present so Phase 3 doesn't need a config reshape).

---

### `tests/api/test_tasks.py`, `tests/worker/test_tasks.py`, `tests/graph/test_build.py` (test)

**Analog:** none (greenfield) — reference: RESEARCH.md Supporting stack table (lines 78-79) names `httpx` (via FastAPI `TestClient`) and `pytest`/`pytest-asyncio` as the tooling, but gives no example test code. First occurrence — no test-file convention exists yet in this repo. Establish the pattern: `pytest-asyncio` async test functions, FastAPI `TestClient`/`httpx.AsyncClient` against the route handlers in `api/routes/tasks.py`, and a real-Postgres round-trip test for the stub graph per RESEARCH.md line 295 ("the planner should still schedule a task that runs the equivalent against a real Postgres... not just `InMemorySaver`").

## Shared Patterns

### Postgres connection kwargs (autocommit + dict_row)
**Source:** `01-RESEARCH.md` lines 256-269 (Pattern 2) — no in-repo source, first occurrence
**Apply to:** `storage/postgres.py`, `storage/tasks.py`, `storage/migrate.py`, any code constructing a `psycopg` pool/connection
```python
kwargs={"autocommit": True, "row_factory": dict_row}
```
Never construct a bare `psycopg.connect()`/pool without these kwargs (CLAUDE.md "What NOT to Use" table; RESEARCH.md Pitfall 1).

### Status vocabulary (TaskStatus enum)
**Source:** `01-RESEARCH.md` lines 406-418 (D-08, D-10) — first occurrence
**Apply to:** `schemas/task.py` (definition), `storage/tasks.py` (writes), `api/routes/tasks.py` (reads/response), `worker/tasks.py` (transitions)
Single canonical `class TaskStatus(str, Enum)` with all 12 values defined now even though only `queued`/`analyzing_problem`/`completed`/`failed` are reachable this phase — plain varchar column, no native Postgres `ENUM`.

### Structured error shape ({code, message})
**Source:** `01-RESEARCH.md` lines 421-423 (D-07) — first occurrence
**Apply to:** `schemas/task.py` (`TaskError`), `storage/tasks.py` (`update_task_failed`), `worker/tasks.py` (failure branch), `api/routes/tasks.py` (GET response when `status=failed`)
Never store/return a plain error string — always `{code, message}`, since this is a locked, costly-to-reverse API contract per CONTEXT.md D-07.

### Enqueue-after-commit ordering
**Source:** `01-RESEARCH.md` lines 361-367 (Pitfall 3) — first occurrence
**Apply to:** `api/routes/tasks.py` (POST handler) — any future route that both writes a DB row and enqueues a task
`INSERT`/commit the row before calling `.kiq()`, never the reverse.

### Redis broker durability config
**Source:** `01-RESEARCH.md` lines 297-329 (Pattern 3), Pitfall 2 lines 353-359 — first occurrence
**Apply to:** `worker/broker.py` only (single instantiation point, imported by both API and worker)
`RedisStreamBroker` with explicit `unacknowledged_lock_timeout`, `consumer_group_name`, shared between `.kiq()` callers (API) and the listening worker.

## No Analog Found

All 20 files in File Classification have no in-repo analog — this is a from-scratch greenfield phase. Every entry above points to `01-RESEARCH.md`'s verified Code Examples/Architecture Patterns as the reference implementation instead of a codebase analog. The planner should treat `01-RESEARCH.md` as the de facto pattern source for Phase 1, and treat the files this phase produces as the analogs Phase 2's `gsd-phase-pattern-mapper` run will then find.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| all 20 files listed in File Classification | (varies) | (varies) | Repository is greenfield — `git ls-files` (excluding `.planning/`, `.claude/`) returns only `.gitignore` and `interview.md`; no prior application code of any kind exists to analogize from |

## Metadata

**Analog search scope:** entire git-tracked repository (`git ls-files`, excluding `.planning/` and `.claude/`)
**Files scanned:** 2 tracked non-planning files (`.gitignore`, `interview.md`) — neither is a code analog
**Pattern extraction date:** 2026-09-22
**Pattern source used instead:** `.planning/phases/01-foundation-task-lifecycle-skeleton/01-RESEARCH.md` (Code Examples + Architecture Patterns sections, all confirmed by direct execution against Python 3.14.5 per RESEARCH.md's own Sources section)
