---
phase: 02-verified-single-solution-core-pipeline
verified: 2026-09-24T12:00:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - src/algorunner/agents/reviewer/node.py
  - src/algorunner/api/routes/tasks.py
  - src/algorunner/graph/build.py
  - src/algorunner/graph/harness.py
  - src/algorunner/graph/routing.py
  - src/algorunner/tools/go_executor/subprocess_backend.py
  - src/algorunner/tools/python_executor/subprocess_backend.py
  - src/algorunner/worker/tasks.py
covered_digest: "v1:sha256:e210d54ae0e3953e378137bd285ecb6ca88139cfe24cd8eb1cf0faf91a723fc3"
behavior_unverified: 0
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Live ambiguous-problem run: POST an underspecified problem, wait for awaiting_clarification, GET then POST /clarification, and confirm the task resumes and completes."
    expected: "Status goes awaiting_clarification, then analyzing_problem, then completed. The Analyzer's LLM call is not re-run from START (same thread_id)."
    why_human: "The pause/resume path is proven only by automated tests with a mocked LLM against real Postgres checkpoints. The 02-08 live check exercised two non-ambiguous problems, so a real model deciding needs_clarification was never observed."
  - test: "Decide whether CR-01 (generated code runs as root and can read OPENAI_API_KEY via /proc/1/environ) and CR-02 (executor children are not killed on cancellation or global timeout) must be fixed before Phase 3."
    expected: "A product-owner decision: accept as v1 no-sandbox risk, or schedule a hardening plan (drop privileges to uid 65534, killpg on CancelledError, Go rlimits)."
    why_human: "These are advisory security and reliability findings, not failures of the phase-goal truths. They are an owner risk-acceptance decision."
  - test: "Optional: run the literal Two Sum end-to-end script (PHASE2_LIVE_OK)."
    expected: "Task completes with python_execution.passed, go_execution.passed and review.passed all true."
    why_human: "Requires a real OPENAI_API_KEY. The user accepted two other live tasks in place of it."
---

# Phase 2: Verified Single-Solution Core Pipeline Verification Report

**Phase Goal:** A submitted problem is actually analyzed and solved by the AI pipeline, producing one algorithm approach whose Python and Go code are proven correct by real execution, with clarification and correction handled automatically.
**Verified:** 2026-09-24
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Analyzer extracts constraints and intent from EN/RU text, assigns difficulty, and moves to `awaiting_clarification` when ambiguous | VERIFIED | `problem_analyzer_node` makes a real `call_structured` call returning `ProblemAnalysis`. `decide_after_analysis` routes `needs_clarification` to `clarification_gate`, which calls `interrupt()`. `_handle_result_or_pause` persists the pause via `update_task_clarification`. `tests/graph/test_clarification.py` passes, including round cap D-04. |
| 2 | `POST /api/v1/tasks/{id}/clarification` resumes from the checkpointed state, not a restart | VERIFIED | `answer_clarification` does an atomic compare-and-set (`attempt_consume_clarification`), then enqueues `resume_task_with_clarification`. That task invokes `Command(resume=answer)` on the same `thread_id`. `test_ambiguous_problem_pauses_then_resumes_same_thread` passes on real Postgres. The concurrent-POST test shows exactly one enqueue, and a second POST returns 409. The live path with a real model was not run (see human item 1). |
| 3 | Generic Solver elaborates a tagged approach into Python and Go plus generated tests, using examples and adding edge cases | VERIFIED | Strategist, Solver, Code Generator and Test Generator nodes exist and are wired `strategist -> solver -> code_generator -> test_generator`. `_validate_code` checks the entry point in both languages. Tests are language-neutral and structured (02-09). Examples are preserved and a 10-test minimum is enforced (`tests/agents/test_code_test_gen.py` passes). Two live tasks produced genuine implementations. |
| 4 | Python and Go are actually executed via swappable executors with structured pass/fail, and the Reviewer produces a structured ReviewResult with justified complexity | VERIFIED | `tools/base.py` defines the `CodeExecutor` Protocol. `execute_python_node` and `execute_go_node` render a harness and run real subprocess and `go build` executors. `_require_pass_marker` rejects exit-0 without the harness marker. `reviewer_node` synthesizes a deterministic failure review when execution failed, so the LLM never overrides real execution. The prompt requires `complexity_reasoning`. The 142-test suite ran real python3 and go build and passed. Both live tasks had both executions and the review pass. |
| 5 | Failing review routes to a bounded correction loop with prior context ending in success or clean FAILED, with backoff retries and a global timeout | VERIFIED | `decide_after_review` terminates at `iterations >= max_iterations` (`finalize_failed`, `CORRECTION_LOOP_EXHAUSTED`). Solver, Code Generator and Test Generator prompts all include `format_review_history`. `test_always_failing_review_exhausts_max_iterations_cleanly` passes. `call_structured` uses tenacity with exponential wait on `APITimeoutError` and `RateLimitError`. `_invoke_with_budget` wraps `ainvoke` in `wait_for` against cumulative active time and marks FAILED/`GLOBAL_TIMEOUT` (3 tests pass). |

**Score:** 5/5 truths verified (0 behavior-unverified)

### Requirements Coverage

Every ID in the phase's requirements list appears in a PLAN frontmatter `requirements:` field, and all appear in REQUIREMENTS.md. No orphaned requirements.

| Requirement | Source Plan | Status | Evidence |
|---|---|---|---|
| INTAKE-02, INTAKE-03 | 02-02 | SATISFIED | Analyzer node and `ProblemAnalysis` schema |
| INTAKE-04, INTAKE-05, API-03 | 02-07 | SATISFIED | Router, gate node, POST/GET clarification endpoints, atomic consume, resume task; graph, API and storage tests pass |
| STRAT-01, STRAT-03, STRAT-04 | 02-03 | SATISFIED | Strategist (technique tag) and single generic Solver |
| CODE-01..04 | 02-04, 02-09 | SATISFIED | Code Generator (Python and Go), Test Generator, D-10/D-11 |
| EXEC-01..03 | 02-05, 02-09 | SATISFIED | Python and Go subprocess executors behind the `CodeExecutor` Protocol; `tests/tools/test_executors.py` passes |
| REV-01..05 | 02-06 | SATISFIED | Reviewer node, `ReviewResult`, complexity justification, correction loop with history, `max_iterations` bound |
| ORCH-03 | 02-01 | SATISFIED | `client_factory.model_for(<agent>)` per-agent config |
| ORCH-04 | 02-02, 02-07 | SATISFIED | Postgres checkpointer with `durability="sync"`; resume tested |
| INFRA-03 | 02-01 | SATISFIED | tenacity retry wrapper (scope caveat, see WR-03 below) |
| INFRA-04 | 02-08 | SATISFIED | `_invoke_with_budget` global active-time budget |

**Traceability documentation gap (non-blocking):** REQUIREMENTS.md still shows INTAKE-04, INTAKE-05, EXEC-01..03, REV-01..05, API-03 and INFRA-04 as unchecked, with "Pending" in the traceability table. The code and tests satisfy them, so update these markers during phase close.

### Key Link Verification

| From | To | Status | Details |
|---|---|---|---|
| `worker/tasks.py` | `graph/build.py` (`build_pipeline_graph`) | WIRED | Shared checkpointer from `broker.state.checkpointer` |
| `api/routes/tasks.py` | `resume_task_with_clarification.kiq` | WIRED | Enqueued only after the atomic status transition |
| `graph/build.py` execute nodes | `harness.py` renderers and executors | WIRED | Uses `solution.entry_point` and `solution.tests` |
| `reviewer` | `decide_after_review` | WIRED | Routes to solver, code_generator, finalize_success or finalize_failed |
| `finalize_*` | `_handle_result_or_pause` | WIRED | Persists completed or failed state |

### Data-Flow Trace (Level 4)

Solver output flows into Code Generator (`solver_output`), then into `Solution` and tests, then into rendered harness programs, then real executions, then the Reviewer, then the persisted `result`. No hardcoded or static terminals were found. Two live tasks confirmed real data end-to-end.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite (real python3, go build, Postgres) | `OPENAI_API_KEY=sk-dummy UV_PROJECT_ENVIRONMENT=/Users/egor/.venvs/algorunner uv run pytest -q` | 142 passed in 60.6s | PASS |
| Live full-stack, real OpenAI (per 02-08-SUMMARY, user-attested) | Two live tasks | completed, exec and review passed | PASS (attested, not re-run by the verifier) |

### Probe Execution

Step 7c: SKIPPED (no probe scripts declared or present).

### Anti-Patterns Found

No TBD/FIXME/XXX debt markers were checked as blockers. The code review findings are treated as advisory hardening and do not fail a truth:

| Finding | Severity | Impact on goal |
|---|---|---|
| CR-01: generated code runs as root and can read `/proc/1/environ` (API key), and RLIMIT_NPROC is a no-op as root | Warning (security) | Correctness goal is unaffected. Project constraints accept "no sandboxing in v1", but the executor docstring over-claims env-secrecy. Owner decision needed. |
| CR-02: children not killed on `CancelledError` (global timeout, shutdown); the Go binary has no rlimits | Warning (reliability) | The task is still marked FAILED/`GLOBAL_TIMEOUT` (INFRA-04 met). The runaway process leaks resources. |
| WR-03: retry covers only timeout and rate-limit, so 5xx and connection errors are fatal, and `insufficient_quota` is retried | Warning | INFRA-03 literally met (timeout and rate-limit retry with backoff). Scope is narrow. |
| WR-07: `ReviewResult.passed=True` is not cross-checked against critical issues | Warning | Real execution still gates the reviewer LLM. Only reviewer self-inconsistency can slip through. |
| WR-09: a re-delivered `solve_problem` resets status and restarts from START | Warning | Affects duplicate delivery only. Normal flow is unaffected. |
| WR-05, WR-06, WR-08 (broker timeout units), WR-01, WR-02, WR-04, WR-10 | Warning | Edge-case and hardening items. None invalidates a success criterion. |

### Human Verification Required

1. **Live ambiguous-problem clarification run.** POST an underspecified problem, wait for `awaiting_clarification`, GET and POST the clarification, and confirm the task resumes on the same thread and completes. Only the mocked-LLM path is proven.
2. **Risk-acceptance decision on CR-01 and CR-02.** Accept for v1 or schedule hardening before Phase 3.
3. **Optional.** Run the literal Two Sum script.

### Gaps Summary

No must-have truth failed. All five roadmap success criteria are backed by code, wiring, and passing tests (142/142, including real execution and real Postgres checkpoints), plus user-attested live full-stack runs. The status is `human_needed`, not `passed`, because the clarification path has never been exercised live with a real model, and because the CR-01/CR-02 security and reliability findings need an owner decision. REQUIREMENTS.md checkboxes for 15 completed requirements are stale and should be updated.

---

_Verified: 2026-09-24_
_Verifier: Claude (gsd-verifier)_
