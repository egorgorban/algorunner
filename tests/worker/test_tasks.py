from uuid import uuid4

from algorunner.schemas.task import Language, TaskSubmission
from algorunner.storage.tasks import get_task, insert_task


async def test_solve_problem_stub_happy_path_completes(pg_pool, monkeypatch):
    import algorunner.worker.tasks as worker_tasks

    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(worker_tasks.asyncio, "sleep", _no_sleep)

    task_id = uuid4()
    submission = TaskSubmission(problem_text="two sum", language=Language.EN, examples=[])
    await insert_task(pg_pool, task_id, submission)

    await worker_tasks.solve_problem_stub(str(task_id))

    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "completed"


async def test_solve_problem_stub_fail_test_marker_fails_with_structured_error(
    pg_pool, monkeypatch
):
    import algorunner.worker.tasks as worker_tasks

    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(worker_tasks.asyncio, "sleep", _no_sleep)

    task_id = uuid4()
    submission = TaskSubmission(
        problem_text="two sum FAIL_TEST", language=Language.EN, examples=[]
    )
    await insert_task(pg_pool, task_id, submission)

    await worker_tasks.solve_problem_stub(str(task_id))

    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "failed"
    assert record.error is not None
    assert record.error.code == "SIMULATED_FAILURE"
