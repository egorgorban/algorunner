# Walking Skeleton — AlgoRunner

**Phase:** 1
**Generated:** 2026-09-22

## Capability Proven End-to-End

A user can POST a problem submission to `POST /api/v1/tasks` and watch it move through the real task lifecycle — `queued` -> `analyzing_problem` -> `completed`/`failed` — on a live, containerized stack (FastAPI + taskiq/Redis worker + PostgreSQL, checkpointed via LangGraph), verified by polling `GET /api/v1/tasks/{id}`, with zero AI logic in the loop yet.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Package structure | Single `uv`-managed package `algorunner` at repo root (`src/algorunner/{schemas,storage,worker,api,agents,tools,graph}/`) — NOT a `uv` workspace | INFRA-01 + ROADMAP/STATE.md explicitly lock this; `.planning/research/STACK.md`'s workspace variant is superseded by this decision for this project (01-RESEARCH.md documents and resolves the conflict) |
| Data layer | PostgreSQL 18, `psycopg[binary,pool]` v3 (AsyncConnectionPool, `autocommit=True`, `row_factory=dict_row`), hand-rolled numbered-SQL-file migration runner (not Alembic/SQLAlchemy) | DATA-01 mandates Postgres as the task-state source of truth; a single `tasks` table this phase doesn't justify an ORM/migration framework dependency |
| Queue | taskiq + `taskiq-redis` `RedisStreamBroker` (explicit `unacknowledged_lock_timeout`), not Celery/ARQ | Fixed by product-owner constraint; `RedisStreamBroker` chosen over `ListQueueBroker`/`PubSubBroker` for ack-based durability (QUEUE-01) |
| Orchestration checkpoint | LangGraph `StateGraph` + `AsyncPostgresSaver`, wired now (a trivial single-node stub graph) even though real pipeline logic doesn't exist until Phase 2 | D-12: doubles as the Python 3.14/LangGraph compatibility smoke test STATE.md flagged as a risk (confirmed resolved by 01-RESEARCH.md's direct execution, and re-proven by this phase's own tests) |
| Auth | None | SEC-01 explicitly deferred to a future milestone; no auth boundary exists in v1 |
| Deployment target | Docker Compose (5 services: postgres, redis, garage, api, worker); Kubernetes explicitly deferred | INFRA-02; single-node local/dev-scale target for this milestone |
| Artifact storage | Garage (S3-compatible) runs in Compose but has zero client wiring this phase | D-11: real integration is Phase 3's job (DATA-02) |
| Status vocabulary | Full 12-value `TaskStatus` enum defined now (`queued` through `failed`), stored as `VARCHAR(32)`, validated by an app-level Python `Enum`, not a native Postgres `ENUM` type | D-08, D-10: front-loads the eventual full pipeline's status contract; additive migrations only from here forward |
| Directory layout | `schemas/`, `storage/`, `worker/`, `api/{routes/}`, `agents/` (empty), `tools/` (empty), `graph/`, mirrored by `tests/{api,worker,graph}/` | INFRA-01's mandated modular structure; `agents/`/`tools/` exist now as empty packages so Phase 2 doesn't need a restructure |

## Stack Touched in Phase 1

- [x] Project scaffold (`uv`-managed `pyproject.toml`, Python 3.14, `pytest`/`pytest-asyncio`/`httpx` for tests)
- [x] Routing — `POST /api/v1/tasks` and `GET /api/v1/tasks/{id}`, both real routes with real validation
- [x] Database — real write (`INSERT INTO tasks` on submission) AND real read (`GET` reflects the live Postgres row; worker `UPDATE`s status as it progresses)
- [x] "UI" (no frontend exists until Phase 4) — the equivalent interactive element wired to the API is the full submit -> queue -> worker -> poll round trip via curl/pytest, exercised end-to-end
- [x] Deployment — `docker compose up -d --build` brings up all 5 services on a real container stack (not just documented, actually run and verified in Plan 01-01 Task 2 and Plan 01-02 Task 3)

## Out of Scope (Deferred to Later Slices)

- Problem Analyzer, Solution Strategist, Solver, Code Generator, Test Generator, real executors, Reviewer, correction loop, Editorial Writer — all Phase 2/3 (no AI logic exists in Phase 1 by explicit phase boundary)
- `openai` SDK — not installed this phase; no LLM call exists yet (deferred to Phase 2, where the v1-vs-v2-vs-v3 SDK pin decision also belongs)
- Garage client wiring / bucket creation (`aioboto3`/`boto3`) — container runs, nothing calls it (D-11; real wiring is Phase 3's DATA-02)
- WebSocket streaming (`WS /api/v1/tasks/{id}/events`), React/TypeScript frontend — Phase 4 (API-04/05, UI-01..04)
- Authentication, sandboxed code execution, resource limits on generated code — deferred v2 items, out of scope for this entire milestone
- `awaiting_clarification` pause/resume flow — the status exists in the enum now (D-08) but nothing reaches it yet; real clarification logic is Phase 2 (INTAKE-04/05)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: Verified Single-Solution Core Pipeline — Analyzer, generic Solver, dual-language code generation, real Python/Go execution, Reviewer, bounded correction loop; the LangGraph stub graph this phase wired becomes the real multi-node pipeline graph; `openai` SDK is added and pinned here
- Phase 3: Multi-Approach Editorial & Persistence — multiple curated approaches, the final Russian-language editorial article, Garage artifact persistence goes live (DATA-02)
- Phase 4: Realtime Streaming, Frontend & Documentation — WebSocket status streaming, the React + TypeScript web UI, and the full documentation set
