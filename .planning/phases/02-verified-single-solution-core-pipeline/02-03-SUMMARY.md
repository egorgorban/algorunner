---
phase: 02-verified-single-solution-core-pipeline
plan: 03
subsystem: agents
tags: [langgraph, openai, structured-outputs, pydantic]

# Dependency graph
requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Plan 02-02's real Analyzer node, GraphState (16-field shape), build_pipeline_graph, mock_openai_parse test fixture, and the CR-01 worker/tasks.py exception handler this plan's empty-approaches guard relies on"
provides:
  - "solution_strategist_node(state) -> dict — proposes 1+ tagged Approach objects via a new ApproachList container schema, with an explicit empty-approaches guard"
  - "solver_node(state) -> dict — elaborates the deterministically-selected approaches[0] into algorithm + complexity reasoning via a new module-local SolverOutput schema"
  - "build_pipeline_graph now runs analyzer -> strategist -> solver -> finalize_success end-to-end against real Postgres"
  - "GraphState.solver_output: dict | None"
  - "mock_pipeline_openai test fixture (tests/conftest.py) — full 3-node pipeline mock, reusable by Plan 02-04's Code Generator tests"
affects: ["02-04 (Code Generator/Test Generator — folds solver_output into a real Solution)", "02-05/02-06 (Reviewer/correction loop — reads approaches/solver_output)"]

# Actuals (#2632)
actuals:
  tokens: 6447
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Container-schema wrapper for OpenAI structured-output arrays (ApproachList wraps list[Approach]) — top-level response_format schemas must be an object, never a bare array"
    - "Module-local partial-elaboration schema (SolverOutput) for an agent whose full downstream contract (Solution) isn't yet fully producible — avoids inventing placeholder code/tests just to satisfy Solution's min_length constraints prematurely"
    - "Multi-stage AsyncMock(side_effect=[...]) for full-pipeline tests where every node shares one client_factory.get_client() call site — one canned response per node, in call order"

key-files:
  created:
    - src/algorunner/agents/solution_strategist/__init__.py
    - src/algorunner/agents/solution_strategist/node.py
    - src/algorunner/agents/solution_strategist/prompts.py
    - src/algorunner/agents/solver/__init__.py
    - src/algorunner/agents/solver/node.py
    - src/algorunner/agents/solver/prompts.py
    - tests/agents/test_strategist_solver.py
  modified:
    - src/algorunner/graph/build.py
    - src/algorunner/graph/state.py
    - src/algorunner/schemas/solution.py
    - tests/conftest.py
    - tests/graph/test_build.py
    - tests/worker/test_tasks.py

key-decisions:
  - "ApproachList carries no min_length constraint on `approaches` — the empty-list case is guarded explicitly in solution_strategist_node (STRAT-03/empty), not at the schema layer, so the same shape stays constructible in tests exercising that guard (a schema-level constraint would make an empty-list mock unconstructible)"
  - "solver_node's SolverOutput is intentionally NOT added to schemas/solution.py — it is a module-local, partial-elaboration shape scoped to this plan (Plan 02-04's Code Generator folds it into a real Solution once code_python/code_go/tests exist), not a durable inter-plan contract"
  - "Added a shared mock_pipeline_openai fixture to tests/conftest.py (rather than duplicating a local one per test file) since extending the graph broke every pre-existing test that exercised the full pipeline through the single-response mock_openai_parse fixture — this fixture is the reusable full-pipeline mock going forward"

requirements-completed: [STRAT-01, STRAT-03, STRAT-04]

coverage:
  - id: D1
    description: "Strategist proposes 1+ distinct, technique-tagged Approach objects from a real (mocked) OpenAI structured-output call"
    requirement: STRAT-01
    verification:
      - kind: unit
        ref: "tests/agents/test_strategist_solver.py#test_solution_strategist_node_returns_tagged_approaches"
        status: pass
    human_judgment: false
  - id: D2
    description: "Strategist returning zero approaches raises a structured error (ValueError, caught by worker/tasks.py's CR-01 handler) rather than proceeding to index approaches[0] and crashing with an IndexError"
    requirement: STRAT-03
    verification:
      - kind: unit
        ref: "tests/agents/test_strategist_solver.py#test_solution_strategist_node_raises_on_empty_approaches"
        status: pass
      - kind: other
        ref: "grep -n 'if not result.approaches' src/algorunner/agents/solution_strategist/node.py"
        status: pass
    human_judgment: true
    rationale: "Manually verified end-to-end (worker/tasks.py's solve_problem, not committed as a test — out of this plan's stated verify scope) that the empty-approaches ValueError results in a persisted TaskError and TaskStatus.FAILED, never a stuck non-terminal status or an unhandled crash. See Deviations for the code-value discrepancy this surfaced."
  - id: D3
    description: "Solver elaborates the deterministically-selected approaches[0] (no re-ranking) into an algorithm description + time/space complexity reasoning, without asking for or producing code_python/code_go/tests"
    requirement: STRAT-04
    verification:
      - kind: unit
        ref: "tests/agents/test_strategist_solver.py#test_solver_node_returns_algorithm_and_complexity"
        status: pass
      - kind: other
        ref: "grep -n 'code_python\\|code_go' src/algorunner/agents/solver/prompts.py returns nothing"
        status: pass
    human_judgment: false
  - id: D4
    description: "build_pipeline_graph runs analyzer -> strategist -> solver -> finalize_success end-to-end against real Postgres, with a real checkpoint row proving it"
    verification:
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_pipeline_graph_runs_analyzer_strategist_solver_end_to_end"
        status: pass
      - kind: integration
        ref: "tests/worker/test_tasks.py#test_solve_problem_happy_path_completes"
        status: pass
    human_judgment: false

duration: ~20 min
completed: 2026-09-23
status: complete
---

# Phase 2 Plan 3: Solution Strategist + Solver Nodes Summary

**Strategist proposes 1+ technique-tagged approaches via a new `ApproachList` container schema with an explicit empty-list guard, and a generic Solver elaborates the deterministically-selected `approaches[0]` into algorithm + complexity reasoning — both wired into `build_pipeline_graph`'s `analyzer -> strategist -> solver -> finalize_success` chain, verified end-to-end against real Postgres.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-23T15:19:00Z (approx, first RED commit at 15:2x)
- **Completed:** 2026-09-23T15:39:20Z
- **Tasks:** 2
- **Files modified:** 13 (7 created, 6 modified)

## Accomplishments

- `solution_strategist_node` — first real LLM call after Analyzer, proposing 1+ `Approach` objects (name/technique/summary) via a new `ApproachList` container schema (OpenAI structured-output top-level schemas must be an object, not a bare array); explicitly guards the empty-approaches case with `if not result.approaches: raise ValueError(...)`, relying on `worker/tasks.py`'s existing CR-01 handler rather than adding a second exception-handling layer
- `solver_node` — elaborates the deterministically-selected `approaches[0]` (no re-ranking/re-sorting) into an algorithm description plus justified time/space complexity, via a new module-local `SolverOutput` schema (intentionally not added to `schemas/solution.py` — it is Plan 02-03's partial-elaboration shape, not a durable inter-plan contract; Plan 02-04's Code Generator folds it into a real `Solution` once code/tests exist)
- `build_pipeline_graph` now runs `analyzer -> strategist -> solver -> finalize_success`; `finalize_success`'s persisted `result` dict gained `approaches` (dumped) and a JSON-safe `solver_output`
- `GraphState.solver_output: dict | None` — the one additive edit since Plan 02-02's "full 16-field shape, never touched again" framing, justified by the Solver/CodeGen split not being knowable until this plan's design decision
- Both new prompts (`solution_strategist/prompts.py`, `solver/prompts.py`) delimit upstream-derived content (`analysis`, the chosen `approach`) as DATA, same prompt-injection framing as `problem_analyzer/prompts.py` (T-02-03-01 mitigation)
- A new end-to-end integration test proves the full analyzer->strategist->solver run against real Postgres, checkpoint row included, driven by a mocked OpenAI client with per-node canned responses

## Task Commits

Task 1 (`tdd="true"`, RED -> GREEN, no REFACTOR needed — implementation was already minimal):

1. **Task 1 RED:** `7d3ef6c` (test) — failing tests for Strategist/Solver nodes (`ModuleNotFoundError`, neither package existed yet)
2. **Task 1 GREEN:** `94f955e` (feat) — `solution_strategist_node`/`solver_node`, `ApproachList`, `SolverOutput`, `GraphState.solver_output`

Task 2 (`type="auto"`, single commit):

3. **Task 2:** `ff1762d` (feat) — wired Strategist + Solver into `build_pipeline_graph`; fixed a JSON-serialization bug (see Deviations) surfaced by the new integration test; updated 3 pre-existing tests broken by the graph extension

**Plan metadata:** committed alongside this SUMMARY.

## TDD Gate Compliance

Task 1 only (`tdd="true"`); Task 2 is `type="auto"`, not TDD.

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| Task 1 (Strategist/Solver nodes) | `7d3ef6c` | `94f955e` | — (not needed) | Pass |

RED-phase evidence: `ModuleNotFoundError: No module named 'algorunner.agents.solution_strategist'`, confirmed via `pytest -v` output — `gsd_run check tdd-red-evidence` was not used (no pytest adapter; same precedent as Phase 01-02/02-01/02-02, carried forward).

## Files Created/Modified

- `src/algorunner/agents/solution_strategist/node.py` — `solution_strategist_node(state) -> dict`
- `src/algorunner/agents/solution_strategist/prompts.py` — `build_strategy_messages(state)`, DATA-delimited analysis
- `src/algorunner/agents/solver/node.py` — `solver_node(state) -> dict`, `SolverOutput` schema
- `src/algorunner/agents/solver/prompts.py` — `build_solver_messages(state)`, DATA-delimited approach, explicitly does not ask for code
- `src/algorunner/schemas/solution.py` — added `ApproachList` container schema
- `src/algorunner/graph/state.py` — added `solver_output: dict | None`
- `src/algorunner/graph/build.py` — wired strategist/solver nodes; `_json_safe_solver_output` helper; `finalize_success` extended
- `tests/agents/test_strategist_solver.py` — 3 unit tests (tagged approaches, empty-list guard, solver elaboration)
- `tests/conftest.py` — new `mock_pipeline_openai` fixture (full 3-node pipeline mock)
- `tests/graph/test_build.py` — 2 pre-existing tests switched to `mock_pipeline_openai`; 1 new end-to-end test added
- `tests/worker/test_tasks.py` — happy-path test switched to `mock_pipeline_openai`

## Decisions Made

See `key-decisions` in frontmatter — summarized: (1) `ApproachList` has no `min_length` constraint (guard lives in the node, not the schema, so empty-list is testable); (2) `SolverOutput` stays module-local, not promoted to `schemas/solution.py`; (3) a shared `mock_pipeline_openai` fixture replaces per-file duplication for full-pipeline tests going forward.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `finalize_success`'s persisted result contained a non-JSON-serializable Approach instance**
- **Found during:** Task 2, writing the new end-to-end integration test
- **Issue:** `finalize_success` copied `state.get("solver_output")` directly into the `result` dict that `worker/tasks.py` persists to Postgres JSONB. `solver_output["approach"]` holds the live `Approach` pydantic instance (by design, so downstream nodes can consume it directly) — attempting to persist it raised `TypeError: Object of type Approach is not JSON serializable` the first time a real Postgres write happened with a real approach in state.
- **Fix:** Added `_json_safe_solver_output()` in `graph/build.py`, dumping `solver_output["approach"]` via `.model_dump()` before it lands in the persisted `result` dict — mirroring how `approaches` was already dumped.
- **Files modified:** `src/algorunner/graph/build.py`
- **Verification:** `tests/graph/test_build.py#test_build_pipeline_graph_runs_analyzer_strategist_solver_end_to_end` and `tests/worker/test_tasks.py#test_solve_problem_happy_path_completes` both pass against real Postgres.
- **Committed in:** `ff1762d` (Task 2 commit)

**2. [Rule 1 - Bug] Extending the pipeline graph broke 3 pre-existing tests' single-stage OpenAI mock**
- **Found during:** Task 2, first full-suite run after wiring the new nodes
- **Issue:** `tests/graph/test_build.py`'s two pre-existing tests and `tests/worker/test_tasks.py`'s happy-path test all used the shared `mock_openai_parse` fixture, which returns the same canned `ProblemAnalysis` for every `parse()` call. Once the graph ran Strategist/Solver after Analyzer, the second call (Strategist) received the same `ProblemAnalysis` object and crashed with `AttributeError: 'ProblemAnalysis' object has no attribute 'approaches'` trying to check the empty-approaches guard.
- **Fix:** Added a shared `mock_pipeline_openai` fixture to `tests/conftest.py` that drives `AsyncMock(side_effect=[...])` with one canned response per node (analysis, then approaches, then solver_output), and switched all 3 affected tests to it.
- **Files modified:** `tests/conftest.py`, `tests/graph/test_build.py`, `tests/worker/test_tasks.py`
- **Verification:** `uv run pytest tests/ -q` → 30 passed (was 26 before this plan).
- **Committed in:** `ff1762d` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs directly surfaced by extending the pipeline graph, the core scope of Task 2)
**Impact on plan:** Both fixes were necessary consequences of wiring two new nodes into an already-tested graph; no scope creep beyond what Task 2's own action already required.

## Issues Encountered

- **Local `.venv` `.pth`-hidden-flag quirk recurred** (same symptom documented in Plan 02-02's SUMMARY): `uv`-created `.pth` files in this worktree's `.venv` repeatedly had the macOS `hidden` file flag set between Bash invocations, making CPython 3.14's `site.py` silently skip them and breaking `import algorunner` with `ModuleNotFoundError`. Worked around via `chflags nohidden .venv/lib/python3.14/site-packages/*.pth` before each `pytest`/`python` invocation in this session. Not a code issue — nothing to fix in the repo.
- **Plan text vs. actual TaskError code for the empty-approaches case:** the plan's `must_haves.truths` states the graph "raises a structured `TaskError` (code=`EMPTY_APPROACHES`)" on zero approaches, but the plan's own `<action>` explicitly instructs "do not add a second exception-handling layer here; rely on the CR-01 handler already in place from Plan 02-02" — and CR-01's handler (`worker/tasks.py`) hardcodes `TaskError(code="UNHANDLED_EXCEPTION", ...)` for every caught exception, not a per-exception-type code. Followed the plan's literal, unambiguous action instruction (no second handling layer) over the aspirational code value in the truths section. Manually verified (ad-hoc script, not committed — outside this plan's stated `<verify>` scope) that the actual runtime behavior is: `solution_strategist_node` raises `ValueError("Strategist returned zero approaches")` → propagates through `graph.ainvoke` → caught by CR-01 → task transitions to `TaskStatus.FAILED` with `TaskError(code="UNHANDLED_EXCEPTION", message="Strategist returned zero approaches")`. The core safety property (never an unhandled `IndexError`, never a stuck non-terminal status, always a structured error with the specific failure message) holds; only the literal `code` string value differs from the truths section's wording. Flagging for a human/future-plan decision on whether a distinct `EMPTY_APPROACHES` code is worth adding later (would require a small, deliberate change to CR-01's generic handler, which this plan's action text explicitly said not to do).

## User Setup Required

None. This plan's own tests all mock the OpenAI client (`mock_openai_parse`/`mock_pipeline_openai`); no live OpenAI call was made or needed to execute or verify this plan.

## Next Phase Readiness

- Plan 02-04 (Code Generator/Test Generator) can read `state["solver_output"]["approach"]`/`state["solver_output"]["algorithm"]` directly to construct the real `Solution` once `code_python`/`code_go`/`tests` are generated.
- `mock_pipeline_openai` (tests/conftest.py) is ready for Plan 02-04's node tests to extend with a 4th canned response.
- The empty-approaches TaskError code discrepancy (see Issues Encountered) is a small, pre-existing-plan-text inconsistency, not a blocker — flagging it here so it isn't silently forgotten if a later plan or the human coordinator wants a distinct `EMPTY_APPROACHES` code for API/UI error handling.

---
*Phase: 02-verified-single-solution-core-pipeline*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 7 created files confirmed present on disk. All 3 commits (`7d3ef6c`, `94f955e`, `ff1762d`) confirmed present in `git log`. Full test suite re-run: `uv run pytest tests/ -q` → 30 passed. Plan-level verification command re-run: `uv run pytest tests/agents/test_strategist_solver.py tests/graph/ -q` → 6 passed. `git status --short` clean at time of this SUMMARY (before staging SUMMARY.md/REQUIREMENTS.md).
