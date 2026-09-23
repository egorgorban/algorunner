---
phase: 02-verified-single-solution-core-pipeline
plan: 08
subsystem: worker
tags: [timeout, asyncio, langgraph, infra-04]
requires:
  - phase: 02-07
    provides: resume_task_with_clarification, active_execution_seconds column and add_active_execution_seconds helper
provides:
  - _invoke_with_budget wrapper bounding cumulative active execution time (D-08, 600s)
affects: []
tech-stack:
  added: []
  patterns: [wait_for-bounded graph invocation with persisted cumulative budget]
key-files:
  created:
    - tests/graph/test_global_timeout.py
  modified:
    - src/algorunner/worker/tasks.py
key-decisions:
  - "Budget accrues only around ainvoke calls, so awaiting_clarification wait time is excluded by construction (RESEARCH A1)"
status: complete
completed: 2026-09-24
actuals:
  tasks: 2
  commits: 1
plan_head_before: dc31c29b815c79baec94ed6b7d4bbd909104a0e6
commits: 1
---

# Phase 2 Plan 08: Global timeout budget Summary

`_invoke_with_budget` now wraps both `solve_problem` and `resume_task_with_clarification`: it short-circuits with FAILED/`GLOBAL_TIMEOUT` before any `ainvoke` when the persisted `active_execution_seconds` already meets `settings.global_timeout_s`, cancels via `asyncio.wait_for` when a run exceeds the remaining budget, and always adds elapsed time to the task row.

## Tasks

1. Task 1 (f2051e2): wrapper plus three fast tests (exhausted-budget short-circuit with `ainvoke` never called, mid-flight cancel returning in under 3s, success path accruing time). Full suite: 142 passed with `OPENAI_API_KEY=test-dummy`.
2. Task 2 (live full-stack verification): verified by the user against the real docker stack (built from main at cdbccdd) with a real `OPENAI_API_KEY`. Two live tasks reached `completed`: a LeetCode "reduce x to zero" problem (technique: brute force, ~114s active time) and a second problem (technique: sliding window / two pointers). For both, `python_execution.passed`, `go_execution.passed` and `review.passed` were true, generated Python/Go code was a genuine implementation, and `review.complexity_reasoning` was a structural justification. The literal Two Sum script (`PHASE2_LIVE_OK`) was not run; the user accepted the two live results as sufficient. Observation: worker logs show only taskiq startup lines because graph nodes do not log progress, and a task takes ~1-2 min, so a task can look stuck in `queued`/`analyzing_problem` from outside.

## Deviations from Plan

None for Task 1. Note: the `_invoke_with_budget` grep criterion `graph.ainvoke(` count is 1, located inside the helper only.

## Known Stubs

None.

## Threat Flags

None. T-02-08-01 mitigated and tested.

## Self-Check: PASSED

tests/graph/test_global_timeout.py and the worker/tasks.py change exist; commit f2051e2 present.
