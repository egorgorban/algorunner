# Phase 1: Foundation & Task Lifecycle Skeleton - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Real API, queue, worker, and database wiring so a submitted task moves through `queued → completed` (or `failed`) on a deployed stack, **before any AI logic exists**. No Problem Analyzer, no Solver, no code generation — this phase proves the infrastructure skeleton works end-to-end. Requirements: INTAKE-01, ORCH-02, API-01, API-02, QUEUE-01, DATA-01, INFRA-01, INFRA-02.

</domain>

<decisions>
## Implementation Decisions

### Task Submission Payload (`POST /api/v1/tasks`)
- **D-01:** Request body includes the full future shape now, not a minimal subset: `problem_text` (required, max 5,000 chars), `language` (required enum `"en" | "ru"`), `examples` (optional list of `{input, output}` pairs, max 10 items). — **Reversibility:** costly — unused fields (`language`, `examples`) sit dormant until Phase 2's Analyzer and Phase 2's Test Generator consume them; changing the shape later means a schema migration touching both API validation and the DB row.
- **D-02:** `examples` is structured as a list of `{input, output}` string pairs (not a raw text blob) — matches LeetCode-style test cases directly, so Phase 2's Test Generator can consume it without re-parsing.
- **D-03:** Basic validation plus explicit limits are enforced in Phase 1 (not deferred): `problem_text` max 5,000 chars, `examples` max 10 items, `language` strictly one of `"en"`/`"ru"` (reject anything else, no auto-detect fallback in this phase).

### Worker Placeholder Behavior
- **D-04:** The Phase 1 worker task has no AI logic — it simulates processing with a configurable success/fail outcome so both the happy path and the failure path are exercised end-to-end.
- **D-05:** Failure is triggered by content: a magic string (e.g. `FAIL_TEST`) inside `problem_text` causes the worker to fail the task, rather than a separate request field. No schema pollution from a test-only flag.
- **D-06:** The worker sleeps briefly (2-5s) before resolving, so the task visibly sits in a non-terminal status — this exercises the real status-transition path (useful for verifying `GET /api/v1/tasks/{id}` polling and later WebSocket work in Phase 4), rather than resolving instantly.
- **D-07:** A failed task stores a structured error object (`{code, message}`), not a plain string — matches the shape Phase 2's real pipeline errors will use, avoiding a reshape later. — **Reversibility:** costly — API clients (including the Phase 4 frontend) will read `error` in this shape; changing it later is a breaking API change.

### Status Vocabulary
- **D-08:** The full future status enum is defined in Phase 1 (`queued, analyzing_problem, designing_solution, generating_code, generating_tests, executing_tests, reviewing, correcting, awaiting_clarification, writing_editorial, completed, failed`), even though only a subset is reachable this phase. — **Reversibility:** one-way — this enum is the DB column's contract; adding values later is a low-cost additive migration, but removing/renaming touches every consumer and was explicitly avoided by front-loading the full set now.
- **D-09:** The Phase 1 placeholder worker sets status to `analyzing_problem` (the first real pipeline stage) while "processing," rather than inventing a generic `processing` status — there is no throwaway status to remove when Phase 2 lands.
- **D-10:** The status column is a plain string/varchar in PostgreSQL, validated by an app-level Python enum (not a native Postgres `ENUM` type) — adding new statuses later is a code change only, no `ALTER TYPE` migration.

### Scaffolding Depth (LangGraph + Garage)
- **D-11:** Garage runs in `docker-compose` (satisfying INFRA-02 literally) but is **not** wired to any client code in Phase 1 — no bucket creation, no connectivity smoke test. Real integration (DATA-02) is Phase 3's job.
- **D-12:** LangGraph, by contrast, **is** wired now: the worker invokes a trivial single-node stub graph (wrapping the placeholder success/fail logic from D-04–D-07), checkpointed to PostgreSQL via `AsyncPostgresSaver`. This doubles as the early smoke test for the STATE.md-flagged risk ("LangGraph's Python 3.14 support is unconfirmed"). — **Reversibility:** reversible — the stub node is replaced by Phase 2's real graph; only the checkpoint plumbing (thread_id ↔ task_id mapping) persists forward.
- **D-13:** If the Python 3.14 + LangGraph compatibility smoke test fails during Phase 1 setup, the documented fallback applies automatically: pin the interpreter to 3.13 and continue, rather than halting to ask the user (STATE.md already records this as the agreed fallback for this specific, pre-flagged risk).

### Claude's Discretion
- Exact taskiq broker choice (`RedisStreamBroker` vs `ListQueueBroker`) — not discussed with user; `.planning/research/STACK.md` recommends `RedisStreamBroker` (acks, durable) as the default. Researcher/planner should confirm against that doc.
- Internal package/module layout within the single `uv` package (`agents/`, `tools/`, `api/`, `worker/`, `schemas/` per INFRA-01) — file-level organization is Claude's call within that fixed top-level structure.
- Docker Compose service details (healthchecks, port mappings, env var wiring) — standard implementation detail, no user preference expressed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level (locked scope and constraints)
- `.planning/PROJECT.md` — core value, full constraints list, key decisions log
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: INTAKE-01, ORCH-02, API-01, API-02, QUEUE-01, DATA-01, INFRA-01, INFRA-02 (and their acceptance shape)
- `.planning/ROADMAP.md` — Phase 1 section: goal, success criteria, dependencies (none — first phase)
- `.planning/STATE.md` — Accumulated Context / Blockers section: LangGraph Python 3.14 risk (addressed by D-12/D-13), OpenAI SDK v1-vs-v2 pinning note (not yet locked — flag for researcher)

### Technology research (from project research phase)
- `.planning/research/STACK.md` — recommended package versions, taskiq broker comparison, `psycopg`/`AsyncPostgresSaver` setup gotchas (autocommit, row_factory), `uv` workspace-vs-single-package guidance
- `.planning/research/ARCHITECTURE.md` — architecture patterns for this stack
- `.planning/research/PITFALLS.md` — known footguns (e.g. `RLIMIT_FSIZE` executor trap — not Phase 1-relevant yet, but Phase 1 sets up the executor interface boundary)
- `.planning/research/FEATURES.md`, `.planning/research/SUMMARY.md` — supporting research context

### Source material
- `interview.md` (repo root) — original two-round product/architecture interview; already resolved into PROJECT.md/REQUIREMENTS.md, kept as reference for any nuance not captured in the distilled docs

</canonical_refs>

<code_context>
## Existing Code Insights

Greenfield project — no source code exists yet (repo currently contains only `.planning/`, `.claude/`, `interview.md`). No reusable assets, established patterns, or integration points to inventory. Phase 1 establishes the first patterns everything after it follows.

</code_context>

<specifics>
## Specific Ideas

- Worker's fake-processing failure trigger is a literal magic string (`FAIL_TEST` or similar) embedded in `problem_text` — this is a Phase-1-only test hook and should be clearly marked as such (comment/docstring) so it isn't mistaken for real Analyzer behavior in Phase 2.
- The LangGraph stub graph in Phase 1 is explicitly a smoke test for the Python 3.14 compatibility risk already flagged in STATE.md — its purpose is de-risking, not functional value. Frame it that way in the plan so it isn't over-built.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. No scope-creep items came up; both scaffolding questions (Garage, LangGraph) were legitimate Phase 1 depth-of-implementation decisions, not new capabilities.

</deferred>

---

*Phase: 1-Foundation & Task Lifecycle Skeleton*
*Context gathered: 2026-09-22*
