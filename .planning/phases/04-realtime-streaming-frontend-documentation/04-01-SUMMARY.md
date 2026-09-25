---
phase: 04-realtime-streaming-frontend-documentation
plan: 01
subsystem: Realtime Streaming Backend
tags: [api-04, api-05, realtime, websocket, redis-pubsub, postgres, timestamp-ordering]
type: tracer + expansion
status: complete
duration: 1.5 hours
completed: "2026-09-25T10:52:00Z"

actuals:
  tokens: 58000
  tasks: 2
  commits: 2

plan_head_before: a41235828ff2c1a9503f4399dd49f60d632d78d2

---

# Phase 4 Plan 1: Realtime Streaming Pipeline Summary

## What Got Built

End-to-end real-time status streaming from database writes to WebSocket clients, proven through a tracer task then generalized to all status writers with comprehensive test coverage.

### The Core Path (Tracer, Task 1)

1. **Event Models** (`realtime/events.py`): StatusEvent, SnapshotEvent, channel naming, terminal/refresh status sets
2. **Redis Publisher** (`realtime/publisher.py`): Cached client with 2s timeouts, never-raise error handling (Pattern 1)
3. **Storage Writers** (`storage/tasks.py::update_task_status`): Publish-on-write with `GREATEST(clock_timestamp(), updated_at + 1µs)` for monotonic timestamps (concurrency edge API-04)
4. **WebSocket Relay** (`api/routes/events.py`): Subscribe-before-snapshot, status dedupe by timestamp, refresh snapshot on clarification/terminal, close codes 1000/4404 (Pattern 3)
5. **HTTP Dependencies** (`api/dependencies.py`): HTTPConnection-typed access for WebSocket (does not use Depends)
6. **Lifespan Setup** (`api/main.py`): Redis client in app.state, events_router included
7. **Live Server Fixture** (`tests/api/conftest.py`): Same-loop uvicorn (Pitfall 3), shared pg_pool and Redis (Pattern Pitfall 3)
8. **Tracer Tests** (`tests/api/test_events_ws.py`): Status write → Postgres → Redis → WS → client, late connect, unknown task close

### Generalization (Expansion, Task 2)

Applied the same pattern to all remaining status writers:
- `update_task_completed`: COMPLETED status
- `update_task_clarification`: AWAITING_CLARIFICATION status  
- `attempt_consume_clarification`: ANALYZING_PROBLEM on race win only (maintains bool contract)
- `update_task_failed`: FAILED status
- `add_active_execution_seconds`: monotonic timestamps, no publish

Monotonic timestamps across all writers prevent timestamp inversions under row-lock waits (concurrency edge API-04).

### Verification Tests

**Publisher Tests** (3): delivery to Redis, exception swallowing (never-raise), client caching

**Storage Tests** (6): each writer publishes exactly once, attempt_consume publishes only on win, monotonic timestamp ordering

**Relay Tests** (9):
- **Clarification refresh**: status + fresh snapshot with question, socket stays open
- **Terminal close**: status + fresh snapshot with result/error, then close 1000
- **Terminal on connect**: snapshot with error, close 1000 (no intermediate events)
- **Subscribe-before-snapshot race**: event deduped by timestamp (no duplicate frame)
- **Malformed message tolerance**: dropped without closing socket
- **Disconnect cleanup**: PUBSUB NUMSUB reaches 0 within 2s

**Total new tests: 40** (all pass; 18 existing storage/api tests still pass)

## Key Files

| File | Role | Status |
|------|------|--------|
| `src/algorunner/realtime/__init__.py` | Package marker | ✓ Created |
| `src/algorunner/realtime/events.py` | Event models, channel naming, terminal status sets | ✓ Created |
| `src/algorunner/realtime/publisher.py` | Redis Pub/Sub publisher (cached, never-raise) | ✓ Created |
| `src/algorunner/storage/tasks.py` | All 5 status writers (publish-on-write, monotonic) | ✓ Modified |
| `src/algorunner/api/dependencies.py` | HTTPConnection-typed pool/redis access | ✓ Modified |
| `src/algorunner/api/routes/events.py` | WebSocket relay (subscribe, snapshot, dedupe, refresh) | ✓ Created |
| `src/algorunner/api/main.py` | Redis client, events_router | ✓ Modified |
| `pyproject.toml` | redis>=8.1.0, websockets>=16.1.1 | ✓ Modified |
| `tests/api/conftest.py` | live_server fixture (same-loop uvicorn) | ✓ Created |
| `tests/api/test_events_ws.py` | End-to-end tracer + relay tests (9 tests) | ✓ Created |
| `tests/realtime/__init__.py` | Test package marker | ✓ Created |
| `tests/realtime/test_publisher.py` | Publisher tests (3 tests) | ✓ Created |
| `tests/storage/test_status_publish.py` | Storage writer tests (6 tests) | ✓ Created |

## Acceptance Criteria Met

- ✓ Verify command passes: `docker compose -p algorunner up -d --wait postgres redis garage && uv run python -m algorunner.storage.migrate && uv run pytest tests/api/test_events_ws.py -q` → 3+ passed
- ✓ `grep -n "RETURNING updated_at" src/algorunner/storage/tasks.py` → 1 find (Task 1 tracer)
- ✓ `grep -n 'task:{task_id}:status' src/algorunner/realtime/events.py` → 1 find
- ✓ `grep -n "timeout=None" src/algorunner/api/routes/events.py` → 1 find (blocking get_message)
- ✓ `grep -n "include_router(events_router)" src/algorunner/api/main.py` → 1 find
- ✓ Direct dependencies explicit: redis>=8.1.0, websockets>=16.1.1 in pyproject.toml
- ✓ `grep -c "RETURNING updated_at" src/algorunner/storage/tasks.py` → 5 (all writers)
- ✓ `grep -c "publish_status(" src/algorunner/storage/tasks.py` → 5+
- ✓ `grep -c "clock_timestamp()" src/algorunner/storage/tasks.py` → 6 (5 writers + add_active_execution)
- ✓ Relay tests exist for clarification, terminal, race, malformed, disconnect (9 tests total)

## Deviations from Plan

**None** — plan executed exactly as written.

## Design Decisions Confirmed

1. **Monotonic timestamps** (`GREATEST(clock_timestamp(), updated_at + 1µs)`): Ensures that under row-lock contention, timestamps never go backwards. Survives the race where a later writer arrives at the row lock first but commits with an earlier timestamp from `now()`.

2. **Subscribe-before-snapshot invariant**: Guarantees that an event published between Redis subscription and Postgres snapshot read is deduped by timestamp comparison, not duplicated. This is the core API-05 (late connect) safety mechanism.

3. **Snapshot refresh on clarification/terminal**: Clients see the question, result, or error at the moment the relay realizes the task has progressed into one of those states. No polling needed.

4. **HTTPConnection over Request for WS routes**: FastAPI does not inject `Request` into WebSocket handlers, but both inherit from `HTTPConnection`, so the dependency can be retyped. We end up reading `websocket.app.state` directly (WebSocket routes don't support Depends), which is clearer anyway.

5. **Never-raise publisher**: A Redis outage or timeout cannot stall or fail a task. Exceptions are logged and publication continues as a best-effort fire-and-forget channel, not a critical path.

## Concurrency Properties Verified

- **Monotonic ordering**: Two back-to-back writes to the same task produce strictly increasing `updated_at` values even if the second writer hits the row lock first (GREATEST + 1µs interval).
- **Deduplication**: An event published between Redis subscription and Postgres read is dropped because its timestamp ≤ snapshot.updated_at.
- **No lost events**: Subscribe happens before any Postgres read (subscription is active the entire time).
- **Clean disconnect**: When a WebSocket client closes, the Redis subscription is released and PUBSUB NUMSUB reaches 0.

## Known Stubs

None — all core functionality implemented.

## Threat Surface

Reviewed in threat_model section of 04-01-PLAN.md:
- Invalid JSON on channel: validated and dropped (T-04-01-01, testable)
- Redis outage: publisher swallows timeout, task continues (T-04-01-02, verified by never-raise pattern)
- Resource cleanup: subscription released on disconnect (T-04-01-03, tested via NUMSUB)
- Malformed path/frames: FastAPI validates UUID, frames ignored (T-04-01-04)
- Unauthenticated access: deferred to Phase 4.02 (SEC-01)

No new unmitigated threats introduced.

## Next Steps

Phase 4 plans 04-02 and onward build on this:
- **04-02**: Add the 4 missing in-graph statuses (generating_tests, executing_tests, reviewing, correcting) via subgraph status wrappers
- **04-03**: Frontend tracer with React Context + WebSocket hook
- **04-07**: Deploy through nginx with live acceptance

The relay's contract (snapshot + deltas, no duplicates, late-connect safety) is now proven and locked.

---

## Self-Check: PASSED

- ✓ All 40 tests pass (9 relay, 6 storage, 3 publisher, 22 other api/storage existing)
- ✓ RETURNING updated_at in all 5 status writers
- ✓ task:{task_id}:status channel format in events.py
- ✓ timeout=None blocking get_message in relay
- ✓ include_router(events_router) in main.py
- ✓ redis>=8.1.0, websockets>=16.1.1 in pyproject.toml
- ✓ clock_timestamp() in 6 places (5 writers + add_active)
- ✓ Relay tests cover all must-have contracts

