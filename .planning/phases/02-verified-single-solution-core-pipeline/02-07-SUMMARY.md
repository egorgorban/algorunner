---
phase: 02-verified-single-solution-core-pipeline
plan: 07
subsystem: graph, api, storage
tags: [langgraph, interrupt, clarification, taskiq, postgres]
requires:
  - phase: 02-06
    provides: reviewer and bounded correction loop
provides:
  - clarification_gate node (interrupt) and decide_after_analysis router
  - resume_task_with_clarification worker task, _handle_result_or_pause helper
  - GET/POST /api/v1/tasks/{id}/clarification with atomic 409 guard
  - tasks.clarification_question, tasks.active_execution_seconds columns
affects: [02-08]
tech-stack:
  added: []
  patterns: [zero-logic interrupt gate node, atomic UPDATE ... WHERE status RETURNING guard]
key-files:
  created:
    - migrations/0002_add_clarification_columns.sql
    - tests/graph/test_clarification.py
    - tests/api/test_clarification.py
    - tests/storage/test_clarification_storage.py
  modified:
    - src/algorunner/schemas/task.py
    - src/algorunner/storage/tasks.py
    - src/algorunner/agents/problem_analyzer/node.py
    - src/algorunner/agents/problem_analyzer/prompts.py
    - src/algorunner/graph/routing.py
    - src/algorunner/graph/build.py
    - src/algorunner/graph/state.py
    - src/algorunner/worker/tasks.py
    - src/algorunner/api/routes/tasks.py
key-decisions:
  - "interrupt() lives only in clarification_gate_node so resume never re-runs the Analyzer LLM call"
  - "Round cap enforced in the Analyzer: needs_clarification forced False with assumption_stated after clarification_round_cap"
  - "Resume enqueued only after attempt_consume_clarification returns True"
requirements-completed: [INTAKE-04, INTAKE-05, API-03]
status: complete
duration: 25min
completed: 2026-09-24
actuals:
  tasks: 3
  commits: 3
plan_head_before: 8109a5e75cd33e2014166a93a43173463481c3c1
commits: 3
---

# Phase 2 Plan 07: Clarification pause/resume Summary

Ambiguous problems now pause via LangGraph `interrupt()` in a dedicated gate node, expose the question over GET, and resume the same checkpointed thread via `Command(resume=answer)` on POST, capped at 2 rounds with a stated-assumption fallback and a race-safe atomic 409 guard.

## Tasks

1. Migration + storage helpers (f4d8cd9): idempotent `0002` migration (applied to the shared local Postgres), `TaskRecord` fields, `update_task_clarification`, `attempt_consume_clarification`, `add_active_execution_seconds`, plus storage tests including a 5-way concurrent single-winner test.
2. Gate node, round cap, worker resume (b6c1d84): `clarification_gate_node`, `decide_after_analysis`, Analyzer override + prompt section, `GraphState.clarification_answer`, `_handle_result_or_pause`, `resume_task_with_clarification`, `finalize_success` includes `assumption_stated`. Graph tests cover pause/resume and the round cap (executors mocked).
3. API routes (e175848): GET returns 404 unless awaiting_clarification; POST returns 202 once, 409 otherwise. Tests cover full flow, double POST, and 5 concurrent POSTs (exactly one enqueue).

Full suite: 135 passed before Task 3; API/worker tests pass after.

## Deviations from Plan

**1. [Rule 1 - Bug] Prompt used a non-existent state key.** The plan referenced `state.get("clarification_question")`, which is not a GraphState field. The question is read from the prior `state["analysis"].clarification_question` instead. Files: prompts.py.

**2. [Rule 2 - Missing] Added storage tests** (`tests/storage/test_clarification_storage.py`) for the atomic guard, not listed in the plan's files. Also `resume_task_with_clarification.kiq` is monkeypatched in API tests so no real worker consumes a resume without a checkpoint.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-02-07-01 mitigated by delimiting the answer as data).

## Self-Check: PASSED
