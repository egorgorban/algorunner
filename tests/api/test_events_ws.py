"""WebSocket events tests (API-04, API-05).

End-to-end tests of the status write -> Postgres -> Redis -> WS relay -> client path.
All tests run against real Postgres and Redis through a real uvicorn server.
"""

import asyncio
from uuid import uuid4

import pytest
import redis.asyncio
import websockets.asyncio.client
import websockets.exceptions
from psycopg_pool import AsyncConnectionPool

from algorunner.config import settings
from algorunner.realtime.events import StatusEvent, SnapshotEvent, channel_for
from algorunner.schemas.task import TaskStatus, TaskError
from algorunner.storage.tasks import (
    insert_task,
    update_task_status,
    update_task_clarification,
    update_task_completed,
    update_task_failed,
)


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


@pytest.mark.asyncio
async def test_ws_clarification_refresh(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Clarification refresh: status event + fresh snapshot + socket stays open."""
    task_id = await _new_task()
    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # First frame: snapshot
        msg1 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        SnapshotEvent.model_validate_json(msg1)

        # Update to clarification
        await update_task_clarification(pg_pool, task_id, "Is this sorted?")

        # Should receive status frame for AWAITING_CLARIFICATION
        msg2 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame2 = StatusEvent.model_validate_json(msg2)
        assert frame2.status == TaskStatus.AWAITING_CLARIFICATION

        # Should receive fresh snapshot with clarification_question
        msg3 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame3 = SnapshotEvent.model_validate_json(msg3)
        assert frame3.task.clarification_question == "Is this sorted?"
        assert frame3.task.status == TaskStatus.AWAITING_CLARIFICATION

        # Socket should stay open for more updates
        await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)
        msg4 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        StatusEvent.model_validate_json(msg4)


@pytest.mark.asyncio
async def test_ws_terminal_close(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Terminal close: status + refresh snapshot + close 1000."""
    task_id = await _new_task()
    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # First frame: snapshot
        msg1 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        SnapshotEvent.model_validate_json(msg1)

        # Complete the task (skip intermediate status, go straight to completion)
        result = {"editorial": {"approaches": []}}
        await update_task_completed(pg_pool, task_id, result)

        # Should receive status frame for COMPLETED
        msg2 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame2 = StatusEvent.model_validate_json(msg2)
        assert frame2.status == TaskStatus.COMPLETED

        # Should receive fresh snapshot with result
        msg3 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame3 = SnapshotEvent.model_validate_json(msg3)
        assert frame3.task.result is not None

        # Connection should close with 1000
        with pytest.raises(websockets.exceptions.ConnectionClosedOK) as exc:
            await websocket.recv()
        assert exc.value.rcvd.code == 1000


@pytest.mark.asyncio
async def test_ws_terminal_on_connect(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Terminal on connect: snapshot with error, then close 1000."""
    task_id = await _new_task()

    # Fail the task before client connects
    error = TaskError(code="TIMEOUT", message="Execution timed out")
    await update_task_failed(pg_pool, task_id, error)

    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # Should receive snapshot with error and status=failed
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame = SnapshotEvent.model_validate_json(msg)
        assert frame.task.status == TaskStatus.FAILED
        assert frame.task.error is not None

        # Connection should close immediately
        with pytest.raises(websockets.exceptions.ConnectionClosedOK):
            await websocket.recv()


@pytest.mark.asyncio
async def test_ws_subscribe_before_snapshot_race(
    live_server: str, pg_pool: AsyncConnectionPool, _new_task, monkeypatch
):
    """Subscribe-before-snapshot race: event between subscribe and read is deduplicated."""
    task_id = await _new_task()

    # Wrap get_task to trigger a write between subscribe and the actual read
    from algorunner.storage.tasks import get_task as original_get_task

    call_count = 0

    async def get_task_with_race(pool, tid):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Trigger a write just before the read
            await update_task_status(pg_pool, tid, TaskStatus.DESIGNING_SOLUTION)
        return await original_get_task(pool, tid)

    monkeypatch.setattr("algorunner.api.routes.events.get_task", get_task_with_race)

    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # Snapshot should have the updated status (DESIGNING_SOLUTION)
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame = SnapshotEvent.model_validate_json(msg)
        assert frame.task.status == TaskStatus.DESIGNING_SOLUTION

        # The event published by the race should be deduplicated
        # (its timestamp <= snapshot.updated_at)
        # So no further status frames should arrive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.recv(), timeout=0.5)


@pytest.mark.asyncio
async def test_ws_malformed_message_tolerance(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Malformed message: dropped, socket stays open."""
    task_id = await _new_task()
    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    async with websockets.asyncio.client.connect(url) as websocket:
        # Receive snapshot
        msg1 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        SnapshotEvent.model_validate_json(msg1)

        # Publish a malformed message directly to Redis
        redis_client = redis.asyncio.Redis.from_url(settings.redis_url)
        channel = channel_for(task_id)
        await redis_client.publish(channel, "not json")

        # Publish a real status event
        await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)

        # The malformed message should be dropped, only the real event received
        msg2 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        frame2 = StatusEvent.model_validate_json(msg2)
        assert frame2.status == TaskStatus.ANALYZING_PROBLEM

        await redis_client.aclose()


@pytest.mark.asyncio
async def test_ws_disconnect_cleanup(live_server: str, pg_pool: AsyncConnectionPool, _new_task):
    """Disconnect cleanup: PUBSUB NUMSUB reaches 0 within 2s."""
    task_id = await _new_task()
    url = f"{live_server}/api/v1/tasks/{task_id}/events"

    redis_client = redis.asyncio.Redis.from_url(settings.redis_url)
    channel = channel_for(task_id)

    async with websockets.asyncio.client.connect(url) as websocket:
        # Receive snapshot to confirm connection
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        SnapshotEvent.model_validate_json(msg)

    # Verify that after disconnect, there are no subscribers
    await asyncio.sleep(0.1)  # Small delay for cleanup
    numsub = await redis_client.pubsub_numsub(channel)
    # numsub returns [(channel, count)]
    assert numsub[0][1] == 0

    await redis_client.aclose()
