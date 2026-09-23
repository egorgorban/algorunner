import asyncio
from uuid import uuid4

from algorunner.schemas.task import Language, TaskError, TaskStatus, TaskSubmission
from algorunner.storage.tasks import (
    attempt_consume_clarification,
    get_task,
    insert_task,
    update_task_clarification,
    update_task_completed,
    update_task_failed,
    update_task_status,
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
    assert task.clarification_question is None


async def test_concurrent_consume_has_single_winner(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    results = await asyncio.gather(
        *(attempt_consume_clarification(pg_pool, task_id) for _ in range(5))
    )
    assert results.count(True) == 1
    task = await get_task(pg_pool, task_id)
    assert task.status == TaskStatus.ANALYZING_PROBLEM
    assert task.clarification_question is None


async def test_consume_unknown_task_returns_false(pg_pool):
    assert await attempt_consume_clarification(pg_pool, uuid4()) is False


async def test_consume_clears_question_and_stays_cleared_after_completion(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    before = await get_task(pg_pool, task_id)
    assert before.status == TaskStatus.AWAITING_CLARIFICATION
    assert before.clarification_question == "which array?"

    assert await attempt_consume_clarification(pg_pool, task_id) is True
    after = await get_task(pg_pool, task_id)
    assert after.clarification_question is None
    assert after.status == TaskStatus.ANALYZING_PROBLEM

    await update_task_completed(pg_pool, task_id, {"ok": True})
    done = await get_task(pg_pool, task_id)
    assert done.status == TaskStatus.COMPLETED
    assert done.clarification_question is None


async def test_question_stays_cleared_after_failure(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    assert await attempt_consume_clarification(pg_pool, task_id) is True
    await update_task_failed(pg_pool, task_id, TaskError(code="X", message="boom"))
    task = await get_task(pg_pool, task_id)
    assert task.status == TaskStatus.FAILED
    assert task.clarification_question is None
    assert task.error is not None


async def test_second_round_stores_new_question_then_consume_clears_it(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    assert await attempt_consume_clarification(pg_pool, task_id) is True
    await update_task_clarification(pg_pool, task_id, "what is the range of n?")
    task = await get_task(pg_pool, task_id)
    assert task.status == TaskStatus.AWAITING_CLARIFICATION
    assert task.clarification_question == "what is the range of n?"

    assert await attempt_consume_clarification(pg_pool, task_id) is True
    task = await get_task(pg_pool, task_id)
    assert task.clarification_question is None
    assert task.status == TaskStatus.ANALYZING_PROBLEM


async def test_failed_consume_leaves_row_untouched(pg_pool):
    task_id = await _make_awaiting(pg_pool)
    await update_task_status(pg_pool, task_id, TaskStatus.QUEUED)
    assert await attempt_consume_clarification(pg_pool, task_id) is False
    task = await get_task(pg_pool, task_id)
    assert task.status == TaskStatus.QUEUED
    assert task.clarification_question == "which array?"
