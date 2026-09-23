import logging
from uuid import uuid4

import pytest

from algorunner.schemas.task import Language, TaskSubmission
from algorunner.storage.tasks import get_task, insert_task


async def test_solve_problem_happy_path_completes(pg_pool, mock_openai_parse):
    import algorunner.worker.tasks as worker_tasks

    task_id = uuid4()
    submission = TaskSubmission(problem_text="two sum", language=Language.EN, examples=[])
    await insert_task(pg_pool, task_id, submission)

    await worker_tasks.solve_problem(str(task_id))

    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    assert record.result["analysis"] is not None


async def test_solve_problem_unhandled_exception_writes_structured_error_and_reraises(
    pg_pool, monkeypatch
):
    import algorunner.graph.build as graph_build
    import algorunner.worker.tasks as worker_tasks

    task_id = uuid4()
    submission = TaskSubmission(problem_text="two sum", language=Language.EN, examples=[])
    await insert_task(pg_pool, task_id, submission)

    class _BoomGraph:
        async def ainvoke(self, *args, **kwargs):
            raise ValueError("boom")

    def _build_boom_graph(checkpointer):
        return _BoomGraph()

    # worker/tasks.py does `from algorunner.graph.build import
    # build_pipeline_graph` freshly on every call (deferred import), so
    # patching the module attribute here is picked up by the next call.
    monkeypatch.setattr(graph_build, "build_pipeline_graph", _build_boom_graph)

    with pytest.raises(ValueError, match="boom"):
        await worker_tasks.solve_problem(str(task_id))

    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "failed"
    assert record.error is not None
    assert record.error.code == "UNHANDLED_EXCEPTION"
    assert "boom" in record.error.message


async def test_solve_problem_missing_task_row_logs_and_returns_without_writing_result(
    pg_pool, caplog
):
    import algorunner.worker.tasks as worker_tasks

    missing_task_id = uuid4()

    with caplog.at_level(logging.ERROR):
        await worker_tasks.solve_problem(str(missing_task_id))

    record = await get_task(pg_pool, missing_task_id)
    assert record is None
    assert any("not found" in message for message in caplog.messages)
