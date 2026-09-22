---
phase: 01-foundation-task-lifecycle-skeleton
reviewed: 2026-09-22T19:49:57Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - src/algorunner/api/main.py
  - src/algorunner/api/routes/tasks.py
  - src/algorunner/api/dependencies.py
  - src/algorunner/config.py
  - src/algorunner/graph/build.py
  - src/algorunner/graph/state.py
  - src/algorunner/schemas/task.py
  - src/algorunner/storage/postgres.py
  - src/algorunner/storage/tasks.py
  - src/algorunner/storage/migrate.py
  - src/algorunner/worker/broker.py
  - src/algorunner/worker/tasks.py
  - migrations/0001_create_tasks_table.sql
  - docker-compose.yml
  - docker/garage/garage.toml
  - tests/api/test_tasks.py
  - tests/graph/test_build.py
findings:
  critical: 4
  warning: 3
  info: 1
  total: 8
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-09-22T19:49:57Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

8-angle finder pass + 1-vote verification (recall-biased) over `git diff 4ceb6d1...HEAD` (all of phase 01's new task-lifecycle/LangGraph/FastAPI/taskiq code). 10 candidates were verified against the actual code and installed dependency source; 8 confirmed, 2 refuted (migrate.py's `parents[3]` path arithmetic is correct as written; psycopg3's simple-query protocol does support multi-statement migration files when unparameterized, contrary to the candidate claim). The confirmed issues cluster around two themes: (1) `solve_problem_stub` has no failure-surfacing path — an exception or a missing task row both result in a task that silently never reaches a terminal, truthful status, which cuts against this project's stated core value that correctness is verified and failures are always structured; and (2) the worker process constructs Postgres resources (connection pool, checkpointer setup) redundantly and without idempotency-safe locking. None of these block basic functionality demonstrated in the executors' own manual verification (the happy path works end-to-end against live Postgres/Redis/Docker), but several are real gaps in the failure-handling and resource-lifecycle design that Phase 2 will build directly on top of.

## Critical Issues

### CR-01: No exception handling in `solve_problem_stub` — unhandled errors leave a task stuck non-terminal forever

**File:** `src/algorunner/worker/tasks.py:36`
**Issue:** The entire task body has no `try`/`except`, and no taskiq-level error hook exists in `worker/broker.py`. If any exception is raised after `update_task_status(..., ANALYZING_PROBLEM)` (line 45) but before a terminal write, the task's row stays at that non-terminal status forever; `GET /api/v1/tasks/{id}` reports it indefinitely with no way for a client to learn the task failed.
**Fix:**
```python
async def solve_problem_stub(task_id: str) -> None:
    try:
        ...  # existing body
    except Exception as exc:
        await update_task_failed(_pool, UUID(task_id), TaskError(message=str(exc)))
        raise
```

### CR-02: Missing task row silently produces a false "completed" result

**File:** `src/algorunner/worker/tasks.py:47`
**Issue:** When `get_task` returns `None` (deleted row, redelivered stale message, corrupted id), the code substitutes `problem_text = ""` and proceeds through the graph to `update_task_completed`, which issues a 0-row `UPDATE` that raises nothing. No error is logged or recorded anywhere — the worker reports success for a task that never really ran.
**Fix:**
```python
task = await get_task(_pool, UUID(task_id))
if task is None:
    logger.error("solve_problem_stub: task %s not found, aborting", task_id)
    return
problem_text = task.problem_text
```

### CR-03: `checkpointer.setup()` called unprotected on every invocation races on concurrent first boot

**File:** `src/algorunner/worker/tasks.py:51`
**Issue:** `AsyncPostgresSaver.setup()` (verified against the installed `langgraph-checkpoint-postgres` source) reads the max applied migration version and then `INSERT`s into `checkpoint_migrations(v)` (a primary key) without locking. Two tasks processed concurrently right after a fresh deploy can both read "no migrations applied" and both attempt to insert the same key, raising `psycopg.errors.UniqueViolation` in the loser. The inline comment ("idempotent — safe to call every invocation") is true only once the table is populated.
**Fix:** Run `checkpointer.setup()` once at `WORKER_STARTUP` (alongside `run_migrations_with_lock`, under the same advisory lock) instead of per-task-invocation, and reuse one compiled graph/checkpointer for the process lifetime.

### CR-04: Body-size DoS middleware is bypassed by chunked or missing `Content-Length`

**File:** `src/algorunner/api/main.py:49`
**Issue:** `limit_body_size` only rejects a request when the `content-length` header is present and parses as an int; a missing header (`Transfer-Encoding: chunked`) or malformed value silently falls through to unbounded Pydantic parsing — defeating the middleware's own stated purpose of mitigating T-01-03 before body parsing runs. The only existing test always sets `Content-Length` (httpx JSON POST), so this gap is untested.
**Fix:** Enforce the limit against actual bytes read from `request.stream()` (abort once the running total exceeds `MAX_BODY_BYTES`), independent of whether a trustworthy `Content-Length` header was sent, or push the cap to the ASGI-server/reverse-proxy layer.

## Warnings

### WR-01: Duplicate, orphaned Postgres connection pool per worker process

**File:** `src/algorunner/worker/broker.py:32`
**Issue:** `_on_worker_startup` builds its own `AsyncConnectionPool` via `get_pool()` (unmemoized — a new instance every call) and stores it as `state.pg_pool`, which is never read anywhere else in the codebase. `worker/tasks.py:32` independently constructs a second pool for all real queries and checkpointing — contradicting `storage/postgres.py`'s own docstring against constructing a second pool. Each worker process ends up holding roughly double the intended idle Postgres connections.
**Fix:** Make `get_pool()` memoize a singleton per process, or have `_on_worker_startup` reuse the same pool object `worker/tasks.py` uses instead of calling `get_pool()` a second time.

### WR-02: `get_task` has no defense against a `status` value that fails `TaskRecord` validation

**File:** `src/algorunner/storage/tasks.py:36`
**Issue:** `status` is a plain `VARCHAR(32)` with no DB-level CHECK/ENUM tying it to the Python `TaskStatus` enum. A drifted value raises an unhandled `pydantic.ValidationError` from inside `class_row(TaskRecord)`'s row construction, with no exception handler registered anywhere in `api/main.py`, surfacing as a raw, unstructured 500 instead of this project's normal structured error shape.
**Fix:** Add a Postgres CHECK constraint (or enum type) on `status` matching `TaskStatus`'s values, and/or wrap the row-construction in a try/except that raises a structured `TaskError`.

### WR-03: Migration advisory-lock holder nests a second pool checkout for the whole run

**File:** `src/algorunner/storage/migrate.py:68`
**Issue:** `run_migrations_with_lock` holds one pool connection for the entire `pg_advisory_lock` duration while `apply_pending_migrations` checks out a second, independent connection from the same pool. This is masked today only because the pool's default `min_size`/`max_size` both resolve to 4; a future `max_size=1` configuration (plausible for a resource-constrained deployment) would deadlock the second checkout until the 30s default `PoolTimeout`, failing container startup with an opaque pool-timeout error instead of a real migration error.
**Fix:** Pass the already-held `conn` into `apply_pending_migrations` instead of having it request a fresh one from `pool`.

## Info

### IN-01: `docker/garage/garage.toml`'s `rpc_secret` is committed to git despite being documented as "gitignored"

**File:** `docker/garage/garage.toml:9`
**Issue:** `01-01-SUMMARY.md` justifies this deviation as safe because the file is "gitignored" — but `git ls-files`/`git check-ignore` confirm it is tracked and committed in plaintext (commit `9c9cefb`). Severity is mitigated by Garage being inert/unwired in this phase (per the same SUMMARY note), but the documentation claim is factually wrong and would mislead a future contributor copying this compose file into a real deployment.
**Fix:** Either actually gitignore the file and generate `rpc_secret` at first boot, or correct the SUMMARY's justification to state it is intentionally committed dev-only.

---

_Reviewed: 2026-09-22T19:49:57Z_
