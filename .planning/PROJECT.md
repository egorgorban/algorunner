# AlgoRunner

## What This Is

Production-ready multi-agent system that takes a text description of a LeetCode-style algorithmic problem (English or Russian) and produces a LeetCode-editorial-style article in Russian: one or more solution approaches (e.g. brute-force and optimized), each with explanation, Python code, Go code, and asymptotic complexity. Built for students and developers preparing for technical interviews.

## Core Value

Correctness of the generated solution — verified by actually executing the generated Python and Go code against generated (or provided) tests — matters more than explanation quality or speed.

## Requirements

### Validated

- ✓ REST API (FastAPI): `POST /api/v1/tasks` creates a task (202 Accepted, returns task_id + status=queued), `GET /api/v1/tasks/{id}` fetches current state — Phase 1
- ✓ Task queue (taskiq + Redis broker): API enqueues and returns immediately; if workers are busy, task sits in "queued" status until a worker is free — Phase 1
- ✓ PostgreSQL stores task state (id, status, timestamps, error, result) and LangGraph checkpoints — Phase 1 (both proven live against real Postgres, not `InMemorySaver`)
- ✓ LangGraph execution state is checkpointed so an interrupted run can resume — Phase 1 (compiled `StateGraph` + `AsyncPostgresSaver`, confirmed under Python 3.14)
- ✓ Docker Compose deployment (API, worker, Postgres, Redis, Garage) — Phase 1

### Active

- [ ] User submits a problem description (text + optional examples) and receives an editorial-style result with 1+ solution approaches
- [ ] Each solution approach includes: explanation, Python code, Go code, complexity analysis
- [ ] Problem Analyzer extracts/clarifies the task from free-text input; when ambiguous or underspecified, the task moves to an `awaiting_clarification` status and an API endpoint lets the user submit an answer to resume the same task (real interactive pause/resume, not stated assumptions)
- [ ] Editorial includes a difficulty rating (Easy/Medium/Hard) from the Problem Analyzer
- [ ] Editorial includes topic/technique tags (e.g. two pointers, DP, graph) from the Solution Strategist
- [ ] Editorial includes explicit edge-case callouts sourced from the Reviewer's edge-case checks
- [ ] Editorial Writer includes a narrative bridge explaining why each subsequent approach improves on the previous one
- [ ] Solution Strategist proposes 1+ distinct approaches (e.g. brute-force + optimized) using a generic solver (not one agent per algorithm type)
- [ ] Code Generator produces Python and Go implementations per approach
- [ ] Test Generator produces test cases per approach (uses provided tests if given, generates additional ones otherwise)
- [ ] Deterministic Python Executor tool runs generated Python code + tests via subprocess (no sandbox yet) and returns structured pass/fail results
- [ ] Deterministic Go Executor tool compiles/runs generated Go code + tests and returns structured pass/fail results
- [ ] Reviewer agent evaluates correctness, algorithm soundness, edge cases, complexity claim, code quality; returns structured ReviewResult (passed, issues, severity, required_changes)
- [ ] Correction loop: failed review routes back to Solution Designer/Solver with a bounded max_iterations (3-5); exceeding it yields a FAILED result instead of looping forever
- [ ] Editorial Writer composes the final Russian-language article from validated solutions
- [ ] LangGraph orchestrates the pipeline as a fixed state graph (hybrid architecture): deterministic transitions, LLM reasoning bounded to specific nodes (analysis, strategy, generation, review, writing)
- [ ] Per-agent model configuration via env/config (different OpenAI models for cheap vs strong reasoning steps)
- [ ] Structured outputs (Pydantic schemas) between agents/nodes
- [ ] WebSocket API: `WS /api/v1/tasks/{id}/events` streams pipeline status transitions (queued → analyzing_problem → designing_solution → generating_code → generating_tests → executing_tests → reviewing → correcting → writing_editorial → completed/failed)
- [ ] Intermediate artifacts persisted per task: ProblemAnalysis, Solution[] (algorithm, python code, go code, tests, complexity, review history), final Editorial — stored in Garage (S3-compatible object storage)
- [ ] Worker-side task failures (exceptions, missing rows, checkpointer setup races) are always caught and surfaced as a structured `FAILED` status — never left stuck at a non-terminal status or silently reported as completed (surfaced by Phase 1 code review; must hold before Phase 2 adds more failure-prone AI/execution logic to the same code path)
- [ ] Global timeout on total task solve time; retries with backoff on OpenAI timeout/rate-limit (pause + cooldown)
- [ ] React + TypeScript web UI: problem input form, live status view (via WebSocket), final editorial display (per-approach: explanation, Python, Go, complexity)
- [ ] Docker Compose deployment (API, worker, Postgres, Redis, Garage)
- [ ] Full docs set mirroring BMAD-inspired structure: `CLAUDE.md` (minimal, repo working rules) + `docs/product/prd.md` + `docs/architecture/{architecture,agents,workflow,data-model}.md` + `docs/development/{testing,conventions}.md` + `docs/plans/implementation-plan.md`
- [ ] Deferred/future-scope assumptions captured in their own dedicated section in the specs, not lost inline

### Out of Scope

- Authentication — explicitly deferred to a later milestone
- Sandboxed code execution (Docker sandbox / isolated execution service) for generated Python/Go — v1 uses plain subprocess execution; sandboxing is a known future hardening step, tracked but not built now
- Resource limits on generated-code execution (CPU/RAM/time/network/filesystem) — deferred alongside sandboxing
- Kubernetes deployment — v1 ships on Docker Compose; Kubernetes is a later infrastructure milestone
- Observability stack (structured logging beyond basics, Prometheus, OpenTelemetry, LangSmith tracing, cost/token tracking) — deferred to a later milestone
- Evaluation framework and benchmark dataset (no existing dataset; system relies on the LLM's built-in capability for v1) — deferred
- Cross-task memory (system remembering a user's previous solved problems) — deferred to a later milestone
- Runtime verification that the claimed asymptotic complexity actually holds (empirical complexity testing) — out of scope, complexity is reviewed analytically only
- Literal BMAD agent personas (Analyst/PM/Architect/Scrum Master/Developer roles) — using BMAD as a methodology/doc-structure influence only, not a literal role-play workflow
- CI/CD, pre-commit, ruff, mypy/pyright enforcement — not required for this milestone (max type-safety is still a coding constraint, just not gated by tooling yet)

## Context

- Solo technical decision-maker (acting as product owner) working with Claude Code as the implementer, following a GSD-adapted BMAD-influenced lifecycle: analysis → PRD → architecture → implementation plan → phased implementation → tests → review.
- Source material: a detailed two-round interview (`interview.md`) already resolved most product and architecture questions before this session — see Key Decisions below for the load-bearing ones.
- User wants git history to read as a single coherent, well-documented build: intermediate architectural decisions captured in specs/docs, deferred/future-scope items explicitly called out in their own section rather than scattered or lost.
- Claude Code is expected to work autonomously through phases without asking permission on every minor task, but should checkpoint at architectural decisions and the completion of major phases.

## Constraints

- **Tech stack**: Python 3.14, LangGraph, OpenAI API (model configurable via env/config, with optional per-agent model overrides) — fixed by product owner
- **Package manager**: `uv` — fixed
- **Task queue**: taskiq + Redis (not Celery — too heavyweight; not ARQ — unsupported/unmaintained) — fixed
- **Database**: PostgreSQL — task state (source of truth) + LangGraph checkpoint storage
- **Artifact storage**: Garage (S3-compatible) for intermediate agent artifacts (analysis, solutions, review history, tests)
- **Frontend**: React + TypeScript, included in v1 (not deferred)
- **Deployment**: Docker Compose for this milestone; Kubernetes explicitly deferred
- **Type safety**: maximum feasible in Python (even though CI/lint tooling enforcement is deferred)
- **Architecture style**: simple modular architecture (not DDD/clean architecture) — explicit product-owner preference
- **Code execution**: Python via subprocess, Go via compile+run — both without sandboxing in v1
- **Language**: input text in English or Russian; output (editorial) always in Russian

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hybrid agent architecture: fixed LangGraph state graph, LLM reasoning bounded to specific nodes (not free supervisor-driven LLM-to-LLM routing) | Best fit for "production-ready": deterministic, testable, controllable cost; still uses specialized agents + deterministic tools | — Pending |
| Strategist + generic Solver (not one dedicated agent per algorithm type) for multi-solution generation | Avoids combinatorial agent sprawl while still surfacing brute-force + optimized (+ alternative) approaches | — Pending |
| Deterministic execution as tools, not agents (PythonExecutorTool, GoExecutorTool) | Keeps agent logic swappable from subprocess → sandbox → isolated service later without touching agent code | — Pending |
| Go code is compiled and executed/tested, not just generated as text | Product owner confirmed correctness must be verified for both Python and Go outputs | — Pending |
| taskiq + Redis over Celery/ARQ | Celery too heavyweight for this project; ARQ unsupported; taskiq fits FastAPI/asyncio naturally | ✓ Shipped Phase 1 — `RedisStreamBroker` wired end-to-end, live queued→completed round trip verified |
| LangGraph `StateGraph` + `langgraph-checkpoint-postgres`'s `AsyncPostgresSaver` under Python 3.14 | Research flagged Python 3.14 LangGraph compatibility as unconfirmed, with a documented 3.13 fallback | ✓ Confirmed Phase 1 — a compiled single-node `StateGraph` checkpoints real rows to Postgres under Python 3.14; no interpreter pin needed |
| Claude Code follows a BMAD-influenced (not literal) lifecycle: requirements → architecture → implementation plan → implementation → testing → review | Product owner wants fixed architecture and staged tasks without the overhead of literal BMAD role personas | — Pending |
| Full docs set (CLAUDE.md + docs/product, architecture, development, plans) generated alongside implementation | Product owner wants git history and specs to read as one coherent build, with deferred items tracked explicitly | — Pending |
| React + TypeScript frontend included in v1, not deferred | Product owner considers the web UI part of the initial deliverable, not a stretch goal | — Pending |
| Ambiguity handling uses real interactive pause/resume (`awaiting_clarification` status + answer endpoint), not stated-assumptions | Interview explicitly said "задавать вопрос"; research flagged the async task-queue architecture makes true interactivity non-trivial, but product owner confirmed the harder path over the cheaper default | — Pending |
| Difficulty rating, topic tags, edge-case callouts, and an approach-bridge narrative are in v1 | Research identified these as near-free byproducts of data the pipeline already produces (Analyzer, Strategist, Reviewer outputs) and baseline user expectations for this product category | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-22 after Phase 1*
