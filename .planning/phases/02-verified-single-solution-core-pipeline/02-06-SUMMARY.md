---
phase: 02-verified-single-solution-core-pipeline
plan: 06
subsystem: review
tags: [reviewer, correction-loop, langgraph, routing, max-iterations]

requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Executors and structured-test harness (02-05, 02-09); Solver/CodeGen/TestGen nodes (02-03, 02-04)"
provides:
  - "reviewer_node with deterministic execution-failure short-circuit (no LLM on failed execution)"
  - "decide_after_review pure bounded router (D-05 category to node table, solver-first priority)"
  - "Correction loop wired into build_pipeline_graph with finalize_failed terminal (CORRECTION_LOOP_EXHAUSTED)"
  - "Full review_history section in solver/code_generator/test_generator prompts (D-06)"
affects: ["02-07", "Phase 3 editorial"]

actuals:
  tokens: 30000
  tasks: 3
  commits: 3
plan_head_before: f59b94cd1874d43e84f908c85bde0d0db9b3929f

tech-stack:
  added: []
  patterns:
    - "Verdict that cannot be produced by the LLM when execution failed: synthesized deterministically"
    - "iterations incremented exactly once per reviewer_node call; router terminates at >= max_iterations"

key-files:
  created:
    - src/algorunner/agents/reviewer/__init__.py
    - src/algorunner/agents/reviewer/node.py
    - src/algorunner/agents/reviewer/prompts.py
    - src/algorunner/graph/routing.py
    - tests/agents/test_reviewer.py
    - tests/graph/test_correction_loop.py
  modified:
    - src/algorunner/graph/build.py
    - src/algorunner/agents/solver/prompts.py
    - src/algorunner/agents/code_generator/prompts.py
    - src/algorunner/agents/test_generator/prompts.py
    - tests/conftest.py
    - tests/graph/test_build.py

key-decisions:
  - "format_review_history lives in reviewer/prompts.py and is imported by the three upstream prompt modules, so the history framing is defined once"
  - "decide_after_review treats state['review'] is None as finalize_failed (never success without a structured verdict)"

requirements-completed: [REV-01, REV-02, REV-03, REV-04, REV-05]

status: complete
completed: 2026-09-24
---

# Phase 2 Plan 6: Reviewer and bounded correction loop Summary

**A Reviewer that never lets an LLM override a real Python/Go execution failure, plus a pure `decide_after_review` router that sends critical issues back to the Solver or Code Generator with full prior-attempt history and ends in a clean `CORRECTION_LOOP_EXHAUSTED` failure at `max_iterations`.**

## Task Commits

1. Task 1 `16eeea9`: reviewer node, prompts, tests (failure short-circuit for each language and for absent results, passing path, minor issues do not block, refusal raises)
2. Task 2 `c9c07a2`: `decide_after_review` and routing tests (boundary at exactly max_iterations, category mapping, solver priority)
3. Task 3 `767f904`: graph wiring, `finalize_failed`, review_history in three prompts, `mock_pipeline_openai` extended with a sixth (Reviewer) response, whole-graph exhaustion test

## Verification

`OPENAI_API_KEY=test-dummy uv run pytest tests/ -q` -> 129 passed (was 113), with real Postgres, real python3 and real `go build`. The whole-graph test runs with `max_iterations=2` and an always-failing Reviewer: it ends with `error.code == "CORRECTION_LOOP_EXHAUSTED"`, no GraphRecursionError, the Solver called more than once, two review_history entries, and "Attempt 1" present in the second Solver prompt only. The happy-path graph test now also asserts `result["review"]["passed"]` and one iteration.

## Deviations from Plan

**1. [Rule 2 - Missing critical] Missing review is never success**
- `decide_after_review` returns `finalize_failed` when `state["review"]` is None (plan's body would raise on `.passed`), honoring the prohibition on treating an absent verification signal as success.

**2. [Note] Docker step skipped**: `docker compose up` not run (services already running, per coordinator). Tests ran against the running Postgres.

**3. [Note] Test dispatch**: the whole-graph test replaces the fixture's ordered side_effect with a dispatcher keyed by `response_format`, since the loop re-calls nodes a variable number of times.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-06-01 (data-delimited solution and history) and T-02-06-02 (bounded loop, unit and integration tested) are implemented.

## Self-Check: PASSED

Created files exist; commits 16eeea9, c9c07a2, 767f904 present; `git rev-list --count f59b94c..HEAD` = 3 before this SUMMARY commit.
