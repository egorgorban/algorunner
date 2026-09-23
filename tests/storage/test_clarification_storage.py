import asyncio
from uuid import uuid4

from algorunner.schemas.task import Language, TaskStatus, TaskSubmission
from algorunner.storage.tasks import (
    attempt_consume_clarification,
    get_task,
    insert_task,
    update_task_clarification,
)


async def _make_awaiting(pg_pool):
    task_id = uuid4()
    await insert_task(pg_pool, task_id, TaskSubmission(problem_text="x", language=Language.EN))
    await update_task_clarification(pg_pool, task_id, "which array?")
    return task_id


async def test_consume_returns_true_exactly_once(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    assert await attempt_consume_clarification(pg_pool, task_id) is True
    assert await attempt_consume_clarification(pg_pool, task_id) is False
    task = await get_task(pg_pool, task_id)
    assert task.status == TaskStatus.ANALYZING_PROBLEM
    assert task.clarification_question == "which array?"


async def test_concurrent_consume_has_single_winner(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    results = await asyncio.gather(
        *(attempt_consume_clarification(pg_pool, task_id) for _ in range(5))
    )
    assert results.count(True) == 1


async def test_consume_unknown_task_returns_false(pg_pool):
    assert await attempt_consume_clarification(pg_pool, uuid4()) is False
