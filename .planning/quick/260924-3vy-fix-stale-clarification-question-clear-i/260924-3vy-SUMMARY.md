---
phase: quick
plan: 260924-3vy
subsystem: storage
tags: [clarification, postgres, bugfix]
status: complete
plan_head_before: 05ef4ce52d919908cfaa79ef683057e3be185e5c
commits: 2
requirements: [INTAKE-05]
key-files:
  modified:
    - src/algorunner/storage/tasks.py
    - tests/storage/test_clarification_storage.py
    - tests/api/test_clarification.py
actuals:
  tasks: 2
  commits: 2
---

# Quick 260924-3vy: Clear stale clarification_question on consume

`attempt_consume_clarification` now sets `clarification_question = NULL` in the same atomic guarded UPDATE, so `GET /api/v1/tasks/{id}` no longer exposes an answered question (including after completion or failure).

## Tasks

1. Tracer: RED (API test `test_get_task_hides_question_after_answer` plus flipped storage assertion failed on the unfixed code), then the SQL fix; GREEN. Commit 5d316ca.
2. Storage regression tests: cleared after completion and failure, second round stores then clears a new question, failed consume leaves the row untouched, concurrent consume has one winner and NULL question. Commit 125cb7d.

## Verification

`tests/storage tests/api tests/worker tests/graph/test_clarification.py`: 29 passed. Changed files are exactly the three planned; no migration, worker, route or schema changes.

## Deviations from Plan

None - plan executed as written.

## Self-Check: PASSED
