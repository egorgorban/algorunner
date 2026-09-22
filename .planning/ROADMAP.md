# Roadmap: AlgoRunner

## Overview

AlgoRunner starts as a bare task-lifecycle skeleton (submit → queue → status, on real infrastructure) so every later phase has a trustworthy foundation to build on. Phase 2 then delivers the product's actual core value in one vertical slice: a submitted problem is analyzed, solved by a generic Solver, implemented in Python and Go, executed for real, reviewed, and automatically corrected until it passes or fails cleanly — with clarification pause/resume built in from the start. Phase 3 widens that single verified solution into the full multi-approach, Russian-language editorial article, durably persisted. Phase 4 closes the loop with live WebSocket status streaming, the React + TypeScript web UI, and the complete documentation set — turning the verified pipeline into a usable, documented product.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & Task Lifecycle Skeleton** - Real API, queue, worker, and database wiring so a submitted task moves through queued → completed on a deployed stack, before any AI logic exists
- [ ] **Phase 2: Verified Single-Solution Core Pipeline** - Analyzer, generic Solver, dual-language code generation, real Python/Go execution, Reviewer, and bounded correction loop deliver one verified solution end-to-end
- [ ] **Phase 3: Multi-Approach Editorial & Persistence** - Multiple curated approaches compose into the final Russian-language editorial article, with all artifacts durably persisted
- [ ] **Phase 4: Realtime Streaming, Frontend & Documentation** - Live WebSocket status, the React web UI, and the full documentation set complete the user-facing product

## Phase Details

### Phase 1: Foundation & Task Lifecycle Skeleton

**Goal**: As a user, I want to submit a problem and observe it move through the task lifecycle end-to-end on a real deployed stack, even before real AI processing exists, so that every later phase has a trustworthy infrastructure foundation to build on
**Mode**: mvp
**Depends on**: Nothing (first phase)
**Requirements**: INTAKE-01, ORCH-02, API-01, API-02, QUEUE-01, DATA-01, INFRA-01, INFRA-02
**Success Criteria** (what must be TRUE):

  1. Running `docker compose up` brings up API, worker, PostgreSQL, Redis, and Garage together and the API responds to requests
  2. A user can POST a problem submission (text + optional examples) to `POST /api/v1/tasks` and immediately receives `202 Accepted` with a `task_id` and `status: queued`
  3. The submitted task is enqueued via taskiq + Redis, picked up by a worker, and its status is visible via `GET /api/v1/tasks/{id}` with PostgreSQL as the single source of truth for that status
  4. All data exchanged between API and worker is validated by Pydantic schemas, inside a single `uv`-managed package with clear modular structure (agents/, tools/, api/, worker/, schemas/)

**Plans**: 2/2 plans executed
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Task lifecycle core (contracts, data layer, worker, API) wired end-to-end, then containerized as the full 5-service Docker Compose stack

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — LangGraph stub graph checkpointed to Postgres (D-12/D-13 smoke test), validation/error-state hardening, and a final full-stack verification

### Phase 2: Verified Single-Solution Core Pipeline

**Goal**: A submitted problem is actually analyzed and solved by the AI pipeline, producing one algorithm approach whose Python and Go code are proven correct by real execution, with clarification and correction handled automatically
**Mode**: mvp
**Depends on**: Phase 1
**Requirements**: INTAKE-02, INTAKE-03, INTAKE-04, INTAKE-05, STRAT-01, STRAT-03, STRAT-04, CODE-01, CODE-02, CODE-03, CODE-04, EXEC-01, EXEC-02, EXEC-03, REV-01, REV-02, REV-03, REV-04, REV-05, ORCH-03, ORCH-04, API-03, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):

  1. The Problem Analyzer extracts constraints/intent from free-text input (English or Russian), assigns a difficulty rating, and — when the problem is ambiguous or underspecified — moves the task to `awaiting_clarification` instead of guessing
  2. A user can answer a pending clarification via `POST /api/v1/tasks/{id}/clarification`, and the task resumes from its checkpointed LangGraph state rather than restarting
  3. A generic Solver elaborates a Strategist-proposed approach (tagged with its topic/technique) into working Python and Go implementations plus generated tests, incorporating any provided examples and adding edge-case tests when needed
  4. The generated Python and Go code are actually executed via swappable executor tools (subprocess/compile+run) against the tests, producing a structured pass/fail result, and a Reviewer evaluates correctness, edge cases, and a justified complexity claim into a structured ReviewResult
  5. A failing review automatically routes back into a bounded correction loop (carrying prior attempt context) that ends in either a passing solution or a clean terminal FAILED result within `max_iterations` — never an unbounded loop — while OpenAI timeouts/rate-limits retry with backoff and total solve time is capped by a global timeout

**Plans**: TBD

### Phase 3: Multi-Approach Editorial & Persistence

**Goal**: The pipeline surfaces multiple solution approaches and composes them into a complete, Russian-language editorial article that is durably persisted
**Mode**: mvp
**Depends on**: Phase 2
**Requirements**: STRAT-02, EDIT-01, EDIT-02, EDIT-03, EDIT-04, EDIT-05, EDIT-06, ORCH-01, DATA-02
**Success Criteria** (what must be TRUE):

  1. The Solution Strategist proposes multiple candidate approaches (e.g. brute-force, optimized, alternative) and curates which ones are worth including, rather than surfacing every possibility
  2. A completed task produces a Russian-language editorial regardless of input language, with each approach following Intuition → Algorithm → Code (Python + Go) → Complexity (with a one-line justification), presented in sequential order with a narrative bridge explaining why each subsequent approach improves on the last
  3. The article surfaces the difficulty rating, topic/technique tags, and the edge cases the Reviewer identified as handled, and reflects any resolved clarification in the problem restatement
  4. The full pipeline (Analyzer → Strategist → Solver → Code Generator → Test Generator → Executors → Reviewer → correction loop → Editorial Writer) runs as one deterministic LangGraph StateGraph, and every intermediate artifact (analysis, each solution's code/tests/review history, final editorial) is persisted to Garage

**Plans**: TBD

### Phase 4: Realtime Streaming, Frontend & Documentation

**Goal**: A user can watch their task progress live and interact with the whole system through a web UI, and the project ships with a full, coherent documentation set
**Mode**: mvp
**Depends on**: Phase 3
**Requirements**: API-04, API-05, UI-01, UI-02, UI-03, UI-04, INFRA-05
**Success Criteria** (what must be TRUE):

  1. Connecting to `WS /api/v1/tasks/{id}/events` streams live status transitions (queued → analyzing_problem → ... → completed/failed), and a client connecting after the task has already progressed immediately receives its current state, not only future deltas
  2. A user can submit a problem, watch live status, answer a clarification prompt, and view the final editorial (per-approach explanation, Python/Go code, complexity, difficulty, tags, edge cases) entirely through the React + TypeScript web UI
  3. The repository includes the full documentation set (`CLAUDE.md`, `docs/product/prd.md`, `docs/architecture/{architecture,agents,workflow,data-model}.md`, `docs/development/{testing,conventions}.md`, `docs/plans/implementation-plan.md`) with deferred/future-scope items captured in their own dedicated section

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Task Lifecycle Skeleton | 2/2 | In Progress|  |
| 2. Verified Single-Solution Core Pipeline | 0/TBD | Not started | - |
| 3. Multi-Approach Editorial & Persistence | 0/TBD | Not started | - |
| 4. Realtime Streaming, Frontend & Documentation | 0/TBD | Not started | - |
