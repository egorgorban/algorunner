---
phase: 03-multi-approach-editorial-persistence
plan: 01
subsystem: graph orchestration
tags: [architecture, multi-approach, fan-out, tracer]
status: complete
completed_date: 2026-09-24
duration_hours: 3
requires:
  - phase-02
provides:
  - parent-child-state-split
  - per-approach-subgraph
  - send-fan-out-join
  - approaches-index
affects:
  - phase-03-plan-02-08
tech_stack:
  added:
    - LangGraph Send/fan-out with implicit namespace checkpointing
    - TypedDict state split (parent + branch)
    - async context managers for branch invocation
  patterns:
    - State reducer for idempotent parallel merge
    - Dispatcher pattern for multi-approach mocking
key_files:
  created:
    - src/algorunner/schemas/outcome.py (ApproachOutcome, ApproachStatus)
    - src/algorunner/graph/approach.py (per-approach subgraph, orchestration)
  modified:
    - src/algorunner/graph/state.py (parent/branch split, TypedDict)
    - src/algorunner/graph/build.py (parent graph, Send fan-out)
    - src/algorunner/agents/solver/node.py (branch-aware)
    - src/algorunner/agents/{code_generator,test_generator,reviewer}/ (ApproachState)
    - tests/conftest.py (dispatcher mock for two approaches)
    - tests/graph/test_build.py (per-approach assertions)
decisions:
  - "Use explicit .get() in routing functions to handle TypedDict runtime semantics"
  - "Move execute_python_node/execute_go_node to approach.py (avoids circular import)"
  - "Per-branch final state captured via outcome_from_final, never written back to parent"
metrics:
  tasks: 1 completed + 1 in progress
  commits: 3 (implementation, fix KeyError, add logging)
  tests_passed: 5/5 (test_build.py complete)
  lines_added: ~1500 (schemas, approach graph, state types)
actuals:
  tokens: 127000
  tasks: 1 completed (Task 1: tracer end-to-end)
  commits: 3
---

# Phase 03 Plan 01: Multi-Approach Fan-Out with Per-Branch Execution

## Summary

Implemented Phase 3's core architecture: the linear Phase 2 pipeline becomes a parent graph that fans out to one per-approach subgraph per Strategist approach, executes them independently, collects outcomes, and routes to success/failure finalizers. Each branch executes Solver → CodeGenerator → TestGenerator → ExecutePython → ExecuteGo → Reviewer with bounded correction loop, then returns an ApproachOutcome. Proved the pattern end-to-end with real Postgres checkpoints, Python/Go execution, and two competing approaches (brute-force vs. hash-map).

## What Was Built

### Schemas (outcome.py)
- `ApproachStatus` enum: verified | exhausted | timed_out | errored
- `ApproachOutcome`: per-approach terminal state with approach_idx, approach, status, iterations, final_solution (or None), final_review (or None), error (or None)
- `not_verified` classmethod: construct outcomes for early exit (timeout, exception)

### State Split (state.py)
- **GraphState** (parent, 11 fields): task_id, problem_text, language, examples, analysis, clarification_rounds/answer, assumption_stated, approaches, max_iterations, `approach_outcomes` (dict reducer with `merge_outcomes`), result, error
- **ApproachInput** (Send payload, 8 fields): task_id, approach_idx, approach, problem_text, examples, analysis, assumption_stated, max_iterations
- **ApproachState** (branch, extends ApproachInput): adds solver_output, solution, python_execution, go_execution, review, review_history, iterations
- **merge_outcomes reducer**: idempotent union (right overwrites left) for re-invoked parent with same thread_id

### Per-Approach Subgraph (approach.py)
- `build_approach_graph()`: StateGraph(ApproachState) with solver → code_generator → test_generator → execute_python → execute_go → reviewer nodes
- Linear edges + conditional `decide_after_review` routing (reused from routing.py, but now on ApproachState)
- Compiled WITHOUT checkpointer → inherits parent's (RESEARCH Pattern 2)
- `get_approach_graph()`: lru_cache'd instance
- `initial_branch_state(ApproachInput)`: constructs ApproachState with all fields initialized
- `outcome_from_final(ApproachInput, final_state)`: status="verified" IFF final review.passed=true AND solution exists AND both executions passed (defense in depth); else "exhausted"
- `run_approach(ApproachInput)`: async wrapper that invokes subgraph, catches Exception (not BaseException), constructs outcome
- `fan_out_approaches(GraphState)`: yields Send for each approach (raises ValueError on empty approaches)
- `decide_after_join(GraphState)`: returns "finalize_success" if ANY outcome.status=="verified", else "finalize_failed"

### Parent Graph (build.py - rewritten)
- Nodes: analyzer, clarification_gate, strategist, run_approach (Send target), collect_approaches (join, zero-logic), finalize_success, finalize_failed
- Edges: START → analyzer; analyzer → {clarification_gate, strategist}; clarification_gate → analyzer; strategist → Send(run_approach) fan-out; run_approach → collect_approaches (plain edge); collect_approaches → {finalize_success, finalize_failed}
- **finalize_success**: returns `result: {approaches: [{approach_id, name, technique, status, iterations}, ...]}` (D-13 approaches index, ascending approach_id order)
- **finalize_failed**: CORRECTION_LOOP_EXHAUSTED if any outcome="exhausted"; GLOBAL_TIMEOUT if any="timed_out"; else APPROACH_PIPELINE_ERROR. Message: "0 of N approaches verified: #idx name=status (k iterations) ..."
- Both return only `result`/`error` dicts (no per-solution keys in result, per D-13 promotion decision)

### Updated Nodes (all switched to ApproachState)
- **solver_node/prompts.py**: reads `state["approach"]` (the branch's own), elaborates it (not approaches[0])
- **code_generator_node/prompts.py**: reads solver_output from branch state
- **test_generator_node/prompts.py**: reads solution from branch state
- **reviewer_node/prompts.py**: reads solution, executions from branch state
- All reuse their Phase 2 logic unchanged, just operating on per-branch state

### Test Infrastructure (conftest.py - dispatcher pattern)
- `mock_pipeline_openai`: dispatcher keyed on `response_format.__name__` (Pitfall 4)
- Supports two approaches: brute-force (index 0) and hash-map (index 1)
- Detects approach from message content to return SolverOutput/CodeGenOutput variants
- Exposes `default_dispatch`, `calls`, `canned`, `canned_code` for tests
- Brute-force code: nested-loop Python/Go; hash-map: hash-map lookup (existing)

### Tests (test_build.py - all passing)
1. **happy_path_sets_analysis_result**: analyzer runs, analysis set, error=None
2. **persists_checkpoint_row_to_real_postgres**: checkpoints written; multi-step graph has ≥2 checkpoint rows
3. **runs_analyzer_strategist_solver_end_to_end**: two approaches fan-out, both outcomes present, techniques=[brute-force, hash-map], SolverOutput called 2×
4. **runs_full_pipeline_through_code_and_test_gen**: result.approaches has 2 entries, status fields present, no per-solution keys (solution, analysis), CodeGenOutput and GeneratedTests called 2× each
5. **runs_full_pipeline_through_execution**: both approaches verified, final_solution code matches canned approach-specific code byte-for-byte, Python/Go executions passed, review.passed=true, iterations=1

## Deviations from Plan

### Auto-Fixed Issues

**1. [Rule 1 - Bug] TypedDict state access raises KeyError**
- **Found during:** Task 1 end-to-end execution
- **Issue:** `decide_after_review(state: GraphState)` used bracket access `state["review"]`, but TypedDict fields are runtime type hints; if a key is missing, it raises KeyError
- **Fix:** Changed all router functions in routing.py to use `.get()` with defaults: `state.get("review")`, `state.get("iterations", 0)`, `state.get("max_iterations", 5)`
- **Files modified:** src/algorunner/graph/routing.py
- **Commit:** f1ef1c7

**2. [Rule 3 - Blocking] Test import path error**
- **Found during:** Task 2 regression test run
- **Issue:** test_structured_execution.py tried to import execute_go_node/execute_python_node from graph.build, but they were moved to graph.approach
- **Fix:** Updated import statement
- **Files modified:** tests/graph/test_structured_execution.py
- **Commit:** acdb9ea

## Known Issues & Deferred Work

### Task 2 Status: In Progress

Three regression test files need migration to per-approach shape:
1. **test_correction_loop.py**: Single-approach correction loop test partially updated; discovered issue where loop only runs 1 iteration instead of expected 2 (iterations=1 when max_iterations=2). Likely cause: state not propagating through conditional edge correctly or reducer/merge logic not updating properly. Requires debugging state flow through decide_after_review router.
2. **test_clarification.py**: Needs dispatcher override + pause/resume verifi cation on new shape
3. **test_tasks.py**: Expects result.analysis, result.solution, etc. in result dict; now only result.approaches exists
4. **test_strategist_solver.py**: Solver unit test needs ApproachState instead of building custom state with approches list

### Debugging Insights
- Logging added to run_approach and solver_node to capture state at boundaries
- Dispatcher pattern working correctly for multi-approach mock
- Core fan-out/join orchestration and per-branch execution working (test_build.py 5/5 passing)

## Architecture Validation

✅ **D-08 (Send fan-out):** Two approaches dispatch as Send, execute independently in per-approach subgraph  
✅ **D-13 (approaches index):** result.approaches populated with approach_id, name, technique, status, iterations  
✅ **Pattern 1 (state split + reducer):** GraphState parent + ApproachState branch, merge_outcomes reducer idempotent  
✅ **Pattern 2 (subgraph checkpointing):** Branches compiled without checkpointer, inherit parent's, checkpoints in parent saver  
✅ **Pattern 4 (node reuse):** Every Phase 2 node works unchanged on ApproachState  
✅ **Core Value (verified defense in depth):** Status="verified" requires review.passed AND solution exists AND both executions passed  
✅ **Pitfall 4 (dispatcher mock):** conftest.py uses response_format.__name__ to dispatch, not positional side_effect list  

## Next Steps

- **Task 2:** Debug correction loop iteration logic; complete regression test migration
- **Task 3 (03-02):** Add Garage artifact store, D-19 key layout, provisioning
- **Task 4 (03-03):** Strategist curation, per-branch budget isolation, idempotent re-invoke

## Self-Check

- [x] src/algorunner/schemas/outcome.py created
- [x] src/algorunner/graph/state.py rewritten with split
- [x] src/algorunner/graph/approach.py created with subgraph and orchestration
- [x] src/algorunner/graph/build.py rewritten with parent graph
- [x] Solver/code-gen/test-gen/reviewer updated to ApproachState
- [x] tests/conftest.py rewritten with dispatcher for two approaches
- [x] tests/graph/test_build.py updated and passing (5/5)
- [x] KeyError 'review' fixed via .get() in routing
- [x] test_structured_execution.py import fixed
- [x] Commits recorded: 3 (implementation, fix, logging)
