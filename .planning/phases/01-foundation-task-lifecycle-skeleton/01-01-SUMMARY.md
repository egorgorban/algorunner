---
phase: 01-foundation-task-lifecycle-skeleton
plan: 01
subsystem: infra
tags: [fastapi, taskiq, taskiq-redis, psycopg, postgres, docker-compose, pydantic, uv]

# Dependency graph
requires: []
provides:
  - "algorunner uv-managed single package (schemas/, storage/, worker/, api/, agents/, tools/)"
  - "TaskSubmission/TaskStatus (12 values)/TaskError/TaskRecord/TaskCreateResponse Pydantic schemas"
  - "tasks table + numbered-SQL migration runner (apply_pending_migrations, run_migrations_with_lock)"
  - "Shared psycopg AsyncConnectionPool (autocommit=True, row_factory=dict_row)"
  - "taskiq RedisStreamBroker + solve_problem_stub placeholder worker task"
  - "POST /api/v1/tasks and GET /api/v1/tasks/{id} FastAPI routes"
  - "5-service docker-compose.yml (postgres, redis, garage, api, worker) + Dockerfile.api/Dockerfile.worker"
affects: [01-02-graph-wiring, phase-02-solver-pipeline]

# Actuals (#2632)
actuals:
  tokens: 5420
  tasks: 2
  commits: 2
plan_head_before: 4ceb6d15c96e4f4c8a54039f293777b4572be471

# Tech tracking
tech-stack:
  added: [langgraph, langgraph-checkpoint-postgres, "psycopg[binary,pool]", taskiq, taskiq-redis, taskiq-fastapi, fastapi, "uvicorn[standard]", pydantic, pydantic-settings, pytest, pytest-asyncio, httpx]
  patterns:
    - "Shared AsyncConnectionPool with autocommit=True + row_factory=dict_row for the pool, class_row(TaskRecord) per-cursor for typed reads"
    - "Insert-then-enqueue ordering (INSERT commits before .kiq())"
    - "Postgres advisory-lock-gated migration runner shared by api lifespan and worker WORKER_STARTUP"
    - "psycopg3 Jsonb(...) wrapper required for any dict/list bound to a JSONB column"

key-files:
  created:
    - src/algorunner/schemas/task.py
    - src/algorunner/storage/postgres.py
    - src/algorunner/storage/tasks.py
    - src/algorunner/storage/migrate.py
    - src/algorunner/worker/broker.py
    - src/algorunner/worker/tasks.py
    - src/algorunner/api/main.py
    - src/algorunner/api/routes/tasks.py
    - migrations/0001_create_tasks_table.sql
    - docker-compose.yml
    - docker/Dockerfile.api
    - docker/Dockerfile.worker
  modified: []

key-decisions:
  - "psycopg3 requires explicit Jsonb(...) wrapping for any Python dict/list bound to a JSONB column parameter — RESEARCH.md's insert example omitted this; without it psycopg3 raises a type-adaptation error at execute time"
  - "psycopg_pool.AsyncConnectionPool has no .opened attribute (only .closed) — pool.open() is documented as safe to call repeatedly on an already-open pool, so all call sites now call it unconditionally instead of guarding on a nonexistent attribute"
  - "storage/migrate.py's MIGRATIONS_DIR must resolve via Path(__file__).resolve().parents[3] (repo root), not parents[2] (which resolves to src/) — fixed the off-by-one from the plan text"
  - "pytest-asyncio requires asyncio_default_fixture_loop_scope=session and asyncio_default_test_loop_scope=session in pyproject.toml; without them a session-scoped async Postgres pool fixture is opened on one event loop and awaited from a different per-test loop, which hangs indefinitely rather than raising"
  - "Garage v2.4.1 requires an explicit /etc/garage.toml (metadata_dir, data_dir, replication_factor, rpc_bind_addr/rpc_public_addr/rpc_secret, [s3_api], [admin]) even when run with --single-node — RESEARCH.md/PATTERNS.md's compose skeleton had no config file, so garage exited immediately; added docker/garage/garage.toml (bind-mounted, gitignored secret is fine here since Garage is inert/unwired per D-11)"

patterns-established:
  - "All async Postgres CRUD helpers take an explicit AsyncConnectionPool as their first argument (no implicit global connection)"
  - "FAIL_TEST_MARKER as a single source of truth in worker/tasks.py, documented as a Phase-1-only test hook not to be mistaken for real Analyzer behavior"

requirements-completed: [INTAKE-01, ORCH-02, API-01, API-02, QUEUE-01, DATA-01, INFRA-01, INFRA-02]

coverage:
  - id: D1
    description: "POST /api/v1/tasks validates TaskSubmission and returns 202 + task_id + status=queued, INSERT committed before .kiq() enqueue"
    requirement: "API-01"
    verification:
      - kind: unit
        ref: "tests/api/test_tasks.py#test_create_task_returns_202_and_queued"
        status: pass
      - kind: e2e
        ref: "curl -X POST http://localhost:8000/api/v1/tasks against the containerized stack -> 202 {task_id, status: queued}"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /api/v1/tasks/{id} is a thin Postgres read reflecting live status, 404 on unknown id"
    requirement: "API-02"
    verification:
      - kind: unit
        ref: "tests/api/test_tasks.py#test_get_task_reflects_live_status"
        status: pass
      - kind: e2e
        ref: "curl http://localhost:8000/api/v1/tasks/00000000-0000-0000-0000-000000000000 -> 404 against the containerized stack"
        status: pass
    human_judgment: false
  - id: D3
    description: "solve_problem_stub transitions queued -> analyzing_problem -> completed on the happy path via taskiq + Redis"
    requirement: "QUEUE-01"
    verification:
      - kind: unit
        ref: "tests/worker/test_tasks.py#test_solve_problem_stub_happy_path_completes"
        status: pass
      - kind: e2e
        ref: "containerized POST -> poll GET round trip reached status=completed"
        status: pass
    human_judgment: false
  - id: D4
    description: "A FAIL_TEST-marked task transitions to failed with a structured {code, message} error, never a plain string"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/worker/test_tasks.py#test_solve_problem_stub_fail_test_marker_fails_with_structured_error"
        status: pass
    human_judgment: false
  - id: D5
    description: "docker compose up -d --build brings up postgres, redis, garage, api, worker together; re-running does not re-apply migrations"
    requirement: "INFRA-02"
    verification:
      - kind: e2e
        ref: "docker compose up -d --build (run twice); docker compose ps showing all 5 services Up/healthy; docker compose logs api/worker showing no unhandled exception"
        status: pass
    human_judgment: false
  - id: D6
    description: "tasks table + schema_migrations tracking table created via a numbered-SQL migration runner, idempotent on re-run"
    requirement: "DATA-01"
    verification:
      - kind: other
        ref: "uv run python -m algorunner.storage.migrate (first run: applies 0001; second run: No pending migrations)"
        status: pass
    human_judgment: false

duration: 42min
completed: 2026-09-22
status: complete
---

# Phase 1 Plan 1: Foundation & Task Lifecycle Skeleton Summary

**FastAPI + taskiq/Redis + Postgres task lifecycle (queued -> analyzing_problem -> completed/failed) proven end-to-end, containerized as a 5-service Docker Compose stack**

## Performance

- **Duration:** ~42 min
- **Started:** 2026-09-22T18:38:00Z
- **Completed:** 2026-09-22T19:19:36Z
- **Tasks:** 2 completed
- **Files modified:** 38 (32 created in Task 1, 6 created/modified in Task 2)

## Accomplishments
- Scaffolded the single `uv`-managed `algorunner` package (Python 3.14) with the modular layout INFRA-01 requires: `schemas/`, `storage/`, `worker/`, `api/`, `agents/`, `tools/` — re-confirmed the Python 3.14 + LangGraph dependency resolution RESEARCH.md flagged as the phase's dominant risk (`uv add langgraph ...` resolved and imported cleanly)
- Full Pydantic contract locked per D-01/D-02/D-03/D-07/D-08/D-10: `TaskSubmission`, 12-value `TaskStatus` enum, structured `TaskError`, `TaskRecord`, `TaskCreateResponse`
- Postgres storage layer: shared `AsyncConnectionPool` (`autocommit=True`, `row_factory=dict_row`), parameterized CRUD (`insert_task`, `get_task`, `update_task_status`, `update_task_completed`, `update_task_failed`), numbered-SQL migration runner with `schema_migrations` tracking, plus an advisory-lock-gated variant for concurrent container startup
- `RedisStreamBroker` with explicit `unacknowledged_lock_timeout` and a `solve_problem_stub` placeholder task exercising both the happy path (2-5s simulated sleep -> completed) and the `FAIL_TEST` marker path (-> failed with `{code, message}`)
- `POST /api/v1/tasks` (202 + queued, insert-then-commit-then-enqueue ordering) and `GET /api/v1/tasks/{id}` (thin Postgres read, 404 on unknown id) wired against the live database and queue
- Full 5-service `docker-compose.yml` (postgres, redis, garage, api, worker) with `Dockerfile.api`/`Dockerfile.worker`; a real containerized POST -> queue -> worker -> GET round trip reaches `status: completed`, and re-running `docker compose up -d --build` does not re-apply migrations

## Task Commits

Each task was committed atomically:

1. **Task 1: Task lifecycle core** - `9c9cefb` (feat)
2. **Task 2: Docker Compose full stack** - `6753853` (feat)

**Plan metadata:** committed alongside this SUMMARY (see final commit)

## Files Created/Modified
- `pyproject.toml`, `uv.lock` - uv-managed dependency set (langgraph, taskiq, fastapi, psycopg, pydantic, dev test deps)
- `src/algorunner/schemas/task.py` - Pydantic contract for the task lifecycle
- `src/algorunner/storage/postgres.py` - shared AsyncConnectionPool factory
- `src/algorunner/storage/tasks.py` - parameterized task-table CRUD
- `src/algorunner/storage/migrate.py` - migration runner + advisory-lock wrapper
- `migrations/0001_create_tasks_table.sql` - tasks table DDL
- `src/algorunner/worker/broker.py` - RedisStreamBroker + WORKER_STARTUP migration hook
- `src/algorunner/worker/tasks.py` - solve_problem_stub placeholder pipeline
- `src/algorunner/api/main.py` - FastAPI app, lifespan (pool open, migrations, broker startup/shutdown)
- `src/algorunner/api/routes/tasks.py` - POST/GET task routes
- `src/algorunner/api/dependencies.py` - get_pg_pool dependency
- `docker-compose.yml` - 5-service stack
- `docker/Dockerfile.api`, `docker/Dockerfile.worker` - container images
- `docker/garage/garage.toml` - Garage single-node config (see Deviations)
- `tests/conftest.py`, `tests/api/test_tasks.py`, `tests/worker/test_tasks.py` - automated round-trip tests

## Decisions Made
- Garage v2.4.1 needs an explicit config file even with `--single-node`; added `docker/garage/garage.toml` (bind-mounted read-only) since RESEARCH.md/PATTERNS.md's compose skeleton omitted one and the container exited immediately without it
- psycopg3 requires `Jsonb(...)` wrapping for Python dict/list values bound to JSONB columns; added this in `storage/tasks.py` since the plan's/RESEARCH.md's insert example passed raw lists/dicts, which psycopg3 cannot adapt on its own
- `pytest-asyncio` needed explicit `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope = "session"` in `pyproject.toml` — without it, the session-scoped Postgres pool fixture was opened on one event loop and later awaited from a different per-test loop, which hangs (not an exception) under `asyncio_mode = "auto"`'s default per-test loop

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Garage v2.4.1 requires a config file even with `--single-node`**
- **Found during:** Task 1 (bringing up `docker compose up -d postgres redis garage`)
- **Issue:** `garage server --single-node` alone exits immediately with `Failed to read config file /etc/garage.toml: No such file or directory` — the plan's docker-compose skeleton had no config file
- **Fix:** Added `docker/garage/garage.toml` (metadata_dir, data_dir, replication_factor=1, rpc_bind_addr/rpc_public_addr/rpc_secret, `[s3_api]`, `[admin]`) and bind-mounted it read-only plus two named volumes for garage data/meta persistence
- **Files modified:** `docker/garage/garage.toml`, `docker-compose.yml`
- **Verification:** `docker compose logs garage` shows the S3/Admin API servers listening with no crash loop
- **Committed in:** `9c9cefb` (Task 1 commit)

**2. [Rule 1 - Bug] psycopg3 cannot adapt raw Python dict/list to JSONB without `Jsonb(...)`**
- **Found during:** Task 1 (writing `storage/tasks.py`)
- **Issue:** RESEARCH.md's/PATTERNS.md's insert example passes `[e.model_dump() for e in body.examples]` directly as a bound parameter; psycopg3 has no default adapter for `list`/`dict` to `jsonb` and raises a type-adaptation error at execute time
- **Fix:** Wrapped every dict/list value bound to a JSONB column (`examples`, `result`, `error`) with `psycopg.types.json.Jsonb(...)`
- **Files modified:** `src/algorunner/storage/tasks.py`
- **Verification:** `tests/api/test_tasks.py` and `tests/worker/test_tasks.py` pass, exercising real INSERT/UPDATE against live Postgres
- **Committed in:** `9c9cefb` (Task 1 commit)

**3. [Rule 1 - Bug] `MIGRATIONS_DIR` path arithmetic off by one directory level**
- **Found during:** Task 1 (writing `storage/migrate.py`)
- **Issue:** The plan's text specifies `Path(__file__).parents[2] / "migrations"`, which resolves to `src/migrations` (does not exist) rather than the repo-root `migrations/` directory, since `migrate.py` lives three levels below the repo root (`storage/` -> `algorunner/` -> `src/` -> repo root)
- **Fix:** Used `Path(__file__).resolve().parents[3] / "migrations"`
- **Files modified:** `src/algorunner/storage/migrate.py`
- **Verification:** `uv run python -m algorunner.storage.migrate` finds and applies `migrations/0001_create_tasks_table.sql`
- **Committed in:** `9c9cefb` (Task 1 commit)

**4. [Rule 1 - Bug] `AsyncConnectionPool` has no `.opened` attribute**
- **Found during:** Task 1 (running the migration CLI for the first time)
- **Issue:** Both `storage/migrate.py` and `worker/tasks.py` guarded pool opening with `if not pool.opened:`, but `psycopg_pool.AsyncConnectionPool` only exposes `.closed`, raising `AttributeError`
- **Fix:** Removed the guard; `pool.open()` is documented as safe to call repeatedly on an already-open pool, so all call sites now call it unconditionally
- **Files modified:** `src/algorunner/storage/migrate.py`, `src/algorunner/worker/tasks.py`
- **Verification:** Migration CLI and worker tests run without error
- **Committed in:** `9c9cefb` (Task 1 commit)

**5. [Rule 3 - Blocking] `pytest-asyncio` session-scoped async fixture hung across per-test event loops**
- **Found during:** Task 1 (first full test-suite run — tests never completed, no error, no output)
- **Issue:** `asyncio_mode = "auto"` alone gives each test function its own event loop by default; the session-scoped `pg_pool` fixture was opened on the first test's loop and then awaited from a different loop in later tests, which hangs indefinitely (psycopg_pool's internal background worker never runs on the new loop) rather than raising a "different loop" error
- **Fix:** Added `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` to `[tool.pytest.ini_options]` in `pyproject.toml`
- **Files modified:** `pyproject.toml`
- **Verification:** Full test suite now passes in ~0.1s instead of hanging
- **Committed in:** `9c9cefb` (Task 1 commit)

---

**Total deviations:** 5 auto-fixed (1 missing-config blocking issue, 3 bugs, 1 test-infrastructure blocking issue)
**Impact on plan:** All auto-fixes were necessary for the described behavior to actually run; none changed the plan's architecture or scope.

## Issues Encountered
- The local dev machine had a Homebrew-managed PostgreSQL 15 service bound to `127.0.0.1:5432`/`[::1]:5432`, which silently intercepted host-side connections intended for the Docker Compose Postgres (`role "algorunner" does not exist`, since it hit the wrong cluster). This is a local-environment port conflict, not a code or config bug in this project — resolved for this session by stopping the local Homebrew service (`brew services stop postgresql@15`) before running host-side tests/migrations; not a repository change.
- `uv`'s editable-install `.pth` file for the local `algorunner` package intermittently gained the macOS `UF_HIDDEN` filesystem flag (a known macOS quirk where files created via a dot-prefixed temp name and renamed keep the hidden bit, which CPython's `site.addpackage` explicitly skips), causing `ModuleNotFoundError: No module named 'algorunner'` on some `uv run` invocations. Worked around locally via `PYTHONPATH=src` for host-side `uv run` invocations during this session; not a repository change, and does not affect the containerized `Dockerfile.api`/`Dockerfile.worker` builds (which use `uv sync --frozen` without relying on a pre-existing editable install for the host's `.venv`).

## User Setup Required

None - no external service configuration required. (Note: if running tests/migrations against `localhost:5432` on a machine with another local Postgres service already bound to that port, stop the conflicting service first.)

## Next Phase Readiness
- Plan 01-02 (LangGraph wiring, D-12/D-13 smoke test, validation hardening) can proceed directly: `storage/tasks.py`'s CRUD helpers, `storage/postgres.py`'s pool, and `worker/tasks.py`'s `FAIL_TEST_MARKER`/`solve_problem_stub` are all in place exactly as Plan 01-02's `<interfaces>` section expects
- No blockers carried forward

---
*Phase: 01-foundation-task-lifecycle-skeleton*
*Completed: 2026-09-22*

## Self-Check: PASSED

All key files created in this plan verified present on disk; both task commits (`9c9cefb`, `6753853`) verified present in git history.
