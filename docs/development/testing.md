# Testing Guide

## Backend Tests

### Setup & Dependencies

Before running tests, set up your environment:

```bash
# Install dependencies
uv sync

# Start required services for integration tests
docker compose -p algorunner up -d postgres redis garage
```

The `-p algorunner` project name isolates your worktree's containers from the main dev environment, preventing port conflicts.

### Running Tests

Backend tests require a real Postgres and Redis (mocked OpenAI). All tests are async and share a session-wide event loop ([`asyncio_default_fixture_loop_scope = "session"`](../../pyproject.toml#L44) in `pyproject.toml`).

```bash
# Full test suite
pytest

# Single test file
pytest tests/api/test_events_ws.py

# Single test function
pytest tests/graph/test_status_emission.py::test_status_emitted_on_node_boundary
```

### Test Fixtures

All fixtures are defined in `tests/conftest.py` (session scope) and `tests/api/conftest.py` (function scope):

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `pg_pool` | session | `AsyncConnectionPool` to the test Postgres, migrated once per session |
| `app_client` | function | `AsyncClient` (ASGI transport) for REST API tests; bypasses FastAPI lifespan and uses the shared `pg_pool` |
| `live_server` | function | Real uvicorn server on a random port, running on the same event loop as the test; enables real WebSocket and Pub/Sub testing |
| `mock_openai_parse` | function | Monkeypatches `client_factory.get_client()` to return a fake client whose `parse` returns canned `ProblemAnalysis`; used for single-node agent tests |
| `mock_pipeline_openai` | function | Full pipeline mock: `parse` returns side-effects (one per agent call in order): analyzer, strategist, solver (2x), code_gen (2x), test_gen (2x), reviewer (2x), editorial_writer; used for end-to-end graph tests |

**Key rule:** Always monkeypatch module attributes, not imported names. For example, patch `client_factory_module.get_client`, not a name imported as `from algorunner.llm.client_factory import get_client`. This ensures the patch applies regardless of import order ([`tests/conftest.py` line 81](../../tests/conftest.py#L81)).

### Test Loop Scope

The session-wide loop (`asyncio_default_fixture_loop_scope = "session"`) means:
- All tests in a session share one event loop.
- The `pg_pool` fixture opens once at the start, closes once at the end.
- Each test function runs synchronously in the loop, not in a separate thread.
- This is required for real Postgres/Redis testing (neither can be used from multiple threads).

### Test Examples

**Single-node test (analyzer):**
```python
async def test_analyzer_output(mock_openai_parse):
    result = await analyze_problem(client_factory.get_client(), ...)
    assert result.difficulty == "easy"
```

**Full graph test:**
```python
async def test_graph_end_to_end(mock_pipeline_openai, pg_pool, app_client):
    # Graph runs, calls the mocked client in order, emits statuses
    response = await app_client.post("/api/v1/tasks", json={...})
    task_id = response.json()["id"]
    # Status emitted to Postgres and Redis
    result = await app_client.get(f"/api/v1/tasks/{task_id}")
    assert result.json()["status"] == "completed"
```

**WebSocket test:**
```python
async def test_websocket_events(live_server, mock_pipeline_openai):
    async with websockets.connect(f"{live_server}/api/v1/tasks/{task_id}/events") as ws:
        # Receive initial snapshot + live status updates
        msg = await ws.recv()
        assert msg["status"] == "designing_solution"
```

### Environment Notes

On macOS with worktree venvs, if `import algorunner` fails, fix the hidden-file flag:
```bash
chflags nohidden /path/to/venv/lib/python3.14/site-packages/algorunner.pth
```

#### Placeholder `.env`

For mocked unit tests (using `mock_openai_parse`), the `.env` can be empty or minimal since no real OpenAI calls are made:

```
# Placeholder for worktree tests (real calls not made)
OPENAI_API_KEY=sk-test
DATABASE_URL=postgresql://algorunner:algorunner@localhost:5432/algorunner
REDIS_URL=redis://localhost:6379
```

Integration tests and live probes (see below) require a real `OPENAI_API_KEY`.

---

## Frontend Tests

### Unit Tests

```bash
npm --prefix frontend test
```

Runs vitest in `node` environment (not browser). Tests live in `src/**/*.test.ts` alongside their modules. No Starlette TestClient equivalent; just pure module exports and mocked sockets/timers.

### Live Integration Tests

```bash
npm --prefix frontend run test:live
```

Requires a running backend (api and worker services). Runs tests in `src/**/*.integration.test.ts` with the same loop, hitting real WebSocket and HTTP endpoints. Timeout is 120 seconds per test.

---

## Live Probes

Three scripts in `scripts/` verify the entire system end-to-end:

| Script | Purpose | OK Marker |
|--------|---------|-----------|
| `verify_phase3_live.py` | Core backend: task creation, status polling, editorial retrieval | `PHASE3_LIVE_OK` |
| `verify_phase4_live.py` | WebSocket streaming, clarification flow, gateway reverse proxy (with `--gateway-only`) | `PHASE4_LIVE_OK` or `PHASE4_GATEWAY_OK` |
| `verify_executor_isolation.py` | Executor process group isolation, signal handling on timeout | (no marker; exits 0 on pass) |

Run them with Docker Compose up:

```bash
docker compose -p algorunner up -d
sleep 10  # Wait for services to be healthy
uv run python scripts/verify_phase4_live.py

# For gateway-only tests (faster, skips some checks)
uv run python scripts/verify_phase4_live.py --gateway-only
```

**Note:** Full runs can take up to 20 minutes (5-minute editorial generation timeout per task).

---

## Test Patterns

### Async & Event Loop

- All test functions are `async def`; pytest-asyncio automatically schedules them on the session loop.
- No need for `async_to_sync` wrappers; the loop is reused per session.
- WebSocket tests can use real `websockets` library alongside Redis Pub/Sub in the same loop.

### Mocking OpenAI

- Use `mock_openai_parse` for single-node tests.
- Use `mock_pipeline_openai` for multi-node or full-graph tests.
- Always patch the module reference, not imported names.

### Fixtures Don't Need Cleanup

- `pg_pool` is opened once, closed at session end.
- `app_client` and `live_server` are function-scoped; pytest handles cleanup.

### No TestClient for WebSockets

Starlette's `TestClient` runs in a separate event loop and cannot be used for WebSocket or Pub/Sub testing. Always use `live_server` (a real uvicorn server on the test loop) for these cases.
