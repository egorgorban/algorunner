---
phase: 02-verified-single-solution-core-pipeline
plan: 04
subsystem: agents
tags: [langgraph, openai, structured-outputs, pydantic]

# Dependency graph
requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Plan 02-03's solver_node/GraphState.solver_output, build_pipeline_graph (analyzer->strategist->solver->finalize_success), and mock_pipeline_openai test fixture"
provides:
  - "code_generator_node(state) -> dict — constructs the real Solution (schemas/solution.py) from state[\"solver_output\"] plus freshly LLM-generated code_python/code_go, tests=[]"
  - "test_generator_node(state) -> dict — merges state[\"examples\"] verbatim (D-10, enforced in Python code) with >=settings.test_generator_min_tests generated tests when fewer than 3 examples are provided (D-11, ValueError on shortfall)"
  - "build_pipeline_graph now runs analyzer -> strategist -> solver -> code_generator -> test_generator -> finalize_success end-to-end against real Postgres"
  - "finalize_success's persisted result[\"solution\"] (dumped Solution) supersedes the interim result[\"solver_output\"] key from Plan 02-03"
  - "mock_pipeline_openai fixture (tests/conftest.py) extended with CodeGenOutput/GeneratedTests canned responses — 5-node pipeline mock, reusable by Plan 02-05's executor tests"
affects: ["02-05 (PythonExecutor/GoExecutor tools — run the real Solution.code_python/code_go/tests this plan now produces)", "02-06/02-07 (Reviewer/correction loop, Editorial Writer — read the full Solution)"]

# Actuals (#2632)
actuals:
  tokens: 6910
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Local, narrower structured-output schema per LLM call (CodeGenOutput, GeneratedTests/TestCase) with the durable inter-node contract (Solution) assembled by hand in the node body from the prior node's state plus the LLM's narrow output — same pattern as Plan 02-03's SolverOutput"
    - "Verbatim-preservation merge performed in Python, never trusted to the LLM's echo (D-10) — provided examples and generated tests are two separately-typed lists concatenated after independent validation, not a single LLM-produced list"
    - "Module-qualified import (import ... as module, then module.symbol) in a test file to avoid pytest collecting a plan-mandated production symbol whose name matches pytest's default test_*/Test* discovery patterns"

key-files:
  created:
    - src/algorunner/agents/code_generator/__init__.py
    - src/algorunner/agents/code_generator/node.py
    - src/algorunner/agents/code_generator/prompts.py
    - src/algorunner/agents/test_generator/__init__.py
    - src/algorunner/agents/test_generator/node.py
    - src/algorunner/agents/test_generator/prompts.py
    - tests/agents/test_code_test_gen.py
  modified:
    - src/algorunner/graph/build.py
    - tests/conftest.py
    - tests/graph/test_build.py

key-decisions:
  - "CodeGenOutput/GeneratedTests/TestCase stay module-local in code_generator/node.py and test_generator/node.py (not added to schemas/solution.py) — each is only the narrow shape the corresponding LLM call is responsible for; the durable Solution contract is assembled by hand in each node body, mirroring Plan 02-03's SolverOutput precedent"
  - "tests/agents/test_code_test_gen.py imports algorunner.agents.test_generator.node as a module and accesses test_generator_node/TestCase through it, rather than importing those two names directly — both are plan-mandated production names that collide with pytest's default test_*/Test* collection patterns"

requirements-completed: [CODE-01, CODE-02, CODE-03, CODE-04]

coverage:
  - id: D1
    description: "Code Generator constructs a real Solution with non-empty, dual-language (Python + Go) generated code for the analyzed problem's single selected approach, tests=[] until the Test Generator runs"
    requirement: CODE-01
    verification:
      - kind: unit
        ref: "tests/agents/test_code_test_gen.py#test_code_generator_node_produces_solution_with_empty_tests"
        status: pass
      - kind: other
        ref: "grep -n 'min_length=1' src/algorunner/agents/code_generator/node.py — both code_python and code_go constrained"
        status: pass
    human_judgment: false
  - id: D2
    description: "Test Generator never drops or rewrites a user-provided example — every TaskSubmission.examples entry appears unmodified in the merged Solution.tests list"
    requirement: CODE-03
    verification:
      - kind: unit
        ref: "tests/agents/test_code_test_gen.py#test_test_generator_node_preserves_provided_examples"
        status: pass
      - kind: other
        ref: "grep -n 'provided = \\[' src/algorunner/agents/test_generator/node.py — merge performed in Python, not trusted to the LLM"
        status: pass
    human_judgment: false
  - id: D3
    description: "When fewer than 3 examples are provided, Test Generator requires >=settings.test_generator_min_tests (10) generated tests, raising ValueError on a shortfall rather than silently shipping too few tests"
    requirement: CODE-04
    verification:
      - kind: unit
        ref: "tests/agents/test_code_test_gen.py#test_test_generator_node_raises_on_shortfall"
        status: pass
      - kind: unit
        ref: "tests/agents/test_code_test_gen.py#test_test_generator_node_zero_provided_examples"
        status: pass
      - kind: other
        ref: "grep -n 'test_generator_min_tests' src/algorunner/agents/test_generator/node.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "build_pipeline_graph runs analyzer -> strategist -> solver -> code_generator -> test_generator -> finalize_success end-to-end against real Postgres, producing a persisted Solution with non-empty dual-language code and a merged test list"
    requirement: CODE-02
    verification:
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_pipeline_graph_runs_full_pipeline_through_code_and_test_gen"
        status: pass
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_pipeline_graph_runs_analyzer_strategist_solver_end_to_end"
        status: pass
    human_judgment: false

duration: ~9 min
completed: 2026-09-23
status: complete
---

# Phase 2 Plan 4: Code Generator + Test Generator Nodes Summary

**Code Generator constructs the real `Solution` with fresh LLM-generated dual-language (Python + Go) code, and Test Generator merges user-provided examples (preserved verbatim in Python code, never trusted to the LLM) with a hard-enforced minimum of 10 generated tests when few/no examples are given — both wired into `build_pipeline_graph`'s `analyzer -> strategist -> solver -> code_generator -> test_generator -> finalize_success` chain, verified end-to-end against real Postgres.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-09-23T15:41:00Z (approx)
- **Completed:** 2026-09-23T15:50:22Z
- **Tasks:** 2
- **Files modified:** 10 (7 created, 3 modified)

## Accomplishments

- `code_generator_node` — constructs the real `Solution` (schemas/solution.py) from `state["solver_output"]` (approach/algorithm/complexity) plus a fresh LLM call producing `code_python`/`code_go` (both `Field(..., min_length=1)`, rejecting empty-string generation at the schema layer), `tests=[]` left for the Test Generator
- `test_generator_node` — calls the LLM for additional test cases, then merges in Python (never trusts the LLM's echo — D-10): `provided = [...]` built directly from `state["examples"]`, concatenated with the LLM's generated tests; explicitly enforces D-11's numeric floor (`settings.test_generator_min_tests`, 10) in code when fewer than 3 examples were provided, raising `ValueError` on a shortfall
- `build_pipeline_graph` now runs `analyzer -> strategist -> solver -> code_generator -> test_generator -> finalize_success`; `finalize_success`'s persisted `result` dict gained `solution` (dumped `Solution`), superseding Plan 02-03's interim `solver_output` key (`solver_output` stays in `GraphState` as an internal field the Code Generator still reads directly)
- Both new prompts (`code_generator/prompts.py`, `test_generator/prompts.py`) delimit upstream-derived content (`solver_output`, `solution.code_python`, `examples`) as DATA, same prompt-injection framing as the prior three agent prompts; the Code Generator prompt also carries a soft safety guideline about unsandboxed execution (real enforcement is Plan 02-05's static denylist, per this plan's threat model)
- `tests/conftest.py`'s `mock_pipeline_openai` fixture extended from 3 to 5 canned responses (added `CodeGenOutput`, `GeneratedTests`) so the full 5-node pipeline mock stays reusable for Plan 02-05's executor tests
- New end-to-end integration test proves the full analyzer->strategist->solver->code_generator->test_generator run against real Postgres, asserting the persisted `Solution` has non-empty dual-language code and a merged test list of at least the mocked generated-test count

## Task Commits

Task 1 (`tdd="true"`, RED -> GREEN, no REFACTOR needed — implementation was already minimal):

1. **Task 1 RED:** `a63a382` (test) — failing tests for Code Generator/Test Generator nodes (`ModuleNotFoundError`, neither package existed yet)
2. **Task 1 GREEN:** `d1b96ed` (feat) — `code_generator_node`/`test_generator_node`, `CodeGenOutput`, `GeneratedTests`/`TestCase`

Task 2 (`type="auto"`, single commit):

3. **Task 2:** `9750d5f` (feat) — wired Code Generator + Test Generator into `build_pipeline_graph`; extended `mock_pipeline_openai`; updated 1 pre-existing test's assertion, added 1 new end-to-end test

**Plan metadata:** committed alongside this SUMMARY.

## TDD Gate Compliance

Task 1 only (`tdd="true"`); Task 2 is `type="auto"`, not TDD.

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| Task 1 (Code Generator/Test Generator nodes) | `a63a382` | `d1b96ed` | — (not needed) | Pass |

RED-phase evidence: `ModuleNotFoundError: No module named 'algorunner.agents.code_generator'`, confirmed via `pytest -q` output — `gsd_run check tdd-red-evidence` was not used (no pytest adapter; same precedent as Phase 01-02/02-01/02-02/02-03, carried forward).

## Files Created/Modified

- `src/algorunner/agents/code_generator/node.py` — `code_generator_node(state) -> dict`, `CodeGenOutput` schema
- `src/algorunner/agents/code_generator/prompts.py` — `build_code_messages(state)`, DATA-delimited solver_output, soft unsandboxed-execution safety guideline
- `src/algorunner/agents/test_generator/node.py` — `test_generator_node(state) -> dict`, `TestCase`/`GeneratedTests` schemas, D-10/D-11 enforcement
- `src/algorunner/agents/test_generator/prompts.py` — `build_test_messages(state)`, DATA-delimited code_python/examples, states the exact D-11 numeric floor
- `src/algorunner/graph/build.py` — wired code_generator/test_generator nodes; `finalize_success` now persists `result["solution"]` instead of `result["solver_output"]`
- `tests/agents/test_code_test_gen.py` — 4 unit tests (empty-tests Solution construction, zero-examples floor, verbatim preservation, shortfall ValueError)
- `tests/conftest.py` — `mock_pipeline_openai` extended with `CodeGenOutput`/`GeneratedTests` canned responses
- `tests/graph/test_build.py` — 1 pre-existing test's assertion updated (`result["solution"]` replaces `result["solver_output"]`), 1 new full-pipeline end-to-end test added

## Decisions Made

See `key-decisions` in frontmatter — summarized: (1) `CodeGenOutput`/`GeneratedTests`/`TestCase` stay module-local (not promoted to `schemas/solution.py`), mirroring Plan 02-03's `SolverOutput` precedent; (2) the test file imports the `test_generator.node` module by reference rather than importing `test_generator_node`/`TestCase` by name, to avoid a pytest collection collision (see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest collected the plan-mandated `test_generator_node` function and `TestCase` class as test items themselves**
- **Found during:** Task 1, first run of `tests/agents/test_code_test_gen.py` after implementing the GREEN nodes
- **Issue:** The plan's `<action>` mandates the exact production names `test_generator_node` (a function) and `TestCase` (a class). Both match pytest's default `test_*`/`Test*` collection patterns. Importing them directly by name into the test module (`from algorunner.agents.test_generator.node import test_generator_node, TestCase`) made pytest treat them as test items in their own right — `test_generator_node` errored with "fixture 'state' not found" (pytest tried to call it as a zero-fixture-arg test), and `TestCase` produced a `PytestCollectionWarning` (it has an `__init__`, so pytest can't instantiate it as a test class).
- **Fix:** Changed the test file's import to `import algorunner.agents.test_generator.node as test_generator_node_module` and accessed `test_generator_node_module.test_generator_node(...)` / `test_generator_node_module.TestCase(...)` / `test_generator_node_module.GeneratedTests(...)` throughout, instead of importing the colliding names directly. No production code was renamed — the plan's mandated `test_generator_node`/`TestCase` names in `src/algorunner/agents/test_generator/node.py` are unchanged.
- **Files modified:** `tests/agents/test_code_test_gen.py`
- **Verification:** `uv run pytest tests/agents/test_code_test_gen.py -q` → 4 passed, 0 warnings, 0 collection errors.
- **Committed in:** `d1b96ed` (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking pytest-collection issue caused by plan-mandated production names colliding with pytest's default discovery patterns)
**Impact on plan:** Test-file-only workaround; zero production code impact. No scope creep.

## Issues Encountered

- **Worktree lacked `OPENAI_API_KEY`** (git worktrees don't inherit gitignored `.env` files, as flagged in this plan's dispatch context). `algorunner.config.Settings` requires `openai_api_key` with no default, so even the fully-mocked test suite fails to import without *some* value present. Wrote a local, gitignored `.env` in this worktree (`OPENAI_API_KEY=sk-placeholder-worktree-mocked-tests-only`, never committed, confirmed `.env` remains in `.gitignore`) — every test in this plan's scope mocks `client_factory.get_client()` and never makes a real OpenAI call, matching this plan's stated `<verify>` scope. No live-call checkpoint was needed.
- **Port 5432/6379 already bound by a sibling worktree/main-repo's `docker compose` project** (`algorunner-postgres-1`/`algorunner-redis-1`, both already running and accepting connections). This worktree's own `docker compose up -d postgres redis garage` failed on the Postgres port bind (`garage` started fine under this worktree's own compose project on port 3900). Verified the already-running `algorunner-postgres-1`/`algorunner-redis-1` containers were healthy (`pg_isready`, `redis-cli ping`) and used them directly via `DATABASE_URL=postgresql://algorunner:algorunner@localhost:5432/...` — same host network, same effective service, no functional difference for this plan's real-Postgres integration tests. Not a code issue — nothing to fix in the repo.

## User Setup Required

None. This plan's own tests all mock the OpenAI client (`mock_openai_parse`/`mock_pipeline_openai`); no live OpenAI call was made or needed to execute or verify this plan.

## Next Phase Readiness

- Plan 02-05 (PythonExecutor/GoExecutor tools) can now run the real `Solution.code_python`/`Solution.code_go`/`Solution.tests` this plan produces — `Solution` is fully populated (approach, algorithm, code_python, code_go, tests, complexity_time, complexity_space) for the first time.
- `mock_pipeline_openai` (tests/conftest.py) is ready for Plan 02-05's executor/pipeline tests to reuse as-is (5 canned responses already cover the full analyzer->...->test_generator chain).
- No unresolved blockers from this plan. The two Issues Encountered above (worktree `.env`, shared Postgres/Redis ports) are worktree-execution-environment notes, not code defects — nothing carries forward as a blocker.

---
*Phase: 02-verified-single-solution-core-pipeline*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 7 created files confirmed present on disk. All 3 commits (`a63a382`, `d1b96ed`, `9750d5f`) confirmed present in `git log`. Full test suite re-run: `uv run pytest tests/ -q` → 35 passed. Plan-level verification command re-run: `uv run pytest tests/agents/test_code_test_gen.py tests/graph/ -q` → 8 passed. `git status --short` clean except this SUMMARY.md at time of this self-check (before staging REQUIREMENTS.md).
