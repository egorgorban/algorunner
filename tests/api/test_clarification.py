import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from algorunner.schemas.task import Language, TaskSubmission
from algorunner.storage.tasks import (
    insert_task,
    update_task_clarification,
    update_task_completed,
)
from algorunner.worker.tasks import resume_task_with_clarification


@pytest.fixture
def kiq_mock(monkeypatch) -> AsyncMock:
    # No worker consumes the resume in API tests; assert enqueue behavior only.
    mock = AsyncMock()
    monkeypatch.setattr(resume_task_with_clarification, "kiq", mock)
    return mock


async def _awaiting_task(pg_pool, question: str = "Which array?"):
    task_id = uuid4()
    await insert_task(pg_pool, task_id, TaskSubmission(problem_text="x", language=Language.EN))
    await update_task_clarification(pg_pool, task_id, question)
    return task_id


async def test_get_clarification_404_when_not_awaiting(app_client, pg_pool):
    task_id = uuid4()
    await insert_task(pg_pool, task_id, TaskSubmission(problem_text="x", language=Language.EN))
    assert (await app_client.get(f"/api/v1/tasks/{task_id}/clarification")).status_code == 404
    assert (await app_client.get(f"/api/v1/tasks/{uuid4()}/clarification")).status_code == 404


async def test_clarification_full_flow_and_double_post_409(app_client, pg_pool, kiq_mock):
    task_id = await _awaiting_task(pg_pool, "Which array?")

    got = await app_client.get(f"/api/v1/tasks/{task_id}/clarification")
    assert got.status_code == 200
    assert got.json() == {"question": "Which array?"}

    first = await app_client.post(
        f"/api/v1/tasks/{task_id}/clarification", json={"answer": "the input list"}
    )
    assert first.status_code == 202
    assert first.json()["status"] == "analyzing_problem"
    kiq_mock.assert_awaited_once_with(str(task_id), "the input list")

    second = await app_client.post(
        f"/api/v1/tasks/{task_id}/clarification", json={"answer": "again"}
    )
    assert second.status_code == 409
    assert kiq_mock.await_count == 1

    # question is no longer pending once resumed
    assert (await app_client.get(f"/api/v1/tasks/{task_id}/clarification")).status_code == 404


async def test_get_task_hides_question_after_answer(app_client, pg_pool, kiq_mock):
    task_id = await _awaiting_task(pg_pool, "Which array?")

    pending = await app_client.get(f"/api/v1/tasks/{task_id}")
    assert pending.status_code == 200
    assert pending.json()["status"] == "awaiting_clarification"
    assert pending.json()["clarification_question"] == "Which array?"

    posted = await app_client.post(
        f"/api/v1/tasks/{task_id}/clarification", json={"answer": "the input list"}
    )
    assert posted.status_code == 202

    resumed = (await app_client.get(f"/api/v1/tasks/{task_id}")).json()
    assert resumed["status"] == "analyzing_problem"
    assert resumed["clarification_question"] is None

    await update_task_completed(pg_pool, task_id, {"ok": True})
    done = (await app_client.get(f"/api/v1/tasks/{task_id}")).json()
    assert done["status"] == "completed"
    assert done["clarification_question"] is None


async def test_concurrent_posts_enqueue_exactly_one_resume(app_client, pg_pool, kiq_mock):
    task_id = await _awaiting_task(pg_pool)
    responses = await asyncio.gather(
        *(
            app_client.post(f"/api/v1/tasks/{task_id}/clarification", json={"answer": f"a{i}"})
            for i in range(5)
        )
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [202, 409, 409, 409, 409]
    assert kiq_mock.await_count == 1


async def test_post_unknown_task_returns_409(app_client, kiq_mock):
    response = await app_client.post(
        f"/api/v1/tasks/{uuid4()}/clarification", json={"answer": "x"}
    )
    assert response.status_code == 409
    kiq_mock.assert_not_awaited()
