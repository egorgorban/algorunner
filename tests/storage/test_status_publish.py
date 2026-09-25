"""Tests for status writer publish-on-write behavior and monotonic timestamps."""

from uuid import uuid4

import pytest
from psycopg_pool import AsyncConnectionPool

from algorunner.schemas.task import TaskStatus, TaskSubmission, Language, TaskError
from algorunner.storage.tasks import (
    insert_task,
    update_task_status,
    update_task_completed,
    update_task_clarification,
    attempt_consume_clarification,
    update_task_failed,
    get_task,
)


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
async def test_update_task_status_publishes(pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """update_task_status publishes exactly once."""
    task_id = await _new_task()
    published = []

    async def mock_publish(tid, status, timestamp):
        published.append((tid, status, timestamp))

    monkeypatch.setattr("algorunner.storage.tasks.publish_status", mock_publish)

    await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)

    assert len(published) == 1
    assert published[0][0] == task_id
    assert published[0][1] == TaskStatus.ANALYZING_PROBLEM


@pytest.mark.asyncio
async def test_update_task_completed_publishes(pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """update_task_completed publishes with COMPLETED status."""
    task_id = await _new_task()
    published = []

    async def mock_publish(tid, status, timestamp):
        published.append((tid, status, timestamp))

    monkeypatch.setattr("algorunner.storage.tasks.publish_status", mock_publish)

    result = {"editorial": {"approaches": []}}
    await update_task_completed(pg_pool, task_id, result)

    assert len(published) == 1
    assert published[0][1] == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_attempt_consume_clarification_publishes_on_win(pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """attempt_consume_clarification publishes ANALYZING_PROBLEM when it wins."""
    task_id = await _new_task()

    # Set up clarification
    await update_task_clarification(pg_pool, task_id, "Is the problem sorted?")
    published_records = []

    async def mock_publish(tid, status, timestamp):
        published_records.append((tid, status, timestamp))

    monkeypatch.setattr("algorunner.storage.tasks.publish_status", mock_publish)

    # Attempt to consume
    result = await attempt_consume_clarification(pg_pool, task_id)

    assert result is True
    # Should have 3 publishes: clarification, then consume
    # (clarification already happened with the real publisher, so we only see the consume)
    assert len([p for p in published_records if p[1] == TaskStatus.ANALYZING_PROBLEM]) >= 1


@pytest.mark.asyncio
async def test_attempt_consume_clarification_returns_false_on_race_loss(pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """attempt_consume_clarification returns False and doesn't publish on race loss."""
    task_id = await _new_task()

    # Set up clarification
    await update_task_clarification(pg_pool, task_id, "Is the problem sorted?")

    # First consumer wins
    result1 = await attempt_consume_clarification(pg_pool, task_id)
    assert result1 is True

    # Second consumer loses
    published = []

    async def mock_publish(tid, status, timestamp):
        published.append((tid, status, timestamp))

    monkeypatch.setattr("algorunner.storage.tasks.publish_status", mock_publish)

    result2 = await attempt_consume_clarification(pg_pool, task_id)
    assert result2 is False
    assert len(published) == 0


@pytest.mark.asyncio
async def test_status_write_completes_before_publish(pg_pool: AsyncConnectionPool, _new_task, monkeypatch):
    """Status write commits before publish (Postgres first, Redis second)."""
    task_id = await _new_task()

    publish_called_after_write = None

    async def mock_publish_after_check(*args, **kwargs):
        nonlocal publish_called_after_write
        # Check that the task status has already been written
        task = await get_task(pg_pool, task_id)
        publish_called_after_write = (task is not None and task.status == TaskStatus.ANALYZING_PROBLEM)

    monkeypatch.setattr("algorunner.storage.tasks.publish_status", mock_publish_after_check)

    # Call update_task_status
    await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)

    # Verify that publish was called after the write
    assert publish_called_after_write is True


@pytest.mark.asyncio
async def test_monotonic_timestamps(pg_pool: AsyncConnectionPool, _new_task):
    """Consecutive writes produce strictly increasing updated_at values."""
    task_id = await _new_task()

    # Get initial timestamp
    task1 = await get_task(pg_pool, task_id)
    ts1 = task1.updated_at

    # Write 1
    await update_task_status(pg_pool, task_id, TaskStatus.ANALYZING_PROBLEM)
    task2 = await get_task(pg_pool, task_id)
    ts2 = task2.updated_at

    # Write 2
    await update_task_status(pg_pool, task_id, TaskStatus.DESIGNING_SOLUTION)
    task3 = await get_task(pg_pool, task_id)
    ts3 = task3.updated_at

    # Verify strictly increasing
    assert ts2 > ts1
    assert ts3 > ts2
