# Phase 03 Plan 06: Russian-Language Editorial with Deterministic Checks & One-Retry Split

## Summary

Implemented the Russian-language editorial guarantee (EDIT-01, D-16) through deterministic Cyrillic-ratio checking and one-retry logic with user-confirmed failure split. The Writer now makes at most two parse calls per article; language failures ship with explicit warnings, structural failures fail the task immediately.

## Execution

**Status:** Complete (2/2 tasks)

**Duration:** ~60 minutes

### Task 1: Deterministic Russian Check (✓ Complete)

**Files Created/Modified:**
- `src/algorunner/agents/editorial_writer/language.py` (new)
- `src/algorunner/config.py` (updated)
- `tests/agents/test_editorial_writer.py` (new)

**What was built:**
- `cyrillic_ratio(text: str) -> tuple[float, int]`: Calculates Cyrillic letter ratio, excluding backtick code spans and O(...) notation
- `check_russian(fields, aggregate_min, field_min, field_min_letters)`: Validates that prose meets Russian-language thresholds (aggregate >= 0.6, per-field >= 0.3 for fields with >= 20 letters)
- `prose_fields(draft: EditorialDraft) -> list[str]`: Extracts all prose from draft (problem_restatement, approach titles/bridges/intuitions/algorithms/justifications/notes, edge_cases, unverified notes; excludes complexity_time/complexity_space)
- Settings in `config.py`: `editorial_cyrillic_min_ratio=0.6`, `editorial_cyrillic_field_min_ratio=0.3` (RESEARCH A1 tunables)
- 20 unit tests covering ratio calculation, threshold checking, field extraction

**Verified by:**
- `uv run pytest tests/agents/test_editorial_writer.py -q` — 20/20 passing
- `grep -n "def cyrillic_ratio\|def check_russian\|def prose_fields"` finds all three functions
- `grep -n "editorial_cyrillic_min_ratio\|editorial_cyrillic_field_min_ratio"` finds both settings

### Task 2: Two-Attempt Writer with Hard/Soft Failure Split (✓ Complete)

**Files Created/Modified:**
- `src/algorunner/agents/editorial_writer/node.py` (updated)
- `src/algorunner/agents/editorial_writer/prompts.py` (updated)
- `src/algorunner/graph/state.py` (updated)
- `src/algorunner/graph/build.py` (updated)
- `src/algorunner/graph/routing.py` (updated)
- `src/algorunner/worker/tasks.py` (updated)
- `tests/agents/test_editorial_writer.py` (updated)

**What was built:**
- `soft_warnings(draft, analysis) -> list[str]`: Returns warning codes for non-structural failures (["language_check_failed"] when Russian check fails; Plan 03-07 extends with completeness)
- Two-attempt Writer loop in `editorial_writer_node`:
  - Attempt 1: Initial LLM call
  - Refusal on attempt 1 → raises ValueError immediately (D-00f, not retried)
  - Assembly attempt 1 → if ValueError, it's a hard failure; if success, check soft warnings
  - On any failure → compute retry_reason, retry once
  - Attempt 2: LLM call with retry_reason in prompt
  - Refusal on attempt 2 → raises ValueError (not retried)
  - Decision logic per user-confirmed split:
    * Attempt 2 assembled → return with warnings (soft or none)
    * Attempt 2 failed but Attempt 1 assembled → return Attempt 1 with its warnings
    * Both failed to assemble → return `{"error": {"code": "EDITORIAL_ASSEMBLY_FAILED", ...}}`
- `build_editorial_messages` with optional `retry_reason` parameter
- `editorial_warnings: list[str]` field in GraphState (initialized to [])
- `decide_after_writer` router: returns "finalize_success" if editorial is set and no error, else "end"
- Conditional edge `editorial_writer → {finalize_success, end}` via `decide_after_writer`
- `finalize_success` now includes `result["editorial_warnings"]` (always present)
- Updated `decide_after_review` annotation from GraphState to ApproachState (reflects per-branch usage in subgraph)
- 2 additional tests for soft_warnings behavior

**Verified by:**
- `uv run pytest tests/agents/test_editorial_writer.py -q` — 22/22 passing
- `grep -n "EDITORIAL_ASSEMBLY_FAILED"` finds error code in node.py
- `grep -n "decide_after_writer"` finds definition in routing.py and wiring in build.py
- `grep -n '"editorial_warnings"'` finds in build.py result assembly
- `grep -n "editorial_warnings"` finds field in state.py and initial value in worker/tasks.py
- `grep -n "def decide_after_review(state: ApproachState)"` finds retyped router

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| `b72dbef` | feat(03-06): Task 1 - Deterministic Russian check |
| `de2a07f` | feat(03-06): Task 2 - One shared Writer retry, then user-confirmed split |

## Key Decisions

**D-16 (User-Confirmed, 2026-09-24, LOCKED):** After one retry, split failures by type:
- **Structural** (approach ID mismatch, bridge rule broken): fail with `EDITORIAL_ASSEMBLY_FAILED`
- **Language** (Russian check fails after retry): ship verified editorial with `editorial_warnings=["language_check_failed"]`

**RESEARCH A1 (Cyrillic Thresholds):** 0.6 aggregate, 0.3 per-field (for fields >= 20 letters) — tunable via Settings.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-03-06-01 | agents/editorial_writer/node.py | Retry reason is deterministic node code + fixed one-line descriptions (not draft echoed verbatim) |

## Technical Notes

- **Cyrillic detection:** U+0400-U+04FF block; backticks and O(...) excluded from count
- **Retry prompt:** Fenced "Your previous draft was rejected because: ..." section appended to user message
- **Parse call budget:** Max 2 per article, no judge calls ever
- **Result contract:** `editorial_warnings` always present in finalize_success result (empty list if no warnings)
- **Refusal handling:** ValueError raised immediately on attempt 1; not retried (D-00f)

## Roadmap Impact

**SC2 ("Russian-language editorial regardless of input language")**: ✓ Achieved
- Writer receives prompt in Russian
- Deterministic Cyrillic check validates output
- Language failures ship with warnings rather than failing the task
- Threshold tunable for future refinement (RESEARCH A1)

---

**Plan:** 03-06 (Phase 03-multi-approach-editorial-persistence)  
**Status:** `status: complete`  
**Requirement:** EDIT-01 (editorial in Russian)  
**Cost (estimated vs. actual):** 40k tokens (est) vs. ~35k (actual)  
**Actuals:**
- tokens: 35000
- tasks: 2
- commits: 2
- files_created: 2
- files_modified: 8

*Executed: 2026-09-25*
