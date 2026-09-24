---
phase: 02-verified-single-solution-core-pipeline
verified: 2026-09-24T18:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - .planning/REQUIREMENTS.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-01-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-01-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-02-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-02-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-03-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-03-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-04-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-04-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-05-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-05-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-06-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-06-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-07-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-07-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-08-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-08-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-09-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-09-SUMMARY.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-10-PLAN.md
  - .planning/phases/02-verified-single-solution-core-pipeline/02-10-SUMMARY.md
  - docker-compose.yml
  - docker/Dockerfile.worker
  - scripts/verify_executor_isolation.py
  - src/algorunner/agents/reviewer/node.py
  - src/algorunner/api/routes/tasks.py
  - src/algorunner/graph/build.py
  - src/algorunner/graph/harness.py
  - src/algorunner/graph/routing.py
  - src/algorunner/storage/tasks.py
  - src/algorunner/tools/go_executor/subprocess_backend.py
  - src/algorunner/tools/process.py
  - src/algorunner/tools/python_executor/subprocess_backend.py
  - src/algorunner/worker/tasks.py
covered_digest: "v1:sha256:968480d8a4fa066eb892ae8e48ff5113864b88d0551c64d0b2b45e63b841b73c"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  gaps_closed:
    - "Human item 1: live ambiguous-problem clarification run (02-UAT.md, passed with a real model)"
    - "Human item 2: CR-01 and CR-02 hardened in code (plan 02-10, quick 260924-53g), user-verified in Docker"
    - "Human item 3: literal Two Sum live run (02-UAT.md, passed)"
  gaps_remaining: []
  regressions: []
---

# Phase 2: Verified Single-Solution Core Pipeline Verification Report

**Phase Goal:** A submitted problem is actually analyzed and solved by the AI pipeline, producing one algorithm approach whose Python and Go code are proven correct by real execution, with clarification and correction handled automatically.
**Verified:** 2026-09-24
**Status:** passed
**Re-verification:** Yes. The first report's digest went stale after plan 02-10 and the quick fixes 260924-53g, 260924-3vy and 260923-q5h landed.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Analyzer extracts constraints and intent from EN/RU text, assigns difficulty, and moves to `awaiting_clarification` when ambiguous | VERIFIED | Unchanged graph wiring (`graph/build.py`, `graph/routing.py`) with `clarification_gate` using `interrupt()`. The live ambiguous-problem run in 02-UAT.md observed a real model choosing `needs_clarification`. The suite includes the clarification tests, which pass. |
| 2 | `POST /api/v1/tasks/{id}/clarification` resumes from the checkpointed state, not a restart | VERIFIED | `api/routes/tasks.py` calls `attempt_consume_clarification` (atomic compare-and-set), returns 409 if not consumed, then `resume_task_with_clarification.kiq`. Re-read `storage/tasks.py`: the single UPDATE now also sets `clarification_question = NULL` (quick 3vy), so a stale question is never served after resume. Live resume passed (02-UAT.md). |
| 3 | Generic Solver elaborates a tagged approach into Python and Go plus generated tests, using examples and adding edge cases | VERIFIED | Strategist, Solver, Code Generator and Test Generator wiring unchanged. `Example.explanation` is now nullable (quick q5h). Live Two Sum run produced genuine implementations. |
| 4 | Python and Go are actually executed via swappable executors with structured pass/fail, and the Reviewer produces a structured ReviewResult with justified complexity | VERIFIED | Both executors were re-read in full. They still implement the `CodeExecutor` Protocol and return structured `ExecutionResult`. They now go through `tools/process.run_in_process_group`. 200 tests pass, including real python3 and go build runs, plus uvloop-based executor tests. Live Two Sum run: python_execution, go_execution and review all passed (02-UAT.md). |
| 5 | Failing review routes to a bounded correction loop with prior context ending in success or clean FAILED, with backoff retries and a global timeout | VERIFIED | Routing and budget code unchanged and covered by tests that pass. Global-timeout cancellation now also kills executor children (CR-02 closed, below), so INFRA-04 no longer leaks processes. |

**Score:** 5/5 truths verified (0 behavior-unverified)

### CR-01 and CR-02 closure check (read from current code)

| Item | Evidence in code | Status |
|------|------------------|--------|
| CR-01 privilege drop | `tools/process.py::make_preexec_fn`: when euid is 0, returns `_drop_then_limit`, which runs `os.setgroups([])`, `os.setgid(65534)`, `os.setuid(65534)` and only then `limit_fn()`. Groups and gid are changed while still root, and setuid is last, so a failure at any step aborts the spawn and can never yield a root exec. The rlimits, including `RLIMIT_NPROC=0`, run after setuid as the code comment requires. | CLOSED |
| Identity via preexec, not spawn kwargs (uvloop) | `run_in_process_group` passes only `preexec_fn`, `start_new_session=True`, `cwd` and `env`. `tests/tools/test_executor_uvloop.py` (real uvloop) and `test_no_source_passes_identity_kwargs_to_subprocess_spawn` guard against regression. | CLOSED |
| Workdir ownership | `prepare_workdir` chowns the fully populated tree (no symlink following) once, before any child. Both executors call it. | CLOSED |
| Fail-closed flag | `ALGORUNNER_REQUIRE_PRIVILEGE_DROP=1` is set at `docker/Dockerfile.worker:35`. When the worker is non-root and the flag is set, `make_preexec_fn` raises `PrivilegeDropUnavailableError` instead of downgrading. `docker-compose.yml` sets `no-new-privileges:true`. | CLOSED |
| Python site-packages isolation | The spawn args are `["python3", "-S", script]`, env is PATH only, and the denylist is extended. | CLOSED |
| CR-02 process-group kill | `run_in_process_group` has a `finally` that calls `kill_process_group` (SIGKILL to the pgid, guarded by `returncode is None`) and does a bounded reap. `TimeoutError` is caught and returned as `None`; `CancelledError` is never swallowed and still triggers the `finally`. The Go executor sends both the `go build` step and the binary run step through this helper. | CLOSED |
| Go rlimits | `_go_run_limits`: CPU backstop, 4 GiB address space, 256 open files, no NPROC (the Go runtime needs threads). Applied to the run step only. | CLOSED |
| Tests | Cancellation kills the group for Python, the Go run step, and timeout, all on uvloop. Call order and failure propagation of the preexec function are unit-tested. All pass. | VERIFIED |

**What remains open (honest residual risk, documented in `tools/process.py` trust model item 4):**
- Outbound network egress from generated code is not blocked. The import denylists are bypassable and are not a network control.
- Lateral access to postgres and redis with default credentials is still possible. A kernel-enforced control (NET_ADMIN or a separate sandbox, or a uid-owner iptables rule for uid 65534) is deferred to SEC-02/SEC-03 (v2).
- All concurrent runs share uid 65534, so one run can signal another. Go has no NPROC limit.
- The uid drop applies only when the worker euid is 0. Docker enforces this through the fail-closed flag; developer hosts are unchanged.
- Docker-side behavior (the probe `ALL CHECKS PASSED` incl. uvloop, live Two Sum with no permission errors) is user-attested in 02-UAT.md. The verifier cannot run as root in a container, so it was not re-run here. The unit and uvloop tests use patched euid and real spawns as non-root.

### Requirements Coverage

All 24 IDs appear in REQUIREMENTS.md as checked (`[x]`) and `Complete` in the traceability table (Phase 2). The stale-marker gap from the first report is fixed. No orphaned requirements.

| Requirement | Source Plan | Status |
|---|---|---|
| INTAKE-02, INTAKE-03 | 02-02 | SATISFIED |
| INTAKE-04, INTAKE-05, API-03 | 02-07 | SATISFIED |
| STRAT-01, STRAT-03, STRAT-04 | 02-03 | SATISFIED |
| CODE-01..04 | 02-04, 02-09 | SATISFIED |
| EXEC-01..03 | 02-05, 02-09, 02-10 | SATISFIED |
| REV-01..05 | 02-06 | SATISFIED |
| ORCH-03 | 02-01 | SATISFIED |
| ORCH-04 | 02-02, 02-07 | SATISFIED |
| INFRA-03 | 02-01 | SATISFIED (retry scope narrow, see WR-03) |
| INFRA-04 | 02-08, 02-10 | SATISFIED |

### Key Link Verification

| From | To | Status |
|---|---|---|
| `api/routes/tasks.py` | `attempt_consume_clarification` then `resume_task_with_clarification.kiq` | WIRED |
| Python executor | `tools.process.run_in_process_group` (with `make_limit_fn`, `prepare_workdir`) | WIRED |
| Go executor (build and run steps) | `tools.process.run_in_process_group` | WIRED |
| `run_in_process_group` | `make_preexec_fn` (privilege drop then rlimits) | WIRED |
| `worker/tasks.py` | `graph/build.py` with the shared Postgres checkpointer | WIRED |

### Data-Flow Trace (Level 4)

Unchanged: solver output flows to Solution, tests and rendered harness, then real executions, then the Reviewer, then the persisted result. The live Two Sum run in 02-UAT.md confirmed real data end to end.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full suite (real python3, go build, Postgres, uvloop) | `OPENAI_API_KEY=sk-dummy UV_PROJECT_ENVIRONMENT=/Users/egor/.venvs/algorunner uv run pytest -q` | 200 passed in 72.36s | PASS |

### Probe Execution

`scripts/verify_executor_isolation.py` exists and is the Docker isolation probe, but it needs a root worker container. It was run by the user (ALL CHECKS PASSED incl. uvloop, see 02-UAT.md) and not re-run by the verifier.

### Anti-Patterns Found

No TBD, FIXME or XXX markers in `src`, `scripts` or `docker`. The only uncommitted diff in the covered source is a formatting-only import re-wrap in `python_executor/subprocess_backend.py`, with no behavior change. It is included in the digest.

### Human Verification Required

None. All three items from the first report are resolved (02-UAT.md, status complete).

### Deferred advisory findings (from 02-REVIEW.md, not phase-goal failures)

WR-01..WR-10 and IN-* remain open by design and are advisory hardening for later. Not to be lost:
- Unbounded executor stdout/stderr capture (`proc.communicate()` buffers everything in memory).
- WR-03: retry covers only timeout and rate-limit (5xx and connection errors are fatal; `insufficient_quota` is retried).
- WR-07: `ReviewResult.passed=True` is not cross-checked against critical issues.
- WR-09: a re-delivered `solve_problem` resets status and restarts from START.
- Raw error text is exposed in GET task.
- WR-08: broker `unacknowledged_lock_timeout` units.
- Aliased Go imports (`import x "net"`) partially evade the text denylist.
- Network egress and lateral postgres/redis access (SEC-02/SEC-03, v2).

### Gaps Summary

No gaps. All five roadmap success criteria hold against the current code, CR-01 and CR-02 are closed in code with regression tests, the 200-test suite passes, and REQUIREMENTS.md traceability is complete for all 24 IDs.

---

_Verified: 2026-09-24_
_Verifier: Claude (gsd-verifier)_
