---
phase: 02-verified-single-solution-core-pipeline
plan: 05
subsystem: execution
tags: [asyncio, subprocess, go, docker, langgraph, process-group, denylist]

requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Plan 02-04's Solution (code_python/code_go/tests) produced by code_generator/test_generator nodes, ExecutionResult schema, mock_pipeline_openai pattern"
provides:
  - "CodeExecutor Protocol (tools/base.py) - single swap surface for execution backends (EXEC-03)"
  - "SubprocessPythonExecutor - async subprocess, AST import denylist, process-group timeout kill, best-effort rlimits, minimal env (EXEC-01)"
  - "SubprocessGoExecutor - go build into pre-seeded go-template scaffold, direct binary run (never go run), text-scan import denylist, same kill/reap helper for build and run (EXEC-02)"
  - "Worker Docker image now contains a Go toolchain (multi-stage golang:1.27-bookworm) - verified by building the image and running `go version` (go1.27.1) inside it"
  - "build_pipeline_graph runs test_generator -> execute_python -> execute_go -> finalize_success; finalize_success persists python_execution/go_execution"
affects: ["02-06 (Reviewer reads python_execution/go_execution)", "02-07 (correction loop / editorial)"]

actuals:
  tokens: 8118
  tasks: 3
  commits: 5
plan_head_before: 1dd886e440d842b00a78e5904148d920c68ec029

tech-stack:
  added: []
  patterns:
    - "Executor `tests` argument is literal source appended after `code` (Python: assert statements; Go: statements inside generated func main) - matches RESEARCH.md Pattern 3, no separate interchange format"
    - "One shared process-group timeout-kill/reap helper (_run_with_timeout) guards both go build and the compiled binary"
    - "Per-limit try/except in _limit_resources so a kernel that cannot honor one rlimit does not abort subprocess creation"
    - "Go harness imports injected only when missing AND harness non-empty (Go rejects duplicate and unused imports)"

key-files:
  created:
    - src/algorunner/tools/base.py
    - src/algorunner/tools/python_executor/__init__.py
    - src/algorunner/tools/python_executor/subprocess_backend.py
    - src/algorunner/tools/go_executor/__init__.py
    - src/algorunner/tools/go_executor/subprocess_backend.py
    - go-template/go.mod
    - tests/tools/__init__.py
    - tests/tools/test_executors.py
  modified:
    - docker/Dockerfile.worker
    - src/algorunner/graph/build.py
    - tests/graph/test_build.py

key-decisions:
  - "Executor `tests: str` is literal language source (assert statements / Go statements), not a data format; graph/build.py's _render_test_harness produces it per language"
  - "go-template/go.mod declares `go 1.26` (minimum-version directive) so it builds under both the local go1.26.3 and the container's go1.27.1"
  - "Go timeout_s applies independently to the build step and the run step"
  - "Import denylists are the documented interim control; real sandboxing (SEC-02/03) stays deferred to v2"

patterns-established:
  - "Deterministic tools live behind the CodeExecutor Protocol; graph nodes are thin wrappers"

requirements-completed: [EXEC-01, EXEC-02, EXEC-03]

coverage:
  - id: D1
    description: "PythonExecutorTool runs generated Python via asyncio subprocess in a fresh temp dir and returns a structured ExecutionResult"
    requirement: EXEC-01
    verification:
      - kind: unit
        ref: "tests/tools/test_executors.py#test_python_executor_runs_correct_solution"
        status: pass
      - kind: unit
        ref: "tests/tools/test_executors.py#test_python_executor_reports_failure_on_assertion_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Infinite-looping generated Python is killed via the whole process group and returns passed=False, exit_code=-1 without hanging"
    requirement: EXEC-01
    verification:
      - kind: unit
        ref: "tests/tools/test_executors.py#test_python_executor_kills_infinite_loop_via_process_group"
        status: pass
    human_judgment: false
  - id: D3
    description: "Denylisted Python imports rejected before any subprocess spawns, name surfaced in stderr"
    requirement: EXEC-01
    verification:
      - kind: unit
        ref: "tests/tools/test_executors.py#test_python_executor_rejects_denylisted_import_without_spawning_subprocess"
        status: pass
    human_judgment: false
  - id: D4
    description: "GoExecutorTool compiles generated Go into the go-template scaffold and runs the binary directly, with denylist rejection and process-group timeout kill"
    requirement: EXEC-02
    verification:
      - kind: unit
        ref: "tests/tools/test_executors.py#test_go_executor_runs_correct_solution"
        status: pass
      - kind: unit
        ref: "tests/tools/test_executors.py#test_go_executor_rejects_disallowed_import_without_spawning_subprocess"
        status: pass
      - kind: unit
        ref: "tests/tools/test_executors.py#test_go_executor_kills_infinite_loop_via_process_group"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both executors satisfy the identical CodeExecutor Protocol run() signature"
    requirement: EXEC-03
    verification:
      - kind: other
        ref: "tools/base.py CodeExecutor; both classes exercised with the same three scenarios (happy path, timeout, denylist) in tests/tools/test_executors.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "Worker Docker image contains a working Go toolchain"
    requirement: EXEC-02
    verification:
      - kind: other
        ref: "docker build -f docker/Dockerfile.worker . then docker run --rm <image> go version -> go1.27.1 linux/arm64"
        status: pass
    human_judgment: false
  - id: D7
    description: "Pipeline graph runs generation through real execution end-to-end against real Postgres, producing passing ExecutionResults for both languages on a known-correct solution"
    requirement: EXEC-01
    verification:
      - kind: integration
        ref: "tests/graph/test_build.py#test_build_pipeline_graph_runs_full_pipeline_through_execution"
        status: pass
    human_judgment: false
  - id: D8
    description: "Generated code does not inherit worker secrets (minimal env) and cannot fork (RLIMIT_NPROC=0) on Linux containers"
    requirement: EXEC-01
    verification: []
    human_judgment: true
    rationale: "env allowlist is asserted by code inspection (grep env=) only; rlimit enforcement could not be exercised on this macOS host and no Linux container test was run"

duration: 24min
completed: 2026-09-23
status: complete
---

# Phase 2 Plan 5: Python and Go Executors Summary

**Deterministic Python (asyncio subprocess, AST import denylist, process-group kill, minimal env) and Go (go build + direct binary run in the go-template scaffold) executors behind a shared CodeExecutor Protocol, wired into the LangGraph pipeline so generated code is actually executed, plus a Go toolchain added to the worker Docker image.**

## Performance

- **Duration:** ~24 min
- **Started:** 2026-09-23T15:55:00Z (approx)
- **Completed:** 2026-09-23T16:19:00Z
- **Tasks:** 3
- **Files modified:** 11 (8 created, 3 modified)

## Accomplishments

- `SubprocessPythonExecutor`: never blocks the event loop, checks an AST import denylist (os/subprocess/socket/shutil/sys/ctypes/multiprocessing/threading) before spawning anything, runs with `env={PATH}` only, kills the whole process group (SIGTERM, SIGKILL fallback, reap) on timeout.
- `SubprocessGoExecutor`: copies `go-template/` per run, per-run `GOCACHE`/`GOMODCACHE`, `go build` then runs the binary directly; the same kill/reap helper protects both the build and the run; rejects net/os-exec/syscall/unsafe (including subpackages) before building.
- Worker image: multi-stage `golang:1.27-bookworm` toolchain stage. Verified the tag exists on Docker Hub, built the image, and ran `go version` inside it (go1.27.1 linux/arm64).
- Graph: `test_generator -> execute_python -> execute_go -> finalize_success`; the persisted result now carries both `ExecutionResult`s. An end-to-end test against real Postgres runs a known-correct solution through real `python3` and real `go build` and asserts both pass.

## Task Commits

1. **Task 1 RED:** `a4641df` (test) - CodeExecutor Protocol + failing Python executor tests (ModuleNotFoundError)
2. **Task 1 GREEN:** `58930c4` (feat) - SubprocessPythonExecutor
3. **Task 2 RED:** `dccce89` (test) - go-template scaffold + failing Go executor tests (ModuleNotFoundError)
4. **Task 2 GREEN:** `fbfdfe0` (feat) - SubprocessGoExecutor + Dockerfile Go toolchain
5. **Task 3:** `76c40a4` (feat) - graph wiring + end-to-end test (`type="auto"`, single commit)

**Plan metadata:** committed with this SUMMARY (docs).

## TDD Gate Compliance

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| Task 1 | `a4641df` | `58930c4` | not needed | Pass |
| Task 2 | `dccce89` | `fbfdfe0` | not needed | Pass |

RED evidence: `ModuleNotFoundError: No module named 'algorunner.tools.python_executor.subprocess_backend'` (Task 1) and `...go_executor.subprocess_backend` (Task 2), from pytest collection output. `gsd_run check tdd-red-evidence` not used (no pytest adapter; same precedent as prior plans).

## Files Created/Modified

- `src/algorunner/tools/base.py` - CodeExecutor Protocol
- `src/algorunner/tools/python_executor/subprocess_backend.py` - Python executor
- `src/algorunner/tools/go_executor/subprocess_backend.py` - Go executor
- `go-template/go.mod` - `module algorunner-exec`, `go 1.26`
- `docker/Dockerfile.worker` - Go toolchain stage, `COPY go-template`
- `src/algorunner/graph/build.py` - execute nodes, `_render_test_harness`, `_ensure_go_imports`, extended `finalize_success`
- `tests/tools/test_executors.py` - 8 tests (4 Python, 4 Go)
- `tests/graph/test_build.py` - 1 new end-to-end execution test with a known-correct mock

## Decisions Made

See `key-decisions`. In short: `tests` is literal per-language source; `go 1.26` directive; Go `timeout_s` is per step; import denylists are the interim control.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_limit_resources` crashed subprocess creation on macOS**
- **Found during:** Task 1 (first GREEN run)
- **Issue:** RESEARCH.md's Pattern 3 applies three rlimits unconditionally. On this macOS host `setrlimit(RLIMIT_AS, ...)` raises `ValueError: current limit exceeds maximum limit`, which surfaces as `SubprocessError: Exception occurred in preexec_fn` and made every executor call fail.
- **Fix:** Each limit is applied independently inside try/except (ValueError, OSError). Linux containers (deployment target) still get all three.
- **Files modified:** src/algorunner/tools/python_executor/subprocess_backend.py
- **Verification:** all 4 Python executor tests pass
- **Committed in:** 58930c4

**2. [Rule 1 - Bug] `_render_test_harness` given a required `language` keyword**
- **Found during:** Task 3
- **Issue:** The plan specifies one `_render_test_harness(tests: list[dict]) -> str` reused by both node wrappers. Python `assert` lines are not valid Go and Go has no `eval`, so a single no-parameter renderer would hand one executor unusable source. Also verified with the Go compiler that imports must precede all declarations and that both duplicate and unused imports are compile errors, so the Go path additionally needs `_ensure_go_imports`.
- **Fix:** `_render_test_harness(tests, *, language)` still walks `tests` in one place but emits per-language syntax; `execute_go_node` injects only missing, actually-used `reflect`/`os` imports.
- **Files modified:** src/algorunner/graph/build.py
- **Verification:** end-to-end test passes for both languages
- **Committed in:** 76c40a4

**3. [Rule 1 - Bug] `go.mod` uses `go 1.26`, not the plan's `go 1.27`**
- **Found during:** Task 2
- **Issue:** Only go1.26.3 is installed locally and the acceptance criteria require `pytest -k go` to pass locally; a `go 1.27` directive would trigger a toolchain download or failure.
- **Fix:** `go 1.26` (a minimum-version directive) builds under both go1.26.3 and the container's go1.27.1.
- **Files modified:** go-template/go.mod
- **Committed in:** dccce89

**4. [Rule 3 - Blocking] Test-file collection collisions and D-11 floor in the new integration test**
- **Found during:** Task 3
- **Issue:** Importing `TestCase` by name made pytest try to collect it (same as 02-04); the first mock generated only 3 tests and tripped the D-11 minimum of 10.
- **Fix:** Import aliased as `GoTestCase`; mock now generates 11 scalar `double(n)` cases.
- **Files modified:** tests/graph/test_build.py
- **Committed in:** 76c40a4

**5. [Note] Plan frontmatter `files_modified` omitted `tests/graph/test_build.py`**, though Task 3's action requires an integration test there. Added per the action text.

**6. [Note] Acceptance grep for the file-size rlimit name** required the literal name to be absent from the source, so explanatory comments paraphrase it.

---

**Total deviations:** 4 auto-fixed (3 Rule 1, 1 Rule 3), 2 notes
**Impact on plan:** All required for correctness or to make the plan's own acceptance criteria satisfiable; no scope creep.

## Issues Encountered

- **Known limitation (important, not fixed here):** The Go and Python harnesses treat each test's `input`/`output` as an expression in the target language. The Test Generator prompt (Plan 02-04, not in this plan's file list) only sees `code_python` and asks for pairs "matching the shape of provided examples" (LeetCode-style prose such as `nums = [2,7,11,15], target = 9`), and the Code Generator does not fix a function name. So real LLM output will not reliably evaluate through either harness, and the Go harness cannot reuse Python-style list literals at all. The end-to-end test deliberately uses a scalar `double(n)` solution where one expression is valid in both languages. A follow-up (language-aware test format plus a fixed entry-point convention, likely in 02-06/02-07 or a quick task) is needed before Core Value verification is reliable on real problems. Logged via `gsd windows append` locally but not committed (avoids cross-worktree add/add conflicts); the orchestrator should register it from here.
- **Denylist is not a sandbox:** `eval` of test expressions and `__import__` calls are not caught by the import scan. This is the documented v1 interim control (T-02-05-01); SEC-02/03 remain deferred.
- **rlimits unverified on Linux:** RLIMIT_AS is silently skipped on macOS; enforcement was not exercised in a Linux container test.
- **Worktree environment:** no `.env` in the worktree (gitignored); created a local placeholder `OPENAI_API_KEY` (never committed) since all tests mock the client. `docker compose up` hit the same shared-port conflict as 02-04 (5432/6379 already bound by an existing project); cleaned up the partial containers and ran migrate + tests directly against the running Postgres (`No pending migrations`).
- **Go toolchain:** present locally (go1.26.3), so nothing was skipped or faked.

## User Setup Required

None.

## Next Phase Readiness

- `state["python_execution"]` / `state["go_execution"]` are populated for the Reviewer (02-06). Note the limitation above: on real LLM output these may report failures caused by harness/format mismatch rather than incorrect solutions; the Reviewer plan should not treat every `passed=False` as a solution bug until the test format is made language-aware.
- The Docker worker image builds and contains Go.

---
*Phase: 02-verified-single-solution-core-pipeline*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 8 created files present on disk; all 5 task commits (`a4641df`, `58930c4`, `dccce89`, `fbfdfe0`, `76c40a4`) present in `git log`; `git rev-list --count 1dd886e..HEAD` = 5 (matches `commits: 5`). `uv run pytest tests/ -q` -> 44 passed. Plan verification `uv run pytest tests/tools/test_executors.py tests/graph/ -q` -> 13 passed. Acceptance greps: no RLIMIT_FSIZE literal, `start_new_session=True` and `env=` present, `go build` present and no `"go", "run"`, `golang:` in Dockerfile, both `add_node` lines present.
