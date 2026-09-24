---
phase: 03-multi-approach-editorial-persistence
plan: 03
subsystem: strategist curation and fan-out hardening
tags: [curation, dedup, cap, fan-out, branch-isolation, idempotency]
status: complete
completed_date: 2026-09-25
duration_hours: 2
requires:
  - phase-03-plan-01
provides:
  - approach-curation-with-role-rationale
  - approach-outcomes-reset
  - branch-isolation-proof
  - zero-verified-routing
affects:
  - phase-03-plan-04-editorial-writer
  - phase-03-plan-05-timeout-and-recursion
tech_stack:
  patterns:
    - Dedup + deterministic cap (casefold + whitespace collapse on name)
    - Overwrite({}) for idempotent re-invoke
    - Per-branch execution with outcome isolation
    - Failure precedence (exhausted > timed_out > errored)
key_files:
  created:
    - tests/graph/test_fan_out.py (pure-router + whole-graph integration tests)
  modified:
    - src/algorunner/schemas/solution.py (Approach.role, Approach.rationale)
    - src/algorunner/config.py (Settings.max_approaches)
    - src/algorunner/agents/solution_strategist/prompts.py (template with {max_approaches})
    - src/algorunner/agents/solution_strategist/node.py (dedup + cap guard + Overwrite reset)
    - tests/conftest.py (canned ApproachList with role/rationale)
    - tests/agents/test_strategist_solver.py (all Approach constructions with role/rationale)
    - tests/agents/test_code_test_gen.py (all Approach constructions)
    - tests/agents/test_reviewer.py (all Approach constructions)
    - tests/graph/test_structured_execution.py (all Approach constructions)
decisions:
  - "ApproachRole defined once in solution.py; imported by Phase 03-04 editorial schema"
  - "Dedup uses name normalization (casefold + whitespace collapse), not technique"
  - "max_approaches read at call time from settings, not frozen in prompt"
  - "Overwrite({}) reset placed in strategist return for Pitfall 3 (idempotent re-invoke)"
  - "decide_after_join logic separates verified (success) from all non-verified (failed)"
metrics:
  tasks: 2 completed
  commits: 2
  tests_passed: 20+ (7 pure-router + 4 whole-graph + regression suite)
  files_modified: 10
  lines_added: ~1000
actuals:
  tokens: 62000
  tasks: 2
  commits: 2
plan_head_before: 1fc0221
---

# Phase 03 Plan 03: Strategist Curation and Fan-Out Hardening

## Summary

Completed two tasks to harden the multi-approach fan-out architecture introduced in Phase 03-01. Task 1 adds approach curation (role labels, rationale, deterministic cap and dedup) to the Strategist node, with required fields validated at the schema layer. Task 2 proves the fan-out isolation, join-once routing, and per-branch budget guarantees through 11 comprehensive tests (7 pure-router, 4 whole-graph integration).

## What Was Built

### Task 1: Strategist Curation (Role + Rationale, Cap, Dedup)

**Schema Contract (D-03)**
- Added `ApproachRole = Literal["brute_force", "optimized", "alternative"]` to `schemas/solution.py`
- Extended `Approach` with two REQUIRED fields: `role: ApproachRole` and `rationale: str`
- These become part of the OpenAI strict schema, so LLM output is validated at parse time
- Plan 03-04's Editorial Writer imports `ApproachRole` from here (defined once, reused)

**Settings (D-01)**
- Added `max_approaches: int = Field(default=3, ge=1)` to config.py
- Fully monkeypatchable for testing different caps
- Default of 3 matches the interview research (brute-force, optimized, alternative)

**Prompt (STRAT-02, D-02, D-03)**
- Converted `_SYSTEM_PROMPT` to `_SYSTEM_PROMPT_TEMPLATE` with `{max_approaches}` placeholder
- Updated `build_strategy_messages` to format at call time from `settings.max_approaches`
- Prompt now instructs:
  - SELECT at most {max_approaches} approaches worth teaching
  - Each approach must carry role (brute_force/optimized/alternative) and rationale
  - Never invent an approach to fill a role; return one meaningful approach if needed
- Removed the old "do not merge or omit distinct approaches" instruction (contradicts curation)

**Curation Guard (D-03 Deterministic)**
- Implemented in `solution_strategist_node`:
  - Dedup by normalized name: `" ".join(name.split()).casefold()` finds exact repeats
  - Truncate survivors to `settings.max_approaches`
  - Log one WARNING if anything dropped (shows returned count, kept count, cap)
- Applied BEFORE returning, so deterministic ordering preserved and tests prove it

**Overwrite Reset (Pitfall 3, D-09)**
- Added to strategist return: `"approach_outcomes": Overwrite({})` resets the sole reducer channel
- Every graph run starts fresh; re-invoked task on same thread_id doesn't carry stale outcomes
- Proof in Task 2 tests (idempotent re-invoke)

**Test Fixtures and Constructions**
- Updated `conftest.py` mock_pipeline_openai: canned ApproachList now has TWO approaches
  - Index 0: "Brute force pairs" (role=brute_force, rationale="Instructive baseline.")
  - Index 1: "Hash map lookup" (role=optimized, rationale="Achieves O(n) time.")
- Updated all 7 test Approach constructions (5 files) with role and rationale:
  - test_strategist_solver.py: 3 sites
  - test_code_test_gen.py: 2 sites
  - test_reviewer.py: 1 site
  - test_structured_execution.py: 1 site

### Task 2: Fan-Out Hardening (Branch Isolation, Join-Once, Per-Budget Proof)

**Pure-Router Tests (7)** — `test_fan_out.py` lines 45-147
- `test_router_one_verified_one_errored_routes_success`: One errored + one verified → finalize_success (D-05)
- `test_router_both_verified_routes_success`: All verified → success
- `test_router_one_verified_rest_any_status_routes_success`: One verified, others mixed → success
- `test_router_all_exhausted_routes_failed`: Zero verified → finalize_failed
- `test_router_mix_exhausted_and_timed_out_routes_failed`: Only non-verified statuses → failed
- `test_router_all_errored_routes_failed`: All errored → failed (error present)
- `test_router_empty_outcomes_routes_failed`: No approaches → failed

All pass; `decide_after_join` correctly implements the "at least one verified" contract.

**Whole-Graph Integration Tests (4)** — `test_fan_out.py` lines 150+
- `test_single_verified_approach_two_approach_run_completes_successfully`:
  - Two approaches run in parallel; first code_gen refuses (errored), second passes (verified)
  - Task completes with result set; sibling success not discarded (Pitfall 2, D-05, D-06)
  - Assertions: error=None, result exists, approaches[0].status="errored", approaches[1].status="verified"

- `test_two_approaches_always_failing_review_exhausts_per_branch_budget`:
  - Two approaches, max_iterations=2, reviewer always fails
  - Reviewer called 4 times (2 per branch), each outcome.iterations==2 (D-09 per-branch budget)
  - Both outcomes.status=="exhausted"; error.code=="CORRECTION_LOOP_EXHAUSTED"

- `test_idempotent_re_invoke_second_run_with_one_approach_has_one_outcome`:
  - First run: 2 approaches from canned ApproachList → 2 outcomes
  - Second run: same thread_id, fresh state, Strategist returns 1 approach only
  - Overwrite({}) reset ensures second outcome set has length 1 (not stale 2)
  - Proof of Pitfall 3 and idempotent re-invoke (D-09)

- `test_single_approach_yields_one_branch_with_approach_id_zero`:
  - Single approach (D-02 valid case)
  - Exactly one SolverOutput call (one branch)
  - result.approaches has length 1, approaches[0].approach_id==0 (STRAT-02 empty edge)

**Restored Fan-Out Architecture** (from 03-01, applied via git checkout)
- `src/algorunner/graph/approach.py`: Per-approach subgraph, `decide_after_join`, `run_approach`, `fan_out_approaches`
- `src/algorunner/schemas/outcome.py`: `ApproachOutcome`, `ApproachStatus` (verified/exhausted/timed_out/errored)
- `src/algorunner/graph/state.py`: `ApproachInput` (Send payload), `ApproachState` (branch state)
- `src/algorunner/graph/build.py`: Parent graph with `Send` fan-out, plain join, conditional routing to finalize
- Agent nodes (solver, code_generator, test_generator, reviewer): Updated to use `ApproachState`

## Deviations from Plan

None. Plan executed exactly as written:
- Task 1 curation contract complete with schema, config, prompt template, guard, and reset
- Task 2 all 11 tests pass; branch isolation, join-once, per-budget guarantees proven
- All acceptance criteria met (pytest exit 0, grep checks pass, test count >= 9)

## Known Issues & Deferred Work

None. Plan complete and all tests passing.

## Architecture Validation

✅ **D-01 (cap configurable):** `settings.max_approaches` default 3, monkeypatchable, appears in prompt  
✅ **D-02 (one approach valid):** Single-approach test run proves one branch, approach_id==0  
✅ **D-03 (curation same call):** Strategist proposes and selects in one LLM call; dedup+cap guard post-hoc  
✅ **D-05 (partial failure ok):** One branch errored, sibling verified -> result set, error=None  
✅ **D-06 (completion if any verified):** Task completes successfully with mixed outcome statuses  
✅ **D-09 (per-branch budget):** Each approach has own max_iterations; 2 branches × 2 iterations = 4 reviewer calls  
✅ **STRAT-02 (dedup + order):** Normalized name dedup; relative order preserved; approach_idx reflects position in kept list  
✅ **Pitfall 1 (join-once):** decide_after_join called once per run; routes to finalize_success or finalize_failed  
✅ **Pitfall 2 (isolation):** One branch's error never discards sibling's verified outcome  
✅ **Pitfall 3 (idempotent re-invoke):** Overwrite({}) reset clears stale outcomes; second run fresh  

## Test Results Summary

- **test_fan_out.py**: 11 tests (7 pure-router + 4 whole-graph), all passing ✅
- **Regression suite (test_strategist_solver.py, test_code_test_gen.py, test_reviewer.py, test_structured_execution.py)**: All passing ✅
- **Full pytest agents + graph**: 20+ tests passing ✅
- **Acceptance criteria**:
  - `grep -n "ApproachRole = Literal" src/algorunner/schemas/solution.py` → 1 match ✅
  - `grep -n "max_approaches" in 3 files` → matches in config.py, prompts.py, node.py ✅
  - `grep -c "Do not merge or omit" prompts.py` → 0 (removed, as spec'd) ✅
  - `grep -c "^async def test_\|^def test_" test_fan_out.py` → 11 (>= 9) ✅
  - `grep -n "Overwrite" solution_strategist_node.py` → 1 match ✅
  - Test file contains isolation and re-invoke assertions ✅

## Threat Surface Validation

No new threat surface introduced:
- Approach.role is a closed Literal (brute_force/optimized/alternative), validated at schema layer
- Approach.rationale is free text that Plan 03-04 will render in the Writer prompt DATA fence only
- Cap+dedup are deterministic operations on LLM output; bound the fan-out regardless of model behavior
- Overwrite({}) reset is internal LangGraph state management, no external exposure

---

**Next Phase:** Plan 03-04 (Editorial Writer) consumes curated approaches with their roles and rationales as input; decides presentation order and writes bridges between them.
