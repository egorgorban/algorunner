import asyncio
import time
from uuid import uuid4

import algorunner.worker.tasks as worker_tasks
from algorunner.schemas.task import Language, TaskStatus, TaskSubmission
from algorunner.storage.tasks import add_active_execution_seconds, get_task, insert_task


class _SpyGraph:
    def __init__(self, delay: float = 0.0, result: dict | None = None) -> None:
        self.calls = 0
        self._delay = delay
        self._result = result if result is not None else {"result": {"ok": True}}

    async def ainvoke(self, payload, config=None, **kwargs):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


async def _new_task(pg_pool):
    task_id = uuid4()
    await insert_task(pg_pool, task_id, TaskSubmission(problem_text="x", language=Language.EN))
    return task_id


async def test_exhausted_budget_short_circuits_without_ainvoke(pg_pool, monkeypatch):
    monkeypatch.setattr(worker_tasks.settings, "global_timeout_s", 0.5)
    task_id = await _new_task(pg_pool)
    await add_active_execution_seconds(pg_pool, task_id, 1.0)
    graph = _SpyGraph()

    result = await worker_tasks._invoke_with_budget(graph, {}, {}, str(task_id))

    assert result is None
    assert graph.calls == 0
    record = await get_task(pg_pool, task_id)
    assert record.status == TaskStatus.FAILED
    assert record.error.code == "GLOBAL_TIMEOUT"


async def test_mid_flight_timeout_cancels_and_fails(pg_pool, monkeypatch):
    monkeypatch.setattr(worker_tasks.settings, "global_timeout_s", 0.2)
    task_id = await _new_task(pg_pool)
    graph = _SpyGraph(delay=5)

    started = time.monotonic()
    result = await worker_tasks._invoke_with_budget(graph, {}, {}, str(task_id))
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 3
    assert graph.calls == 1
    record = await get_task(pg_pool, task_id)
    assert record.status == TaskStatus.FAILED
    assert record.error.code == "GLOBAL_TIMEOUT"
    assert record.active_execution_seconds > 0


async def test_success_returns_result_and_accrues_time(pg_pool, monkeypatch):
    monkeypatch.setattr(worker_tasks.settings, "global_timeout_s", 60)
    task_id = await _new_task(pg_pool)
    graph = _SpyGraph(delay=0.05, result={"result": {"x": 1}})

    result = await worker_tasks._invoke_with_budget(graph, {}, {}, str(task_id))

    assert result == {"result": {"x": 1}}
    record = await get_task(pg_pool, task_id)
    assert record.active_execution_seconds > 0
    assert record.status != TaskStatus.FAILED
