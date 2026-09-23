---
phase: 02-verified-single-solution-core-pipeline
plan: 02
subsystem: agents
tags: [langgraph, openai, structured-outputs, taskiq, postgres, fastapi]

# Dependency graph
requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Plan 02-01's llm/ package (get_client, model_for, call_structured), Phase 2 Pydantic schemas (ProblemAnalysis, Approach, Solution, ReviewResult, ExecutionResult), Settings extended with OpenAI config"
provides:
  - "problem_analyzer_node(state) -> dict — first genuine OpenAI-backed LangGraph node (real chat.completions.parse() call, not a stub)"
  - "GraphState TypedDict — full 16-field Phase 2 shape (replaces StubGraphState); no later plan needs to touch this file again"
  - "build_pipeline_graph(checkpointer) — replaces the Phase-1 stub graph, wires analyzer -> finalize_success"
  - "solve_problem worker task (renamed from solve_problem_stub) with CR-01/CR-02/CR-03 hardening and durability=\"sync\""
  - "mock_openai_parse test fixture in tests/conftest.py — reused by every subsequent Phase 2 agent-node unit test"
  - "get_pool() memoized singleton (WR-01) and api/main.py's streamed-byte-count body-size limiting (CR-04)"
affects: ["02-03 (Strategist node)", "every subsequent Phase 2 agent node built onto the same graph/worker/broker/API surface"]

# Actuals (#2632)
actuals:
  tokens: 9768
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Checkpointer-as-process-singleton via taskiq's broker.state (TaskiqState), constructed and .setup()-called exactly once at WORKER_STARTUP, instead of per-task construction"
    - "Streamed request-body size limiting with in-place request._body replay (Starlette BaseHTTPMiddleware's _CachedRequest.wrapped_receive() mechanism) instead of a Content-Length-only check"
    - "lru_cache-memoized shared AsyncConnectionPool across every caller in a process (worker startup, worker tasks, api lifespan)"
    - "Module-qualified LLM client access (client_factory.get_client(), not `from ... import get_client`) so tests/conftest.py's mock_openai_parse fixture can monkeypatch the source module's attribute regardless of import order"

key-files:
  created:
    - src/algorunner/agents/problem_analyzer/__init__.py
    - src/algorunner/agents/problem_analyzer/node.py
    - src/algorunner/agents/problem_analyzer/prompts.py
    - tests/agents/__init__.py
    - tests/agents/test_problem_analyzer.py
    - tests/storage/__init__.py
    - tests/storage/test_postgres.py
  modified:
    - src/algorunner/graph/state.py
    - src/algorunner/graph/build.py
    - src/algorunner/worker/tasks.py
    - src/algorunner/worker/broker.py
    - src/algorunner/storage/postgres.py
    - src/algorunner/api/main.py
    - src/algorunner/api/routes/tasks.py
    - docker-compose.yml
    - tests/conftest.py
    - tests/graph/test_build.py
    - tests/worker/test_tasks.py
    - tests/api/test_tasks.py

key-decisions:
  - "worker/tasks.py reuses broker.state.checkpointer (the plan's 'clean' CR-03 path) rather than the module-level-fallback escape hatch it also offered — this keeps the single literal checkpointer.setup() call site in broker.py only, satisfying the acceptance criterion's grep -c \"checkpointer.setup\" src/algorunner/worker/tasks.py == 0 literally; a new autouse fixture in tests/worker/test_tasks.py mimics WORKER_STARTUP's one-time setup for tests that call solve_problem directly without taskiq's real worker lifecycle"
  - "docker-compose.yml's OPENAI_API_KEY fail-fast wiring (${OPENAI_API_KEY:?...}) extended to the api service, not just worker as the plan's action literally specified — Settings() has required openai_api_key unconditionally since Plan 02-01 with no docker-compose wiring at all, so the api container would otherwise crash on startup and block the plan's own human-check"
  - "CR-04's body-size fix caches the consumed bytes onto request._body (mirroring what Starlette's Request.body() does internally) rather than monkeypatching request._receive — read the installed Starlette source (middleware/base.py's _CachedRequest.wrapped_receive) to confirm it already replays request._body downstream to FastAPI's route handler when set, so no custom receive-replay plumbing was needed"

requirements-completed: [INTAKE-02, INTAKE-03, ORCH-04]

coverage:
  - id: D1
    description: "Real Analyzer node end-to-end: genuine OpenAI structured-output call (call_structured), real GraphState/build_pipeline_graph (not the Phase-1 stub), real Postgres checkpoint via durability=\"sync\", invoked by the worker's solve_problem task"
    requirement: INTAKE-02
    verification:
      - kind: unit
        ref: "tests/agents/test_problem_analyzer.py#test_problem_analyzer_node_returns_parsed_analysis"
        status: pass
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_pipeline_graph_happy_path_sets_analysis_result"
        status: pass
      - kind: integration
        ref: "tests/worker/test_tasks.py#test_solve_problem_happy_path_completes"
        status: pass
    human_judgment: true
    rationale: "Live end-to-end content correctness (real, problem-specific ProblemAnalysis text, not placeholder) requires human judgment beyond mocked unit tests. Already confirmed via this plan's tracer feedback gate checkpoint — coordinator reported: 'real, problem-specific analysis returned (intent/difficulty/constraints all meaningful, not placeholder)'."
  - id: D2
    description: "Analyzer treats empty/whitespace/trivially-short problem_text as needing clarification (needs_clarification=True) rather than guessing an analysis (INTAKE-04 prompt-level behavior)"
    requirement: INTAKE-03
    verification: []
    human_judgment: true
    rationale: "This is model-inference behavior instructed via prompts.py's system prompt; a mocked unit test always returns the same canned analysis regardless of input, so it cannot exercise the model's actual clarification judgment for edge-case inputs. Not independently verified against a real OpenAI call beyond the single happy-path human-check."
  - id: D3
    description: "problem_text flows through the pipeline as a UTF-8-decoded Python str with no byte-slicing/truncation that could split multi-byte Cyrillic characters (backstop must-have)"
    verification: []
    human_judgment: true
    rationale: "Structural backstop claim — no byte-slicing/truncation code exists anywhere in the touched files (problem_text is passed as a plain Python str end-to-end: task row -> worker/tasks.py -> GraphState -> prompts.py's f-string), but not independently exercised by a dedicated multi-byte-character test this plan."
  - id: D4
    description: "CR-01: an unhandled exception anywhere in solve_problem is caught and written to the task row as a structured TaskError, never leaving the task stuck at a non-terminal status forever"
    verification:
      - kind: integration
        ref: "tests/worker/test_tasks.py#test_solve_problem_unhandled_exception_writes_structured_error_and_reraises"
        status: pass
    human_judgment: false
  - id: D5
    description: "CR-02: a solve_problem invocation for a task_id with no matching Postgres row logs an error and returns without fabricating a false completed result"
    verification:
      - kind: integration
        ref: "tests/worker/test_tasks.py#test_solve_problem_missing_task_row_logs_and_returns_without_writing_result"
        status: pass
    human_judgment: false
  - id: D6
    description: "CR-03: AsyncPostgresSaver.setup() runs exactly once per worker process (WORKER_STARTUP), not on every task invocation"
    requirement: ORCH-04
    verification:
      - kind: other
        ref: "grep -c checkpointer.setup src/algorunner/worker/tasks.py returns 0; grep -n checkpointer.setup src/algorunner/worker/broker.py shows the sole setup() call site"
        status: pass
    human_judgment: false
  - id: D7
    description: "CR-04: a request whose actual streamed body exceeds MAX_BODY_BYTES is rejected with 413 even when Content-Length is absent/chunked"
    verification:
      - kind: integration
        ref: "tests/api/test_tasks.py#test_create_task_rejects_oversized_streamed_body_without_content_length"
        status: pass
      - kind: integration
        ref: "tests/api/test_tasks.py#test_create_task_accepts_streamed_body_within_limit"
        status: pass
      - kind: integration
        ref: "tests/api/test_tasks.py#test_create_task_rejects_oversized_body_with_413"
        status: pass
    human_judgment: false
  - id: D8
    description: "WR-01: get_pool() returns the identical AsyncConnectionPool instance on every call within a process"
    verification:
      - kind: unit
        ref: "tests/storage/test_postgres.py#test_get_pool_returns_same_instance_on_second_call"
        status: pass
    human_judgment: false

duration: ~50min active execution (spans a mid-plan checkpoint pause for human verification; see Tracer Feedback Gate below)
completed: 2026-09-23
status: complete
---

# Phase 2 Plan 2: Analyzer Tracer + Phase-1 Reliability Hardening Summary

**Real OpenAI-backed Problem Analyzer node wired into a real (non-stub) Postgres-checkpointed LangGraph pipeline, plus the last three Phase-1-code-review findings (CR-03, CR-04, WR-01) closed out before Plan 02-03 adds more agent nodes onto the same worker/broker/API surface.**

## Performance

- **Duration:** ~50 min active execution (wall-clock span was longer — includes a mid-plan pause for the tracer feedback gate's human verification checkpoint)
- **Started:** 2026-09-23T11:50:07Z (first commit)
- **Completed:** 2026-09-23T15:13:23Z (last commit)
- **Tasks:** 2
- **Files modified:** 19 (7 created, 12 modified)

## Accomplishments

- Problem Analyzer node (`problem_analyzer_node`) — the first genuine OpenAI-backed LangGraph node, calling `call_structured()` (Plan 02-01's tested retry wrapper) directly, with `problem_text` explicitly delimited as untrusted DATA in the prompt (T-02-02-01 prompt-injection mitigation)
- `GraphState` — full 16-field Phase 2 TypedDict shape, replacing `StubGraphState`; later plans populate the remaining fields without touching this file again
- `build_pipeline_graph(checkpointer)` — replaces the Phase-1 stub graph (`analyzer -> finalize_success`), retiring the `FAIL_TEST_MARKER` smoke-test hook
- `solve_problem` worker task (renamed from `solve_problem_stub`) — CR-01 (structured `TaskError` on any unhandled exception, never left stuck non-terminal) and CR-02 (missing task row logs and returns, never fabricates a false completed result) baked directly into the rewrite; `durability="sync"` on the `ainvoke()` call so a worker crash can't lose a just-completed checkpoint write
- Live, real-OpenAI-key verification (tracer feedback gate, coordinator-approved): a real problem reaches `completed` with genuine, problem-specific `ProblemAnalysis` content
- CR-03: `AsyncPostgresSaver.setup()` now runs exactly once per worker process at `WORKER_STARTUP`, stored on `broker.state.checkpointer` and reused by every `solve_problem` invocation — eliminates the concurrent-first-call `UniqueViolation` race on `checkpoint_migrations`
- CR-04: `api/main.py`'s body-size middleware now counts actual streamed bytes (`request.stream()`), rejecting with 413 the instant the running total exceeds `MAX_BODY_BYTES`, independent of whether `Content-Length` was present/trustworthy — no longer bypassable by a chunked or missing-header request
- WR-01: `storage/postgres.py`'s `get_pool()` is now `functools.lru_cache`-memoized, so the worker process (broker startup + task execution) and the api process each share one `AsyncConnectionPool` instead of holding independent, duplicate pools

## Task Commits

Task 1 (`type="tracer"`, single commit — production-quality, not throwaway):

1. **Task 1: Analyzer end-to-end** - `11159d7` (feat) - real OpenAI call, real graph, real checkpoint; CR-01/CR-02 baked in; docker-compose OPENAI_API_KEY wiring; `mock_openai_parse` fixture

Task 2 (`type="auto" tdd="true"`, RED -> GREEN, no REFACTOR needed — implementation was already minimal):

2. **Task 2 RED:** `c6dbc21` (test) - failing tests for `get_pool()` memoization (WR-01) and streamed-body size limit (CR-04)
3. **Task 2 GREEN:** `92cd0b7` (feat) - `get_pool()` memoization, `broker.py` WORKER_STARTUP checkpointer setup (CR-03), `worker/tasks.py` reuse, `api/main.py` streamed-byte-count body limit (CR-04)

**Plan metadata:** committed alongside this SUMMARY.

## TDD Gate Compliance

Task 2 only (`tdd="true"`); Task 1 is `type="tracer"`, not TDD.

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| Task 2 (CR-03/CR-04/WR-01) | `c6dbc21` | `92cd0b7` | — (not needed) | Pass |

RED-phase evidence: both target tests failed on the planned assertion (`AssertionError` on pool identity for WR-01; `assert 422 == 413` for CR-04 — the oversized streamed body fell through to downstream Pydantic validation instead of being rejected by the size middleware), confirmed via `pytest -v` output — `gsd_run check tdd-red-evidence` was not used (no pytest adapter, precedent from Phase 02-01, carried forward).

## Files Created/Modified

- `src/algorunner/agents/problem_analyzer/node.py` - `problem_analyzer_node(state) -> dict`
- `src/algorunner/agents/problem_analyzer/prompts.py` - `build_analysis_messages(state)`, prompt-injection-mitigated message construction
- `src/algorunner/graph/state.py` - full `GraphState` TypedDict (16 fields)
- `src/algorunner/graph/build.py` - `build_pipeline_graph(checkpointer)`, `finalize_success` node
- `src/algorunner/worker/tasks.py` - `solve_problem` (renamed, CR-01/CR-02/CR-03 hardened, `durability="sync"`)
- `src/algorunner/worker/broker.py` - `_on_worker_startup` now constructs/sets up the checkpointer once (CR-03)
- `src/algorunner/storage/postgres.py` - `get_pool()` memoized with `@lru_cache` (WR-01)
- `src/algorunner/api/main.py` - `limit_body_size` middleware counts streamed bytes, replays consumed body (CR-04)
- `src/algorunner/api/routes/tasks.py` - imports/enqueues `solve_problem` (renamed)
- `docker-compose.yml` - `OPENAI_API_KEY` required on both `worker` and `api` services
- `tests/conftest.py` - `mock_openai_parse` fixture
- `tests/agents/test_problem_analyzer.py` - Analyzer node unit tests
- `tests/storage/test_postgres.py` - `get_pool()` memoization test
- `tests/graph/test_build.py`, `tests/worker/test_tasks.py`, `tests/api/test_tasks.py` - updated/extended for the real pipeline and CR-03/CR-04 behavior

## Decisions Made

See `key-decisions` in frontmatter — summarized: (1) `broker.state.checkpointer` reuse over the module-level fallback for CR-03, with a test fixture bridging the gap for direct-call tests; (2) `OPENAI_API_KEY` wiring extended to the `api` service beyond what the plan's action literally specified; (3) CR-04's fix caches `request._body` directly (Starlette's own internal mechanism) rather than a custom receive-replay wrapper.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added OPENAI_API_KEY to docker-compose.yml's api service**
- **Found during:** Task 1
- **Issue:** `config.py`'s `Settings()` has required `openai_api_key` (no default) since Plan 02-01, but `docker-compose.yml` never wired `OPENAI_API_KEY` into any service. The plan's action only specified adding it to the `worker` service; the `api` service would still crash on startup without it, which would have blocked the plan's own human-check (POSTing to a running API container).
- **Fix:** Added the same `OPENAI_API_KEY: ${OPENAI_API_KEY:?OPENAI_API_KEY must be set}` fail-fast wiring to the `api` service's `environment:` block.
- **Files modified:** `docker-compose.yml`
- **Verification:** `docker compose config -q` validates; the live human-check (coordinator-approved) confirmed the api container started and served the request correctly.
- **Committed in:** `11159d7` (Task 1 commit)

**2. [Rule 1 - Bug] Removed literal "FAIL_TEST_MARKER" string from two docstrings**
- **Found during:** Task 1
- **Issue:** The task's own acceptance criteria requires `grep -rn "FAIL_TEST_MARKER" src/algorunner/` to return nothing, but the first draft of `graph/build.py` and `worker/tasks.py` referenced the retired constant by name in explanatory comments, failing that check.
- **Fix:** Reworded both docstrings to describe the retired mechanism without using the literal identifier.
- **Files modified:** `src/algorunner/graph/build.py`, `src/algorunner/worker/tasks.py`
- **Verification:** `grep -rn "FAIL_TEST_MARKER" src/algorunner/ tests/` returns nothing.
- **Committed in:** `11159d7` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 self-correction)
**Impact on plan:** Both were small, necessary corrections with no scope creep — the docker-compose fix was required for the plan's own verification step to succeed; the docstring wording fix was required to satisfy the plan's own literal acceptance criterion.

## Tracer Feedback Gate

Task 1 is `type="tracer"`. Per protocol, after completing and committing Task 1, the tracer feedback gate was evaluated: `workflow._auto_chain_active`/`workflow.auto_advance` were both false (not auto mode), `workflow.human_verify_mode` is `end-of-phase` (default), and Task 1's `<verify>` block carries a `<human-check>` in addition to `<automated>` — per the precedence chain this requires a `checkpoint:human-verify` before Task 2, which cannot be bypassed by re-running the automated `<verify>` alone.

This worktree had no access to a real `OPENAI_API_KEY` (git worktrees do not inherit the gitignored `.env` file from the main checkout, and the sandbox's secret-file protections prevent reading/copying it), so the live end-to-end check could not be automated from within the worktree. A checkpoint was returned to the orchestrator explaining this and providing exact manual-verification steps. The coordinator ran the check against a location with real credentials and reported: **"live end-to-end check passed: real, problem-specific analysis returned (intent/difficulty/constraints all meaningful, not placeholder)."** Execution then resumed with Task 2.

## Issues Encountered

- **Local environment quirk (not a code issue, not committed):** in this worktree's `.venv`, `uv`-created `.pth` files (`algorunner.pth`, `_virtualenv.pth`) repeatedly had the macOS `hidden` file flag (`UF_HIDDEN`) set, which makes CPython 3.14's `site.py` silently skip processing them (`_trace(f"Skipping hidden .pth file...")`), breaking `import algorunner` entirely and intermittently. Root cause confirmed by reading the installed `site.py` source and checking `ls -lO`. Worked around per test run via `chflags nohidden .venv/lib/python3.14/site-packages/*.pth` immediately before each `uv run --no-sync pytest ...` invocation. Not fixed in the codebase (nothing to fix — it's a local `.venv` artifact, not a project file), but flagged here in case a future executor in this same sandboxed environment hits the same `ModuleNotFoundError: No module named 'algorunner'` symptom.
- **Main-checkout Docker stack stopped mid-session:** the `algorunner-*` containers (postgres/redis/garage/api/worker) this worktree's tests rely on for a live Postgres/Redis (since the worktree's own `docker compose up` on the same host ports conflicts with the main checkout's already-running stack) exited unexpectedly partway through execution, for reasons outside this session's control. Restarted `algorunner-postgres-1`/`algorunner-redis-1` via `docker start` (no rebuild needed, no code involved) and continued.

## User Setup Required

None beyond what Plan 02-01 already documented — a real `OPENAI_API_KEY` is required for live pipeline execution and was already confirmed set (used successfully during this plan's tracer feedback gate verification).

## Next Phase Readiness

- The real Analyzer -> `finalize_success` graph, the full `GraphState` shape, and a hardened worker/broker/API surface are ready for Plan 02-03 to add the Strategist node onto the same `build_pipeline_graph`.
- `mock_openai_parse` (tests/conftest.py) is ready to be reused by every subsequent agent-node's unit tests without modification.
- All five Phase-1-code-review findings (CR-01 through CR-04, WR-01) are now closed and covered by tests — no outstanding reliability debt carried into Plan 02-03.

---
*Phase: 02-verified-single-solution-core-pipeline*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 7 created files confirmed present on disk. All 3 commits (`11159d7`, `c6dbc21`, `92cd0b7`) confirmed present in `git log`. Full test suite re-run: `uv run pytest tests/ -q` → 25 passed. Plan-level verification command re-run: `uv run pytest tests/graph/test_build.py tests/worker/test_tasks.py tests/agents/test_problem_analyzer.py tests/api/test_tasks.py -q` → 16 passed. `git status --short` clean at time of this SUMMARY (before staging SUMMARY.md/REQUIREMENTS.md).
