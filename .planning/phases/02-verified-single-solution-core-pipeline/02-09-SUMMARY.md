---
phase: 02-verified-single-solution-core-pipeline
plan: 09
subsystem: execution
tags: [structured-tests, entry-point, harness, go, python, type-vocabulary]

requires:
  - phase: 02-verified-single-solution-core-pipeline
    provides: "Plan 02-05 executors (CodeExecutor Protocol, subprocess backends) and Plan 02-04 Code/Test Generator nodes"
provides:
  - "Closed language-neutral type vocabulary (schemas/typespec.py)"
  - "EntryPoint/EntryParam/StructuredCase contracts; Solution.entry_point and Solution.tests as list[StructuredCase]"
  - "Deterministic provided-example parser plus verified LLM normalization (schemas/example_cases.py)"
  - "graph/harness.py renderers for Python and Go, including Go typing and import injection"
  - "Code Generator declares/validates the entry point; Test Generator emits structured cases without seeing the implementation"
affects: ["02-06 (Reviewer can trust executor pass/fail)", "02-07", "Phase 3 editorial"]

actuals:
  tokens: 45000
  tasks: 3
  commits: 5
plan_head_before: 39ed5b5cd7db2be14f266d289b1736aca7aa3846

tech-stack:
  added: []
  patterns:
    - "Language-neutral JSON test cases rendered per language by type-directed literal renderers"
    - "Harness prints ALGORUNNER PASS n/n; execute nodes treat exit 0 without that marker as failure"

key-files:
  created:
    - src/algorunner/schemas/typespec.py
    - src/algorunner/schemas/example_cases.py
    - src/algorunner/graph/harness.py
    - tests/graph/test_structured_format.py
    - tests/graph/test_structured_execution.py
  modified:
    - src/algorunner/schemas/solution.py
    - src/algorunner/graph/build.py
    - src/algorunner/agents/code_generator/node.py
    - src/algorunner/agents/code_generator/prompts.py
    - src/algorunner/agents/test_generator/node.py
    - src/algorunner/agents/test_generator/prompts.py
    - tests/conftest.py
    - tests/agents/test_code_test_gen.py
    - tests/graph/test_build.py
    - tests/tools/test_executors.py

key-decisions:
  - "Provided example labels and example_index are 0-based (label 'provided example N'), matching 'FAIL case N' numbering"
  - "Python literals use ascii() (ASCII-safe repr) so program text is locale-independent"
  - "Python harness catches BaseException per case so SystemExit from generated code is a failure, not a false pass"

requirements-completed: [CODE-01, CODE-02, CODE-03, CODE-04, EXEC-01, EXEC-02]

status: complete
completed: 2026-09-23
---

# Phase 2 Plan 9: Language-aware test format Summary

**The Code Generator now fixes a validated entry point, tests are language-neutral typed JSON cases, and per-language renderers turn them into Python and Go programs that pass through the real executors (real python3 and real go build).**

## Task Commits

1. Task 1 RED `76d16f0`, GREEN `7990b5c`: typespec, EntryPoint/StructuredCase, example converter, renderers
2. Task 2 RED `5a861a2`, GREEN `ed9bdc4`: Code Generator entry point, Test Generator structured cases, execute nodes
3. Task 3 `2753447`: segment-level end-to-end tests (Two Sum with any-order result, normalized prose example, list[str] to str with awkward text, wrong solution failing both languages)

## Verification

`OPENAI_API_KEY=test-dummy uv run pytest tests/ -q` -> 113 passed (was 44). `src/algorunner/tools/` untouched (`git log 76c40a4..HEAD -- src/algorunner/tools` empty). Real go1.26 builds were used; nothing skipped or faked.

## Deviations from Plan

**1. [Rule 2 - Missing critical] Pass-marker guard in execute nodes**
- Generated code calling `exit()` at import time would exit 0 before the harness ran, reporting a false pass. `graph/build.py` now downgrades a passed result lacking the `ALGORUNNER PASS` stdout line. Tools untouched (D-00c).

**2. [Rule 2] Stricter name validation**
- EntryPoint also rejects Python builtin names and Go predeclared identifiers/harness package names (fmt, math, os, reflect, sort) as function names, since these would shadow harness dependencies.

**3. [Note] Python harness catches BaseException** (plan said Exception), so `SystemExit` from a case cannot yield a false pass. Go/Python literals for `unordered_result` use sorted `ascii()`/`%q`-based keys as planned; Go keys are built recursively so nil and empty nested slices compare equal.

**4. [Note] Verification commands** that call `docker compose up` were not run (services already running; instructed by coordinator). Tests ran against the running Postgres.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model; T-02-09-01..04 mitigations are implemented and tested (hostile label escaping, identifier validation, MAX_CASES/MAX_CASE_JSON_CHARS, no vacuous pass).

## Known limitations (backstops from plan)

- Shapes outside the closed vocabulary (trees, linked lists, maps, in-place mutation) fail loudly at Code Generator validation.
- `unordered_result` compares only the top-level list as a multiset.
- Generated expected values are still LLM-computed (oracle independent of implementation, but not proven correct).

## Self-Check: PASSED

Created files exist; commits 76d16f0, 7990b5c, 5a861a2, ed9bdc4, 2753447 present; `git rev-list --count 39ed5b5..HEAD` = 5 before this SUMMARY commit.
