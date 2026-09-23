---
phase: 02-verified-single-solution-core-pipeline
plan: 10
subsystem: tools/executors
tags: [security, cancellation, process-group, privilege-drop, docker, gap-closure]
requires: [02-05, 02-08]
provides:
  - "tools/process.py: run_in_process_group (kill-and-reap on every exit path), make_limit_fn, spawn_identity_kwargs, prepare_workdir, PrivilegeDropUnavailableError, documented trust model"
  - "Executors spawn children as uid/gid 65534 when the worker is root; python3 -S; extended denylists; Go rlimits"
  - "scripts/verify_executor_isolation.py container acceptance probe"
affects: [python_executor, go_executor, docker/Dockerfile.worker, docker-compose.yml]
tech-stack:
  added: []
  patterns: ["single shared spawn/kill helper", "euid-conditional privilege drop with fail-closed env flag"]
key-files:
  created:
    - src/algorunner/tools/process.py
    - tests/tools/test_executor_cancellation.py
    - tests/tools/test_executor_isolation.py
    - scripts/verify_executor_isolation.py
  modified:
    - src/algorunner/tools/python_executor/subprocess_backend.py
    - src/algorunner/tools/go_executor/subprocess_backend.py
    - docker/Dockerfile.worker
    - docker-compose.yml
key-decisions:
  - "Worker stays root; each child is dropped to 65534 via create_subprocess_exec user/group/extra_groups (applied before preexec_fn so NPROC=0 is effective)"
  - "Fail closed via ALGORUNNER_REQUIRE_PRIVILEGE_DROP=1 in the image"
  - "Single hard SIGKILL of the process group in a finally; no graceful phase"
  - "Network egress and lateral postgres/redis access explicitly left open (SEC-02/SEC-03), documented in process.py"
requirements-completed: [EXEC-01, EXEC-02, INFRA-04]
status: partial
commits: 5
plan_head_before: 4d04d094d1f6570d836fc4f9f8af2536d826b2cf
duration: ~40 min
completed: 2026-09-24
actuals:
  tokens: 30000
  tasks: 3
  commits: 5
---

# Phase 2 Plan 10: Executor isolation and cancellation (CR-01, CR-02) Summary

Shared `tools/process.py` kills the whole child process group on every exit path (including the real GLOBAL_TIMEOUT cancellation), and generated code is dropped to uid 65534 in the root worker so it can no longer read the API key via /proc.

Status is `partial`: Tasks 1-3 are done and committed; Task 4 (human Docker acceptance) is awaiting the user.

## What was done

- **Task 1 (CR-02)**: `run_in_process_group` spawns with `start_new_session`, and a `finally` SIGKILLs the group and reaps with a bounded wait, covering cancel, timeout and any exception. Python run, Go build and Go run all use it. Go run gets CPU (2x timeout, min 2s), NOFILE 256 and AS 4 GiB limits, deliberately no NPROC. Proven through a real LangGraph graph (InMemorySaver) inside the real `_invoke_with_budget`.
- **Task 2 (CR-01)**: euid==0 -> `user=group=65534, extra_groups=[]`, run tree chowned once via `prepare_workdir` before any spawn; non-root behaves as before; with the env flag a non-root worker raises `PrivilegeDropUnavailableError`. Python runs `python3 -S`. Denylists extended (Python modules plus `__import__`/`__builtins__`; Go `crypto/tls`, `plugin`, `C`). Docstrings now state denylists are best-effort and uid separation is the only boundary.
- **Task 3**: Dockerfile sets the flag and has a build-time guard that uid 65534 can run the venv Python and `go version`; compose worker gets `no-new-privileges`; probe script added (exits 2 when not root).

## RED evidence

- Cancellation tests (commit b7d1781): Python/Go-build/Go-run/budget cancel tests failed with the child group still alive; helper tests failed on the missing `run_in_process_group`/`_go_run_limits`.
- Isolation tests (commit d62bf14): `ImportError: cannot import name 'PrivilegeDropUnavailableError'`.

## Verification performed

- Full suite: `OPENAI_API_KEY=test-dummy uv run pytest -q` -> 185 passed; no orphan `sleep 60` processes.
- `docker build -f docker/Dockerfile.worker` succeeded (build-time uid 65534 guard passed); `docker compose config -q` exits 0.
- Executor-side dry run of the probe (my own `docker run --rm -i` with a canary key, no compose, no ports): all 10 checks printed PASS and `ALL CHECKS PASSED`. This does NOT replace the user's Task 4 sign-off, which additionally covers Step B (live pipeline).
- `tools/base.py`, `graph/build.py`, `worker/tasks.py` untouched.

## Deviations from Plan

- **[Minor]** Test `test_go_executor_passes_limits_only_to_run_step` uses `calls[0].get("limit_fn")` because the build call omits `limit_fn` entirely (plan said both "omitted" and "received None").
- No other deviations. Nothing was fixed from the out-of-scope review findings list.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register (T-02-10-05 network/lateral access remains an accepted residual).

## Awaiting: Task 4 (human-verify)

Run from the repository root:

Step A:
1. `docker build -f docker/Dockerfile.worker -t algorunner-worker:cr01 .`
2. `cat scripts/verify_executor_isolation.py | docker run --rm -i -e OPENAI_API_KEY=sk-canary-not-real algorunner-worker:cr01 uv run python -` (expect `ALL CHECKS PASSED`)

Step B (real key, stack): `docker compose up -d --build`, submit the two-sum task and poll, expect `completed True True True`, and `docker compose logs worker --tail 100 | grep -Ei "permission|eperm|disallowed" || echo "no permission errors"`. Full commands are in 02-10-PLAN.md Task 4.

## Self-Check: PASSED

Created files exist (process.py, both test modules, probe script); commits b7d1781, f9cc570, d62bf14, 093b774, d82a9dc present on the branch.
