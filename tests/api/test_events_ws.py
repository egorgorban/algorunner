"""WebSocket events tests with guard implementations (API-04, API-05, T-04-02-02/03).

End-to-end tests of the status write -> Postgres -> Redis -> WS relay -> client path.
Also tests the two guards added in Plan 04-02:
- Origin allowlist (close 4403)
- Connection cap (close 1013)

All tests run against real Postgres and Redis through a real uvicorn server.
"""

import asyncio
from uuid import uuid4

import pytest
import websockets.asyncio.client
import websockets.exceptions
from psycopg_pool import AsyncConnectionPool

from algorunner.schemas.task import TaskStatus, Language, TaskSubmission
from algorunner.storage.tasks import (
    insert_task,
    update_task_status,
)
from algorunner.realtime.events import SnapshotEvent, StatusEvent


@pytest.fixture
async def _new_task(pg_pool: AsyncConnectionPool):
    """Insert a new task with QUEUED status."""

    async def _make(task_id=None):
        if task_id is None:
            task_id = uuid4()

        submission = TaskSubmission(
            problem_text="Test problem",
            language=Language.EN,
            examples=[],
        )
        await insert_task(pg_pool, task_id, submission)
        return task_id

    return _make


@pytest.mark.asyncio
async def test_ws_origin_allowlist_allowed(live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """With ws_allowed_origins set, Origin header in list -> connection accepted."""
    import algorunner.config as config_module
    import algorunner.api.routes.events as events_module

    task_id = await _new_task()

    # Monkeypatch settings to restrict to specific origin
    monkeypatch.setattr(config_module.settings, "ws_allowed_origins", ["http://allowed.test"])
    # Reset module-level counter
    events_module._active_connections = 0

    url = f"{live_server}/api/v1/tasks/{task_id}/events"
    extra_headers = {"Origin": "http://allowed.test"}

    # Should succeed
    async with websockets.asyncio.client.connect(url, additional_headers=extra_headers) as websocket:
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame = SnapshotEvent.model_validate_json(msg)
        assert frame.type == "snapshot"


@pytest.mark.asyncio
async def test_ws_origin_allowlist_denied(live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """With ws_allowed_origins set, Origin header NOT in list -> close 4403."""
    import algorunner.config as config_module
    import algorunner.api.routes.events as events_module

    task_id = await _new_task()

    # Monkeypatch settings to restrict to specific origin
    monkeypatch.setattr(config_module.settings, "ws_allowed_origins", ["http://allowed.test"])
    # Reset module-level counter
    events_module._active_connections = 0

    url = f"{live_server}/api/v1/tasks/{task_id}/events"
    extra_headers = {"Origin": "http://evil.test"}

    # Should fail with 4403
    try:
        async with websockets.asyncio.client.connect(url, additional_headers=extra_headers) as websocket:
            # If we reach here, the connection was accepted (should not happen)
            pytest.fail("Connection should have been rejected with 4403")
    except websockets.exceptions.InvalidStatusCode as e:
        # The rejection manifests as a 403 Forbidden or connection close with 4403
        assert "4403" in str(e) or "403" in str(e) or e.status_code in (403, 4403)


@pytest.mark.asyncio
async def test_ws_origin_absent_always_allowed(live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """Absent Origin header -> always allowed, even with ws_allowed_origins set (non-browser clients)."""
    import algorunner.config as config_module
    import algorunner.api.routes.events as events_module

    task_id = await _new_task()

    # Monkeypatch settings to restrict to specific origin
    monkeypatch.setattr(config_module.settings, "ws_allowed_origins", ["http://allowed.test"])
    # Reset module-level counter
    events_module._active_connections = 0

    url = f"{live_server}/api/v1/tasks/{task_id}/events"
    # No Origin header (non-browser client)

    # Should succeed
    async with websockets.asyncio.client.connect(url) as websocket:
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame = SnapshotEvent.model_validate_json(msg)
        assert frame.type == "snapshot"


@pytest.mark.asyncio
async def test_ws_connection_cap_exceeded(live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """With ws_max_connections=1 and one open socket, second connection closes with 1013."""
    import algorunner.config as config_module
    import algorunner.api.routes.events as events_module

    task_id1 = await _new_task()
    task_id2 = await _new_task()

    # Monkeypatch settings to cap at 1 connection
    monkeypatch.setattr(config_module.settings, "ws_max_connections", 1)
    # Reset module-level counter
    events_module._active_connections = 0

    url1 = f"{live_server}/api/v1/tasks/{task_id1}/events"
    url2 = f"{live_server}/api/v1/tasks/{task_id2}/events"

    # Open first connection
    async with websockets.asyncio.client.connect(url1) as websocket1:
        # Verify it's connected
        msg1 = await asyncio.wait_for(websocket1.recv(), timeout=2.0)
        assert SnapshotEvent.model_validate_json(msg1).type == "snapshot"

        # Try to open second connection (should be rejected with 1013)
        try:
            async with websockets.asyncio.client.connect(url2) as websocket2:
                # If we reach here, the connection was accepted (should not happen)
                pytest.fail("Second connection should have been rejected with 1013")
        except websockets.exceptions.InvalidStatusCode as e:
            # The rejection manifests as an error or connection close with 1013
            assert "1013" in str(e) or "429" in str(e) or e.status_code in (1013, 429)


@pytest.mark.asyncio
async def test_ws_connection_slot_released_on_disconnect(live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """After first socket closes, new connection succeeds (slot released)."""
    import algorunner.config as config_module
    import algorunner.api.routes.events as events_module

    task_id1 = await _new_task()
    task_id2 = await _new_task()

    # Monkeypatch settings to cap at 1 connection
    monkeypatch.setattr(config_module.settings, "ws_max_connections", 1)
    # Reset module-level counter
    events_module._active_connections = 0

    url1 = f"{live_server}/api/v1/tasks/{task_id1}/events"
    url2 = f"{live_server}/api/v1/tasks/{task_id2}/events"

    # Open and close first connection
    async with websockets.asyncio.client.connect(url1) as websocket1:
        msg1 = await asyncio.wait_for(websocket1.recv(), timeout=2.0)
        assert SnapshotEvent.model_validate_json(msg1).type == "snapshot"

    # Slot should be released; second connection should succeed
    await asyncio.sleep(0.1)  # Small delay to let cleanup happen
    async with websockets.asyncio.client.connect(url2) as websocket2:
        msg2 = await asyncio.wait_for(websocket2.recv(), timeout=2.0)
        assert SnapshotEvent.model_validate_json(msg2).type == "snapshot"
