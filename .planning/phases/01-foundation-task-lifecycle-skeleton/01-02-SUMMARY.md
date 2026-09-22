---
phase: 01-foundation-task-lifecycle-skeleton
plan: 02
subsystem: infra
tags: [langgraph, langgraph-checkpoint-postgres, asyncpostgressaver, fastapi, taskiq, pydantic, asvs]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Postgres AsyncConnectionPool, task CRUD helpers, taskiq RedisStreamBroker, FastAPI routes, FAIL_TEST_MARKER/solve_problem_stub placeholder"
provides:
  - "StubGraphState TypedDict + build_stub_graph(checkpointer) — a compiled, Postgres-checkpointed single-node LangGraph StateGraph (D-12)"
  - "solve_problem_stub refactored to invoke graph.ainvoke(..., config={'configurable': {'thread_id': task_id}}), branching on result_state error/result"
  - "D-03 validation limits (problem_text max_length, examples max_length, language enum) proven under automated tests"
  - "GET /api/v1/tasks/{id} 404 on unknown id, proven under automated test"
  - "Content-Length limiting middleware (413 above 100,000 bytes) mitigating T-01-03"
  - "Final full-stack verification: containerized POST -> queue -> worker -> GET round trip reaches completed, with real checkpoint rows in Postgres"
affects: [phase-02-solver-pipeline]

# Actuals (#2632)
actuals:
  tokens: 2865
  tasks: 3
  commits: 3
plan_head_before: 4306f07355bc0cd6ee49cbecf89fb0a0717a8070

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "1:1 thread_id <-> task_id mapping for LangGraph checkpoint resumability (AsyncPostgresSaver keyed by str(task_id))"
    - "Deferred (function-local) import to break a module-level circular import between worker.tasks and graph.build"
    - "ASGI middleware reading Content-Length before FastAPI/Pydantic body-parsing runs, for a cheap pre-parse DoS mitigation"

key-files:
  created:
    - src/algorunner/graph/__init__.py
    - src/algorunner/graph/state.py
    - src/algorunner/graph/build.py
    - tests/graph/__init__.py
    - tests/graph/test_build.py
  modified:
    - src/algorunner/worker/tasks.py
    - src/algorunner/api/main.py
    - tests/api/test_tasks.py

key-decisions:
  - "graph/build.py imports FAIL_TEST_MARKER from worker/tasks.py at module level (single source of truth per the plan); to avoid the resulting worker.tasks <-> graph.build circular import, worker/tasks.py's import of build_stub_graph was made a function-local (deferred) import inside solve_problem_stub instead of a module-level import"
  - "worker/tasks.py keeps `import asyncio` even though it no longer calls asyncio.sleep directly (D-06's sleep moved into graph/build.py's stub_node) — Plan 01-01's tests/worker/test_tasks.py monkeypatches worker_tasks.asyncio.sleep, and since asyncio is a single shared module object in sys.modules, patching it via either import path still no-ops the sleep call now living in graph/build.py, keeping that test file unmodified as the plan required"
  - "gsd-tools' tdd-red-evidence checker parses Node.js TAP output (# tests/# pass/# fail, ok/not ok lines) and has no pytest adapter in this repo; RED-phase discipline was still followed and manually verified (pytest -v showing the exact named target tests FAILED on AssertionError, not a collection/import error) but the automated `gsd_run check tdd-red-evidence` invocation was not run against this Python/pytest test suite"

requirements-completed: [ORCH-02, INFRA-01, INFRA-02]

coverage:
  - id: D1
    description: "solve_problem_stub invokes a compiled, Postgres-checkpointed LangGraph StateGraph keyed by thread_id=task_id (D-12); Python 3.14 + LangGraph compatibility re-confirmed by this plan's own real-Postgres test run"
    requirement: "ORCH-02"
    verification:
      - kind: unit
        ref: "tests/graph/test_build.py#test_build_stub_graph_happy_path_sets_result"
        status: pass
      - kind: unit
        ref: "tests/graph/test_build.py#test_build_stub_graph_fail_test_marker_sets_error"
        status: pass
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_stub_graph_persists_checkpoint_row_to_real_postgres"
        status: pass
      - kind: unit
        ref: "tests/worker/test_tasks.py (both tests, unmodified from Plan 01-01, now exercising the refactored solve_problem_stub)"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-03 validation limits (problem_text max_length=5000, examples max_length=10, language enum) reject with 422 before reaching the worker/queue"
    requirement: "INFRA-01"
    verification:
      - kind: unit
        ref: "tests/api/test_tasks.py#test_create_task_rejects_oversized_problem_text"
        status: pass
      - kind: unit
        ref: "tests/api/test_tasks.py#test_create_task_rejects_too_many_examples"
        status: pass
      - kind: unit
        ref: "tests/api/test_tasks.py#test_create_task_rejects_invalid_language"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/v1/tasks/{id} for a nonexistent id returns 404"
    requirement: "INFRA-01"
    verification:
      - kind: unit
        ref: "tests/api/test_tasks.py#test_get_task_unknown_id_returns_404"
        status: pass
    human_judgment: false
  - id: D4
    description: "A request whose Content-Length exceeds 100,000 bytes is rejected with 413 before Pydantic body-parsing runs (T-01-03 mitigation)"
    requirement: "INFRA-01"
    verification:
      - kind: unit
        ref: "tests/api/test_tasks.py#test_create_task_rejects_oversized_body_with_413"
        status: pass
    human_judgment: false
  - id: D5
    description: "The full 5-service docker compose stack, running the LangGraph-wired worker, completes a real POST -> queue -> worker -> GET round trip end-to-end, with a real checkpoint row in Postgres"
    requirement: "INFRA-02"
    verification:
      - kind: e2e
        ref: "docker compose up -d --build (rebuilt api+worker images); curl POST -> poll GET reached status=completed; psql SELECT count(*) FROM checkpoints WHERE thread_id=<task_id> returned 3"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-09-22
status: complete
---

# Phase 1 Plan 2: LangGraph Wiring & Validation Hardening Summary

**Worker now invokes a compiled, `AsyncPostgresSaver`-checkpointed single-node LangGraph `StateGraph` keyed by `thread_id=task_id`, with D-03 validation limits, 404 handling, and a Content-Length DoS mitigation all proven under automated tests**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-09-22T19:14:00Z
- **Completed:** 2026-09-22T19:36:23Z
- **Tasks:** 3 completed
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments
- `graph/state.py` (`StubGraphState` TypedDict) + `graph/build.py` (`stub_node`, `build_stub_graph`) — a compiled `StateGraph` (`START -> stub -> END`) checkpointed via `AsyncPostgresSaver(pool)`, re-confirming Python 3.14 + LangGraph compatibility against real, running Postgres (not `InMemorySaver`) — closes out D-12/D-13
- `worker/tasks.py`'s `solve_problem_stub` refactored to construct the checkpointer, build the graph, and `await graph.ainvoke(..., config={"configurable": {"thread_id": task_id}})`, branching on `result_state`'s `error`/`result` to call `update_task_failed`/`update_task_completed` — external behavior (status transitions, structured error shape) unchanged, proven by Plan 01-01's own worker tests passing unmodified
- 5 new API tests proving D-03's validation limits (`problem_text` max 5000 chars, `examples` max 10 items, `language` enum), the unknown-task-id 404 path, and a new Content-Length limiting middleware (413 above 100,000 bytes) mitigating threat T-01-03 (ASVS L1 medium-severity DoS on the client -> API trust boundary)
- Full regression (`tests/graph/test_build.py` + `tests/worker/test_tasks.py` + `tests/api/test_tasks.py`, 12 tests) passes; final `docker compose up -d --build` verification exercised a real containerized POST -> queue -> worker -> GET round trip reaching `status: completed`, with 3 checkpoint rows persisted in Postgres for that task's `thread_id` — ROADMAP Phase 1 Success Criteria 1-4 all hold

## Task Commits

Each task was committed atomically (Task 1 followed RED -> GREEN TDD discipline; Task 3 is verification-only, no commit):

1. **Task 1 (RED): failing tests for stub graph result/error behavior** - `014e913` (test)
2. **Task 1 (GREEN): wire worker through compiled LangGraph StateGraph** - `8c9f7ec` (feat)
3. **Task 2: validation and error-state hardening** - `bb45162` (feat)
4. **Task 3: final full-stack verification** - no commit (verification-only task, no files created/modified)

**Plan metadata:** committed alongside this SUMMARY (see final commit)

## Files Created/Modified
- `src/algorunner/graph/__init__.py` - graph package marker
- `src/algorunner/graph/state.py` - `StubGraphState` TypedDict (task_id, problem_text, result, error)
- `src/algorunner/graph/build.py` - `stub_node` (D-06 sleep + D-04/D-05 FAIL_TEST_MARKER branching) and `build_stub_graph(checkpointer)`
- `src/algorunner/worker/tasks.py` - `solve_problem_stub` refactored to invoke `graph.ainvoke()` against `AsyncPostgresSaver`
- `src/algorunner/api/main.py` - `MAX_BODY_BYTES = 100_000` + `limit_body_size` Content-Length middleware
- `tests/graph/__init__.py`, `tests/graph/test_build.py` - real-Postgres checkpoint round-trip tests (happy path, FAIL_TEST path, checkpoint-row persistence)
- `tests/api/test_tasks.py` - 5 new validation/404/413 tests

## Decisions Made
- Broke a `worker.tasks` <-> `graph.build` circular import (the plan requires `graph/build.py` to import `FAIL_TEST_MARKER` from `worker/tasks.py` as the single source of truth) by making `worker/tasks.py`'s import of `build_stub_graph` a function-local (deferred) import inside `solve_problem_stub`, rather than a module-level import
- Kept `import asyncio` in `worker/tasks.py` even though the sleep call itself moved to `graph/build.py`, so Plan 01-01's existing test monkeypatch (`monkeypatch.setattr(worker_tasks.asyncio, "sleep", ...)`) continues to work unmodified — `asyncio` is a single shared module object, so patching `sleep` via either import path affects the same underlying call
- `gsd-tools check tdd-red-evidence` is TAP-format-specific (Node.js `# tests`/`# pass`/`# fail`/`ok`/`not ok` lines) with no pytest adapter present in this repo; RED-phase discipline (real, intentional assertion-level failure on the named target tests, not a collection/import error) was verified manually via `pytest -v` output instead of the automated checker

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Circular import between `worker.tasks` and `graph.build`**
- **Found during:** Task 1 (writing `graph/build.py`'s module-level `from algorunner.worker.tasks import FAIL_TEST_MARKER`, then refactoring `worker/tasks.py` to import `build_stub_graph`)
- **Issue:** The plan requires `graph/build.py` to import `FAIL_TEST_MARKER` from `worker/tasks.py` (single source of truth) while `worker/tasks.py` needs `build_stub_graph` from `graph/build.py` — a straightforward module-level import on both sides creates a circular import that fails regardless of which module is imported first
- **Fix:** Made `worker/tasks.py`'s import of `build_stub_graph` function-local (inside `solve_problem_stub`), keeping `graph/build.py`'s import of `FAIL_TEST_MARKER` at module level — this guarantees `worker.tasks` always finishes defining `FAIL_TEST_MARKER` before `graph.build` is ever loaded, regardless of import order
- **Files modified:** `src/algorunner/worker/tasks.py`
- **Verification:** `uv run python -c "import langgraph, langgraph.checkpoint.postgres.aio, algorunner.graph.build"` succeeds; full test suite passes
- **Committed in:** `8c9f7ec` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Existing worker test's monkeypatch target moved with the sleep call**
- **Found during:** Task 1 (refactoring `worker/tasks.py` to remove its own `asyncio.sleep` call, per D-06 moving to `graph/build.py`)
- **Issue:** `tests/worker/test_tasks.py` (unmodified, from Plan 01-01) does `monkeypatch.setattr(worker_tasks.asyncio, "sleep", ...)` — removing `import asyncio` from `worker/tasks.py` entirely would make `worker_tasks.asyncio` raise `AttributeError` before the patch is even applied
- **Fix:** Kept `import asyncio` in `worker/tasks.py` (unused directly, but exposes the attribute the test needs); since `asyncio` is the same shared module object imported in `graph/build.py`, patching `sleep` via either import path still correctly no-ops the sleep call inside `stub_node`
- **Files modified:** `src/algorunner/worker/tasks.py`
- **Verification:** `tests/worker/test_tasks.py`'s two tests pass unmodified, in well under the real 2-5s sleep window
- **Committed in:** `8c9f7ec` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 blocking circular-import issue, 1 bug from moving the sleep call)
**Impact on plan:** Both fixes were necessary for the plan's own required import direction (FAIL_TEST_MARKER single-sourced in worker/tasks.py) and for keeping Plan 01-01's test file genuinely unmodified, as the plan's acceptance criteria required. No scope creep.

## Issues Encountered
- The pre-existing local dev editable-install issue documented in Plan 01-01's SUMMARY (macOS `UF_HIDDEN` flag on `uv`'s `.pth` file causing `ModuleNotFoundError: No module named 'algorunner'`) recurred for host-side `uv run` invocations this session; worked around identically via `PYTHONPATH=src uv run ...`. Not a repository change, and does not affect the containerized `Dockerfile.api`/`Dockerfile.worker` builds used for the final verification task.
- `gsd-tools check tdd-red-evidence`'s TAP-format parser has no pytest adapter in this repo (see Decisions Made) — RED-phase evidence was verified manually instead of via the automated checker for this Python project.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 1 is fully complete: all 4 ROADMAP Phase 1 Success Criteria hold against the real deployed stack (verified via `docker compose up -d --build` + curl POST/GET polling + `psql` checkpoint-row count)
- D-12 and D-13 are both resolved: the LangGraph stub graph is wired and checkpointed to real Postgres, and Python 3.14 compatibility is confirmed by this plan's own test run — the D-13 3.13 fallback was never triggered
- ORCH-02, INFRA-01, INFRA-02 fully satisfied; no ASVS L1 medium-or-above threat left unmitigated (T-01-03 mitigated this plan; T-01-04 addressed by reusing the shared pool; T-01-05 accepted as low-severity per the plan's threat register)
- Ready for `/gsd-verify-work` and Phase 2 planning (Verified Single-Solution Pipeline)
- No blockers carried forward

---
*Phase: 01-foundation-task-lifecycle-skeleton*
*Completed: 2026-09-22*

## TDD Gate Compliance

Task 1 (`tdd="true"`) followed RED -> GREEN discipline:
- RED commit `014e913` (`test(01-02): ...`) precedes GREEN commit `8c9f7ec` (`feat(01-02): ...`) — both present in git log
- RED was verified as a genuine, intentional assertion-level failure: `pytest -v` showed `test_build_stub_graph_happy_path_sets_result` and `test_build_stub_graph_fail_test_marker_sets_error` FAILED with `AssertionError: assert None is not None` (not a collection/import error) before `stub_node`'s real logic was implemented
- No REFACTOR commit — the GREEN implementation was already minimal and clean, no further cleanup identified
- The automated `gsd_run check tdd-red-evidence` verdict tool was not invoked against this run (see Decisions Made: it is TAP-format-specific with no pytest adapter in this repo); RED evidence was instead verified manually via direct `pytest -v` inspection of the target tests' failure mode

## Self-Check: PASSED

All key files created in this plan verified present on disk (`src/algorunner/graph/state.py`, `src/algorunner/graph/build.py`, `tests/graph/test_build.py`); all three task commits (`014e913`, `8c9f7ec`, `bb45162`) verified present in `git log`; full regression suite (12 tests across `tests/graph/`, `tests/worker/`, `tests/api/`) passes; final containerized end-to-end round trip reached `status: completed` with 3 real checkpoint rows in Postgres.
