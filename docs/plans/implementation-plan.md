# Implementation Plan: AlgoRunner v1

## Overview

AlgoRunner is delivered as a single integrated milestone (v1) comprising 4 phases. Each phase is a vertical slice, building on the prior phase and delivering measurable user-facing progress. Phases are executed in numeric order: 1 → 2 → 3 → 4.

Work is organized into plans (typically 1-8 per phase), each with a single objective and delivery of specific features. Plans are tracked in the `.planning/phases/` directory.

## Phase 1: Foundation & Task Lifecycle Skeleton

**Goal:** Real API, queue, worker, and database wiring so a submitted task moves through queued → completed on a deployed stack (before any AI logic).

**Requirements Met:** INTAKE-01, ORCH-02, API-01, API-02, QUEUE-01, DATA-01, INFRA-01, INFRA-02

**Status:** ✓ Complete (2026-09-22)

**Plans (2 completed):**

1. **01-01:** Task lifecycle core (contracts, data layer, worker, API) wired end-to-end, then containerized as the full 5-service Docker Compose stack.
2. **01-02:** LangGraph stub graph checkpointed to Postgres (D-12/D-13 smoke test), validation/error-state hardening, and a final full-stack verification.

## Phase 2: Verified Single-Solution Core Pipeline

**Goal:** A submitted problem is analyzed and solved, producing one algorithm approach whose Python and Go code are proven correct by real execution, with clarification and correction handled automatically.

**Requirements Met:** INTAKE-02, INTAKE-03, INTAKE-04, INTAKE-05, STRAT-01, STRAT-03, STRAT-04, CODE-01, CODE-02, CODE-03, CODE-04, EXEC-01, EXEC-02, EXEC-03, REV-01, REV-02, REV-03, REV-04, REV-05, ORCH-03, ORCH-04, API-03, INFRA-03, INFRA-04

**Status:** ✓ Complete (2026-09-24)

**Plans (10 completed):**

1. **02-01:** Phase 2 Pydantic contracts, Settings extension, LLM client factory + retry wrapper
2. **02-02:** Analyzer tracer (real OpenAI call + real graph + real Postgres checkpoint), Phase-1 hardening (CR-01..CR-04, WR-01)
3. **02-03:** Solution Strategist + Solver nodes, wired into the pipeline graph
4. **02-04:** Code Generator + Test Generator nodes (D-10/D-11 example-preservation and 10-test minimum)
5. **02-05:** Python + Go executor tools (subprocess/compile+run, resource limits, import denylist, Docker Go toolchain)
6. **02-09:** Gap closure from 02-05: fixed Code Generator entry point + language-neutral structured tests + typed Python/Go harness renderers
7. **02-06:** Reviewer node + bounded, issue-routed correction loop
8. **02-07:** Clarification pause/resume (interrupt()/Command) + clarification API endpoints
9. **02-08:** Global solve-time timeout + final live full-stack verification
10. **02-10:** Gap closure from 02-REVIEW (CR-01, CR-02): executor children run as unprivileged uid 65534, whole-process-group kill on cancel/timeout, Go rlimits

## Phase 3: Multi-Approach Editorial & Persistence

**Goal:** The pipeline surfaces multiple solution approaches and composes them into a complete, Russian-language editorial article that is durably persisted.

**Requirements Met:** STRAT-02, EDIT-01, EDIT-02, EDIT-03, EDIT-04, EDIT-05, EDIT-06, ORCH-01, DATA-02

**Status:** Planned (8 plans)

**Plans:**

1. **03-01:** Tracer: Send fan-out of per-approach subgraphs → join once → D-13 approaches index in tasks.result; env repair gate; Phase 2 regressions on the per-branch shape
2. **03-02:** Garage artifact store: boto3 legitimacy gate, D-19 key builders, bounded warn-and-continue writes, recorder, compose bucket/key provisioning
3. **03-03:** Strategist curation (role + rationale, cap max_approaches, dedup) + branch hardening (isolation, join-once, per-branch budget, idempotent re-invoke)
4. **03-04:** Editorial Writer: one-call Russian prose draft + deterministic assembly (verbatim executed code, injected difficulty/tags/role/Big-O) → result.editorial
5. **03-05:** 20-min time budget (deadline-bounded branches ship verified ones, Writer reserve + model override, executor semaphore, status transitions, recursion limit)
6. **03-06:** Russian guarantee: Cyrillic check + one shared retry, user-confirmed split (EDITORIAL_ASSEMBLY_FAILED vs shipped with editorial_warnings)
7. **03-07:** Editorial completeness: Reviewer-confirmed edge cases, minor notes, clarifications/assumption in the restatement
8. **03-08:** Incremental Garage persistence across the graph (incl. the zero-verified timeout trail), written-keys-only result + live full-stack phase acceptance

## Phase 4: Realtime Streaming, Frontend & Documentation

**Goal:** A user can watch their task progress live and interact with the whole system through a web UI, and the project ships with a full, coherent documentation set.

**Requirements Met:** API-04, API-05, UI-01, UI-02, UI-03, UI-04, INFRA-05

**Status:** Planned (8 plans)

**Plans:**

1. **04-01:** Tracer: status write → Postgres → Redis → WS relay → client; every status writer publishes after commit; monotonic updated_at; ordering, refresh, terminal close and late-connect guarantees (API-04, API-05)
2. **04-02:** The 4 missing in-graph statuses (D-04); GET /api/config (D-20); WS Origin allowlist (4403) and connection cap (1013)
3. **04-03:** Frontend tracer: npm legitimacy gate, Vite + React + TS scaffold, submit a problem and watch live status (Context + reducer, WS hook with reconnect)
4. **04-04:** Docs: architecture, agents, workflow, data-model, PRD, implementation plan, DEFERRED.md ← **This plan**
5. **04-05:** UI: example list + API-mirroring validation; non-dismissible clarification modal (UI-01, UI-03)
6. **04-06:** UI: full-page editorial with collapsible approaches, highlighted and copyable Python/Go code (UI-04)
7. **04-07:** Deployment: frontend image, nginx gateway, 7-service compose; live acceptance through nginx + end-of-phase UI walkthrough
8. **04-08:** Docs: testing and conventions guides, .claude/CLAUDE.md repository rules, README, docs completeness gate

## Work Organization

**Phases are vertical slices**, not horizontal layers. Each phase adds new capability end-to-end:
- Phase 1: infrastructure works, status moves (no AI yet)
- Phase 2: AI pipeline works for single solution, code is verified
- Phase 3: Multiple solutions, Russian editorial, durably stored
- Phase 4: Live UI, full documentation, ready for users

**Plans within a phase are ordered by dependency.** Each plan depends on prior plans in the phase; a plan may also depend on a prior phase (stated in the plan's `depends_on` field).

**Waves within a phase** group plans that can execute in parallel or in sequence:
- Wave 1: First set of plans (may have multiple plans if truly parallel)
- Wave 2: Dependent on Wave 1
- ... and so on

See `.planning/phases/{NN}-{phase_name}/ROADMAP.md` for the full roadmap with wave dependencies.

## Plan Files

Each plan lives in `.planning/phases/{NN}-{phase_name}/{NN}-{plan_num}-PLAN.md` and contains:

- **Frontmatter:** phase, plan, type (auto/tracer/checkpoint), wave, depends_on, requirements, estimate, must_haves
- **Objective:** What this plan accomplishes
- **Context:** Links to prior decisions and reference materials
- **Tasks:** 1-N tasks, each type="auto" or type="checkpoint:*"
- **Verification:** Automated and manual success checks
- **Success Criteria:** Acceptance thresholds

Plan Summaries are created at completion and live in `.planning/phases/{NN}-{phase_name}/{NN}-{plan_num}-SUMMARY.md`.

## Requirements Traceability

All 48 v1 requirements (INTAKE-01..06, STRAT-01..04, CODE-01..04, EXEC-01..03, REV-01..05, EDIT-01..06, ORCH-01..04, API-01..05, QUEUE-01, DATA-01..02, UI-01..04, INFRA-01..05) are mapped to phases and plans:

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTAKE-01 | Phase 1 | ✓ Complete |
| ORCH-02 | Phase 1 | ✓ Complete |
| API-01 | Phase 1 | ✓ Complete |
| ... | ... | ... |
| API-04 | Phase 4 | Planned |
| UI-01 | Phase 4 | Planned |
| INFRA-05 | Phase 4 | Planned |

(See `.planning/REQUIREMENTS.md` for the full traceability table.)

## Key Decisions by Phase

**Phase 1:**
- Single uv-managed Python package with modular structure (agents/, api/, worker/, schemas/, tools/)
- Docker Compose for local dev and deployment
- Postgres as the single source of truth for task state
- taskiq + RedisStreamBroker for the task queue

**Phase 2:**
- LLM reasoning bounded to specific nodes; no free supervisor-driven routing
- Generic Solver agent, not one per algorithm type
- OpenAI structured outputs (Pydantic schemas) for inter-node contracts
- Per-agent model configuration via environment variables

**Phase 3:**
- LangGraph Send fan-out per-approach branches; join once
- Garage (S3-compatible) for durable intermediate artifact storage
- Editorial JSON (not Markdown) for flexibility in UI rendering
- Verbatim executed code in the editorial (never rewritten)

**Phase 4:**
- WebSocket API for live status streaming (publish-after-commit model)
- Vite + React + TypeScript for the frontend
- nginx reverse proxy to unify API and frontend under one host
- Runtime /api/config endpoint for frontend to discover API/WebSocket URLs

All decisions are logged in `.planning/phases/*/CONTEXT.md` with D-IDs for reference.

## Effort Estimates

| Phase | Plans | Estimate | Status |
|-------|-------|----------|--------|
| Phase 1 | 2 | - | ✓ Complete |
| Phase 2 | 10 | - | ✓ Complete |
| Phase 3 | 8 | - | Planned |
| Phase 4 | 8 | - | Planned |

Estimates are tracked per-plan in `estimate` frontmatter fields.

## Success Criteria

The v1 milestone is complete when:

1. All 48 requirements are implemented and tested.
2. Users can submit a problem → receive a live-updated editorial with multiple approaches (Python + Go) → all code is verified as working.
3. The documentation set is complete and accurate (PRD, architecture, development guides, README).
4. Docker Compose brings up the full system (API, worker, frontend, database, queue, storage) in one command.
5. The system handles failures gracefully (no stuck tasks, clear error messages, bounded retries).
