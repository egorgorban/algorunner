"""WebSocket events tests (API-04, API-05).

End-to-end tests of the status write -> Postgres -> Redis -> WS relay -> client path.
All tests run against real Postgres and Redis through a real uvicorn server.
"""

import asyncio
from uuid import uuid4

import pytest
import websockets.asyncio.client
import websockets.exceptions
from psycopg_pool import AsyncConnectionPool

from algorunner.schemas.task import TaskStatus
from algorunner.storage.tasks import insert_task, update_task_status
from algorunner.realtime.events import StatusEvent, SnapshotEvent


@pytest.fixture
async def _new_task(pg_pool: AsyncConnectionPool):
    """Insert a new task with QUEUED status."""

    async def _make(task_id=None):
        if task_id is None:
            task_id = uuid4()
        from algorunner.schemas.task import TaskSubmission, Language

        submission = TaskSubmission(
            problem_text="Test problem",
            language=Language.EN,
            examples=[],
        )
        await insert_task(pg_pool, task_id, submission)
        return task_id

    return _make


@pytest.mark.asyncio
async def test_ws_tracer(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Tracer: status write -> Postgres -> Redis -> WS -> client."""
    task_id = await _new_task()
    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # First frame: snapshot with QUEUED status
        msg1 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame1 = SnapshotEvent.model_validate_json(msg1)
        assert frame1.type == "snapshot"
        assert frame1.task.status == TaskStatus.QUEUED
        initial_ts = frame1.task.updated_at

        # Update status to ANALYZING_PROBLEM
        await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)

        # Second frame: status event
        msg2 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame2 = StatusEvent.model_validate_json(msg2)
        assert frame2.type == "status"
        assert frame2.status == TaskStatus.ANALYZING_PROBLEM
        assert frame2.timestamp > initial_ts


@pytest.mark.asyncio
async def test_ws_late_connect(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Late connect: client receives current state first."""
    task_id = await _new_task()

    # Advance the task to REVIEWING before client connects
    await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)
    await asyncio.sleep(0.1)
    await update_task_status(pg_pool, task_id, TaskStatus.DESIGNING_SOLUTION)

    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # First frame: snapshot with DESIGNING_SOLUTION status
        msg1 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame1 = SnapshotEvent.model_validate_json(msg1)
        assert frame1.type == "snapshot"
        assert frame1.task.status == TaskStatus.DESIGNING_SOLUTION

        # No further events should arrive within a reasonable timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_ws_unknown_task(live_server: str):
    """Unknown task: connection closes with code 4404."""
    unknown_id = uuid4()
    url = f"{live_server}/api/v1/tasks/{unknown_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # The server will close the connection with code 4404
        try:
            await websocket.recv()
        except websockets.exceptions.ConnectionClosedOK as e:
            # The connection was closed with a close frame
            assert e.rcvd.code == 4404
        except websockets.exceptions.ConnectionClosed as e:
            # Check if the close code was 4404
            if e.rcvd and e.rcvd.code == 4404:
                pass  # Expected
            else:
                raise
