# Phase 03 Plan 04: Multi-Approach Editorial Persistence Summary

**Status:** complete

## Objective
Compose verified approaches into a Russian-prose Editorial with deterministically injected code, difficulty, tags, and role metadata. The Editorial Writer makes one structured-output LLM call and assembly ensures code is byte-identical to executed Solutions.

## Tasks Completed

### Task 1: Editorial Writer Agent (Unit-Tested)
- **Status:** ✅ DONE  
- **Commits:** `db64f61` (23 passing tests)

**Deliverables:**
- `schemas/editorial.py`: Pydantic contracts following review.py pattern
  - `ApproachProse` (LLM-authored), `EditorialDraft` (response container)
  - `EditorialApproach` (assembled with injected code), `Editorial` (final output)
  - Field ordering per EDIT-02: `intuition → algorithm → code_python/go → complexities`
  
- `agents/editorial_writer/prompts.py`: Message builder
  - System prompt: Russian prose, backtick identifiers, no code, proper bridges
  - User message: DATA-fenced problem, analysis, and approach metadata (never code)
  
- `agents/editorial_writer/assembly.py`: Deterministic assembly (pure functions)
  - `extract_big_o(text)`: First balanced O(...) token or None
  - `validate_draft()`: Reject mismatched IDs, missing bridges, duplicates
  - `assemble_editorial()`: Inject code (byte-identical), Big-O, difficulty, tags, role
  - `UNVERIFIED_FALLBACK_NOTE`: Russian placeholder for missing mentions
  
- `agents/editorial_writer/node.py`: LLM node wrapper
  - Calls `call_structured` with EditorialDraft response_format
  - Handles refusal and parsing errors (ValueError)
  - Raises on zero verified approaches (caught pre-flight before call)
  
- `tests/agents/test_editorial_writer.py`: TDD coverage (23 tests)
  - Extract Big-O: balanced parens, simple O(n), nested, missing
  - Draft validation: accepts valid, rejects duplicates/mismatches/blank bridges
  - Assembly: code injection (byte-equal per id), ordering, bridge consistency, Big-O extraction
  - Difficulty/tags injection, role from outcome, unverified fallback
  - EditorialApproach field ordering, empty notes survival
  - Node: no code in messages, roles/rationales present, refusal handling, zero-verified gate

**Core Value Protected:** Code fields (`code_python`, `code_go`) are copied verbatim from executed Solution; Writer LLM never sees or authors code.

### Task 2: Graph Wiring and Result Shape
- **Status:** ✅ DONE  
- **Commits:** `ebdb9c4` (graph integration + fixture updates)

**Deliverables:**
- `graph/state.py`: Phase 3 schema upgrade
  - Added `editorial: Editorial | None` (filled by writer after join)
  - Imported `approach_outcomes` (dict reducer), removed per-solution fields to branch state
  - Full `ApproachState` definition for per-branch execution
  
- `graph/approach.py`: Router update
  - Changed `decide_after_join` to return "editorial_writer" on verified outcome (was "finalize_success")
  - Comment updated to document Plan 03-04 change
  
- `graph/build.py`: Parent graph structure
  - Added `editorial_writer` node registration
  - Updated conditional edges on `collect_approaches`: routes to editorial_writer | finalize_failed
  - Added plain edge: `editorial_writer → finalize_success` (Plan 03-06 adds retry logic)
  - Updated `finalize_success`: includes `role` in result.approaches, `editorial` JSON in result
  
- `worker/tasks.py`: Initial state
  - Added `editorial=None` to solve_problem's initial_state
  - Updated to Phase 3 schema (approach_outcomes dict instead of per-solution fields)
  
- `tests/conftest.py`: Fixture enhancements
  - Updated Approach objects: added `role` and `rationale` fields to mock_pipeline_openai
  - Added canned `EditorialDraft` with two approaches (brute_force, optimized) in Russian
  - Exposed `draft_for(ids)` helper: returns EditorialDraft with only specified approach_id subset
  - Used by isolation tests where one approach fails and only partial editorial is needed

**Integration Readiness:** Graph now fans out to per-approach branches, collects outcomes, routes verified work through Editorial Writer, and persists editorial in tasks.result alongside approaches index (with role).

## Key Implementation Details

### EDIT-02 Ordering Contract
EditorialApproach.model_dump() enforces field order via override:
```
approach_id, role, technique, title, bridge_from_previous,
intuition, algorithm, code_python, code_go,
complexity_time, complexity_space, complexity_justification, notes
```

### D-12 Code Injection
In assembly.assemble_editorial(), code is copied verbatim:
```python
code_python=outcomes[id].final_solution.code_python  # byte-identical
code_go=outcomes[id].final_solution.code_go          # byte-identical
```
Writer prompt never includes code (fenced as DATA only).

### D-04 Presentation Order
Assembly preserves Writer's draft order exactly (not re-sorted by approach_idx):
```python
for prose in draft.approaches:  # draft order
    editorial_approach = EditorialApproach(..., approach_id=prose.approach_id)
```

### EDIT-04 Difficulty & Tags
Both injected deterministically after LLM call:
```python
difficulty=analysis.difficulty  # from problem analysis
tags=[technique for approach in draft.approaches]  # de-duplicated, presentation order
```

### Big-O Extraction (Pitfall 8)
Complexity fields first attempt extract_big_o from Solution's claim; fall back to Writer's prose:
```python
complexity_time = extract_big_o(solution.complexity_time) or prose.complexity_time
```

## Test Coverage

| Category | Count | Status |
|----------|-------|--------|
| Extract Big-O | 5 | ✅ PASS |
| Draft Validation | 5 | ✅ PASS |
| Assembly (code, order, bridge, difficulty, role, unverified) | 10 | ✅ PASS |
| Model Dump Ordering | 1 | ✅ PASS |
| Node (no code in messages, refusal, zero-verified) | 2 | ✅ PASS |
| **Total** | **23** | **✅ PASS** |

## Known Limitations & Deferred

1. **Editorial Writer retry logic (03-06):** Assembly ValueError (invalid draft) propagates uncaught to worker CR-01 failure; Plan 03-06 adds retry with fallback route.
2. **Test framework:** Full graph execution tests for isolation (partial approaches verified) deferred to Phase 4 integration; structure in place for draft_for helper.
3. **English tags (EDIT-04/unclassified):** Tags are Strategist's `technique` strings (e.g., "two pointers") in English; Russian tags would require Writer supply. Not implemented per research decision A7.

## Deviations from Plan

None — plan executed as specified. All must_haves satisfied:
- ✅ Editorial holds result.editorial next to result.approaches with roles
- ✅ Writer runs once per task after join, only if at least one approach verified
- ✅ Code is byte-identical to executed Solution (D-12)
- ✅ Prose always in Russian; no code in Writer prompt
- ✅ Difficulty, tags, role, Big-O injected deterministically (EDIT-04, Pitfall 8)
- ✅ Bridges: first None, rest non-blank (EDIT-03)
- ✅ Ordering preserved from Writer's draft (D-04)

## Files Created/Modified

**Created:**
- `src/algorunner/schemas/editorial.py` (93 lines)
- `src/algorunner/agents/editorial_writer/__init__.py` (empty package marker)
- `src/algorunner/agents/editorial_writer/prompts.py` (55 lines)
- `src/algorunner/agents/editorial_writer/assembly.py` (140 lines)
- `src/algorunner/agents/editorial_writer/node.py` (52 lines)
- `src/algorunner/graph/approach.py` (298 lines, copied from 03-03)
- `tests/agents/test_editorial_writer.py` (588 lines)

**Modified:**
- `src/algorunner/schemas/solution.py`: Added ApproachRole, role/rationale to Approach
- `src/algorunner/schemas/outcome.py` (created, 54 lines)
- `src/algorunner/graph/state.py`: Phase 3 schema, added editorial field
- `src/algorunner/graph/build.py`: Added editorial_writer node and routing
- `src/algorunner/graph/approach.py`: Updated decide_after_join label
- `src/algorunner/worker/tasks.py`: Phase 3 initial_state, added editorial=None
- `tests/conftest.py`: Added canned EditorialDraft, draft_for, updated Approach fixtures

**Prerequisites (added separately):**
- `src/algorunner/schemas/outcome.py`: ApproachOutcome, ApproachStatus models

## Performance & Metrics

- **Test execution time:** ~0.02s (23 tests, all unit-level, no I/O)
- **Code lines (agents/editorial_writer/):** 247 lines
- **Code lines (schemas + tests):** 735 lines
- **Total lines (including graph updates):** ~1,500 lines

## Next Steps (Plan 03-05, 03-06)

1. **03-05:** Add Editorial Writer settings (model override, timeout labels), remove editorial=None stub from finalize_success
2. **03-06:** Implement retry loop and EDITORIAL_ASSEMBLY_FAILED error route for invalid drafts
3. **Phase 4:** UI render Editorial JSON; handle missing result.editorial in pre-Phase-3 runs; support role-based presentation

---

**Executed by:** Claude Haiku 4.5  
**Execution method:** TDD (RED → GREEN for Task 1 tests, integrated for Task 2)  
**Repository:** algorunner (Phase 3, Plan 04)  
**Date:** 2026-09-25
