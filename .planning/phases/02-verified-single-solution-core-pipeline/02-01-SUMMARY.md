---
phase: 02-verified-single-solution-core-pipeline
plan: 01
subsystem: llm
tags: [openai, tenacity, pydantic, pydantic-settings, structured-outputs]

# Dependency graph
requires:
  - phase: 01-foundation-task-lifecycle-skeleton
    provides: "config.py's Settings/BaseSettings pattern, storage/postgres.py's `get_pool()` construct-from-settings shape that llm/client_factory.py's `get_client()` mirrors"
provides:
  - "All 5 Phase 2 Pydantic contracts (ProblemAnalysis, Approach, Solution, Issue/IssueCategory/Severity, ReviewResult, ExecutionResult, ClarificationQuestion, ClarificationAnswer)"
  - "Settings extended with openai_api_key (required, fails loudly) and every per-agent/reliability field Phase 2 needs"
  - "llm/client_factory.py: get_client() lru_cache'd AsyncOpenAI factory, model_for(agent_name) per-agent model resolution"
  - "llm/retry.py: call_structured() tenacity-wrapped retry helper scoped to APITimeoutError/RateLimitError only"
  - ".env.example with OPENAI_API_KEY wiring"
affects: ["02-02 (Analyzer tracer)", "every subsequent Phase 2 agent node (Strategist, Solver, CodeGen, TestGen, Reviewer)"]

# Actuals (#2632)
actuals:
  tokens: 3250
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: ["openai>=3,<4 (explicit dep, pinned major)", "tenacity (promoted from transitive to explicit dep)"]
  patterns:
    - "lru_cache-based client factory (deliberate deviation from worker/broker.py's bare module-level singleton — cheaper lazy construction, easier per-test monkeypatching)"
    - "Required-secret-no-default Settings field that fails loudly at Settings() construction time (openai_api_key), contrasted with database_url's dev-friendly default"
    - "tenacity retry scoped narrowly by exception type (APITimeoutError/RateLimitError only) — message.parsed is None is explicitly NOT retried by this wrapper"

key-files:
  created:
    - src/algorunner/schemas/problem.py
    - src/algorunner/schemas/solution.py
    - src/algorunner/schemas/review.py
    - src/algorunner/schemas/execution.py
    - src/algorunner/schemas/clarification.py
    - src/algorunner/llm/__init__.py
    - src/algorunner/llm/client_factory.py
    - src/algorunner/llm/retry.py
    - .env.example
    - tests/llm/__init__.py
    - tests/llm/test_client_factory.py
    - tests/llm/test_retry.py
  modified:
    - src/algorunner/config.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "openai pinned explicitly to >=3,<4 in pyproject.toml (uv add alone resolved an unbounded >=3.19.0) — avoids floating across a future major version boundary per RESEARCH.md Version Compatibility guidance"
  - "RED-phase discipline verified manually via pytest -v output, not gsd-tools check tdd-red-evidence — that checker only parses Node.js TAP output, no pytest adapter exists (same precedent recorded in STATE.md from Phase 01-02)"
  - "Test invocations in this session supplied OPENAI_API_KEY as an inline dummy value (never committed, never written to any file) — openai_api_key now has no default, so Settings() construction (and therefore every test file that transitively imports algorunner.config) requires OPENAI_API_KEY present in the environment going forward"

requirements-completed: [ORCH-03, INFRA-03]

coverage:
  - id: D1
    description: "All 5 Phase 2 Pydantic schema files importable, min_length=1 enforced on LLM-facing required string fields"
    verification:
      - kind: other
        ref: "uv run python -c 'from algorunner.schemas.problem import ProblemAnalysis; ...' prints OK"
        status: pass
      - kind: other
        ref: "grep -c min_length=1 problem.py solution.py review.py — non-zero in each"
        status: pass
    human_judgment: false
  - id: D2
    description: "Settings carries every OpenAI/reliability field Phase 2 needs; openai_api_key is required and fails loudly (no default) at construction time"
    verification:
      - kind: other
        ref: "grep -n 'openai_api_key: str$' config.py"
        status: pass
      - kind: other
        ref: "manual: unset OPENAI_API_KEY; uv run python -c 'from algorunner.config import settings' raises pydantic_core.ValidationError (Field required)"
        status: pass
    human_judgment: false
  - id: D3
    description: "get_client() lru_cache identity and model_for() per-agent override/fallback/unknown-agent resolution"
    requirement: ORCH-03
    verification:
      - kind: unit
        ref: "tests/llm/test_client_factory.py#test_get_client_returns_same_instance_on_second_call"
        status: pass
      - kind: unit
        ref: "tests/llm/test_client_factory.py#test_model_for_returns_override_when_set"
        status: pass
      - kind: unit
        ref: "tests/llm/test_client_factory.py#test_model_for_falls_back_to_default_when_override_unset"
        status: pass
      - kind: unit
        ref: "tests/llm/test_client_factory.py#test_model_for_falls_back_to_default_for_unknown_agent"
        status: pass
    human_judgment: false
  - id: D4
    description: "call_structured() retries APITimeoutError/RateLimitError with exponential backoff up to retry_max_attempts, reraises on exhaustion, never retries a non-retryable exception"
    requirement: INFRA-03
    verification:
      - kind: unit
        ref: "tests/llm/test_retry.py#test_call_structured_retries_timeout_then_succeeds"
        status: pass
      - kind: unit
        ref: "tests/llm/test_retry.py#test_call_structured_reraises_original_exception_after_exhausting_retries"
        status: pass
      - kind: unit
        ref: "tests/llm/test_retry.py#test_call_structured_retries_rate_limit_then_succeeds"
        status: pass
      - kind: unit
        ref: "tests/llm/test_retry.py#test_call_structured_does_not_retry_non_retryable_exception"
        status: pass
    human_judgment: false
  - id: D5
    description: ".env.example documents OPENAI_API_KEY alongside DATABASE_URL/REDIS_URL/GARAGE_ENDPOINT"
    verification:
      - kind: other
        ref: "grep -n OPENAI_API_KEY .env.example"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-09-23
status: complete
---

# Phase 2 Plan 1: Contracts, Config, and LLM Client/Retry Layer Summary

**All 5 Phase 2 Pydantic schemas, an OpenAI-required Settings extension, and a tested `llm/` package (get_client, model_for, call_structured) ready for Plan 02-02's Analyzer tracer to call directly.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-09-23T15:25:00Z
- **Completed:** 2026-09-23T16:20:00Z
- **Tasks:** 3 (package-legitimacy checkpoint + 2 TDD tasks)
- **Files modified:** 15 (12 created, 3 modified)

## Accomplishments

- All 5 Phase 2 Pydantic contracts defined (`ProblemAnalysis`, `Approach`/`Solution`, `Issue`/`IssueCategory`/`Severity`/`ReviewResult`, `ExecutionResult`, `ClarificationQuestion`/`ClarificationAnswer`), mirroring `schemas/task.py`'s exact style with `Field(..., min_length=1)` on every LLM-facing required string field
- `Settings` extended with `openai_api_key` (required, no default — fails loudly at construction), `default_model` plus 6 per-agent overrides, `max_iterations`, `clarification_round_cap`, `test_generator_min_tests`, `global_timeout_s`, and 3 retry-tuning fields
- `llm/client_factory.py`: `get_client()` (lru_cache'd `AsyncOpenAI` factory) and `model_for(agent_name)` (per-agent override else `default_model`, never raises on an unknown agent name) — both unit-tested
- `llm/retry.py`: `call_structured()` tenacity-wrapped retry helper, scoped narrowly to `APITimeoutError`/`RateLimitError` (never retries a `message.parsed is None` outcome), bounded by `stop_after_attempt`, `reraise=True` on exhaustion
- `openai>=3,<4` and `tenacity` added as explicit `pyproject.toml` dependencies (openai resolved to 3.19.0; tenacity was already transitively resolved at 9.1.4)
- `.env.example` created (none existed before this plan) documenting `DATABASE_URL`/`REDIS_URL`/`GARAGE_ENDPOINT`/`OPENAI_API_KEY`

## Task Commits

Each TDD task was committed as a RED test commit followed by a GREEN implementation commit:

1. **Task 1 RED:** `e21582e` (test) — failing test for `llm.client_factory` (module doesn't exist yet)
2. **Task 1 GREEN:** `412aa97` (feat) — Phase 2 schemas, Settings extension, `llm/client_factory.py`
3. **Task 2 RED:** `5079b56` (test) — failing tests for `llm.retry` (module doesn't exist yet)
4. **Task 2 GREEN:** `7150701` (feat) — `llm/retry.py` (`call_structured`)

No REFACTOR commits — both implementations were already minimal after GREEN; no obvious cleanup was needed.

**Plan metadata:** committed alongside this SUMMARY.

## TDD Gate Compliance

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| Task 1 (schemas/config/client_factory) | `e21582e` | `412aa97` | — (not needed) | Pass |
| Task 2 (retry wrapper) | `5079b56` | `7150701` | — (not needed) | Pass |

RED-phase evidence for both tasks was `ModuleNotFoundError` (the target module did not exist yet) confirmed via `pytest -v` output — `gsd_run check tdd-red-evidence` was not used because it only parses Node.js TAP output and has no pytest adapter (documented precedent from Phase 01-02, carried forward here rather than re-litigated).

## Files Created/Modified

- `src/algorunner/schemas/problem.py` — `ProblemAnalysis` contract
- `src/algorunner/schemas/solution.py` — `Approach`/`Solution` contracts
- `src/algorunner/schemas/review.py` — `IssueCategory`/`Severity`/`Issue`/`ReviewResult` contracts
- `src/algorunner/schemas/execution.py` — `ExecutionResult` contract (deterministic tool output, no `min_length` — not LLM-produced)
- `src/algorunner/schemas/clarification.py` — `ClarificationQuestion`/`ClarificationAnswer` contracts
- `src/algorunner/config.py` — extended `Settings` with `openai_api_key` + 14 other new fields
- `src/algorunner/llm/__init__.py` — new package
- `src/algorunner/llm/client_factory.py` — `get_client()`, `model_for()`
- `src/algorunner/llm/retry.py` — `call_structured()`
- `.env.example` — new file, documents all 4 env vars the project currently uses
- `pyproject.toml` / `uv.lock` — `openai>=3,<4`, `tenacity` promoted to explicit deps
- `tests/llm/__init__.py`, `tests/llm/test_client_factory.py`, `tests/llm/test_retry.py` — new test package, 8 tests total

## Decisions Made

- Pinned `openai` to `>=3,<4` explicitly rather than leaving `uv add`'s unbounded `>=3.19.0` in place, per RESEARCH.md's explicit warning not to let a major version float silently.
- Followed the codebase's existing `monkeypatch.setattr(<module>.asyncio, "sleep", _no_sleep)` convention (established in `tests/graph/test_build.py`) inside `tests/llm/test_retry.py`'s autouse fixture, so the retry-exhaustion test doesn't actually sleep through tenacity's exponential backoff.
- Task 0's package-legitimacy checkpoint for `openai` was pre-approved by the human coordinator before this execution began (documented in the dispatch prompt — a prior worktree attempt hit this same checkpoint and was approved, then lost to an environment issue before any commit landed). Proceeded straight to Task 1 without re-blocking on it.

## Deviations from Plan

None — plan executed exactly as written. One environment note worth flagging (not a deviation from the plan's instructions, but a consequence of it):

**Side effect of `openai_api_key` having no default:** `Settings()` — and therefore any test file that transitively imports `algorunner.config` — now requires `OPENAI_API_KEY` present in the environment to even collect, let alone run. This plan's own `<verification>` block scopes itself to `tests/llm/` only (not the full suite), which lines up with this: the planner appears to have anticipated the scoping. All test invocations in this session supplied a dummy `OPENAI_API_KEY=sk-test-dummy` inline on the command line (never written to any file, never committed). Confirmed the full existing suite still *collects* successfully under that same dummy key (`uv run pytest --collect-only -q` → 20 tests collected, no import errors), so this plan did not break collection for Phase 1's tests — but anyone running the suite locally without `OPENAI_API_KEY` set will now see every test file fail to import, not just LLM-related ones. Worth surfacing to Phase 2's later plans / CI setup, not something to silently fix here since it's the explicit, intentional behavior the plan's must-have truths asked for.

## Issues Encountered

None.

## User Setup Required

**External service requires manual configuration.** A real `OPENAI_API_KEY` must be set (in `.env` or the environment) before Plan 02-02's Analyzer tracer can make a live OpenAI call. Get one from https://platform.openai.com/api-keys. This plan's own tests use a dummy key and make no real API calls, so no key was needed to execute or verify this plan — but the key is required going forward for anything beyond `tests/llm/`.

## Next Phase Readiness

- Plan 02-02 (Analyzer tracer) can now call `get_client()`, `model_for("problem_analyzer")`, and `call_structured(client, model=..., messages=..., response_format=ProblemAnalysis)` directly — no further plumbing needed.
- `ProblemAnalysis` and all other Phase 2 schemas are importable and ready to be used as `response_format=` arguments.
- Blocker for full end-to-end verification (not this plan's scope): a real `OPENAI_API_KEY` must be supplied before Plan 02-02 can be manually verified against a live OpenAI call.

---
*Phase: 02-verified-single-solution-core-pipeline*
*Completed: 2026-09-23*

## Self-Check: PASSED

All 12 created files confirmed present on disk (`[ -f ]`). All 4 commits (`e21582e`, `412aa97`, `5079b56`, `7150701`) confirmed present in `git log`. `uv run pytest tests/llm/ -q` re-run: 8 passed. Import check re-run: prints `OK`. `git status --short` clean at time of this SUMMARY (before staging SUMMARY.md/REQUIREMENTS.md).
