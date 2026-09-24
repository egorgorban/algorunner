import logging
from uuid import uuid4

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from algorunner.schemas.task import Language, TaskSubmission
from algorunner.storage.tasks import get_task, insert_task
from algorunner.worker.broker import broker


@pytest_asyncio.fixture(autouse=True)
async def _worker_state_checkpointer(pg_pool):
    """CR-03: solve_problem() now reads `broker.state.checkpointer` instead
    of constructing/`.setup()`-ing its own per invocation. In production
    that attribute is set once by worker/broker.py's WORKER_STARTUP hook
    (`_on_worker_startup`); these tests call `solve_problem` directly
    without going through taskiq's worker lifecycle, so this fixture
    mimics that same one-time setup for the test process."""
    if not hasattr(broker.state, "checkpointer"):
        checkpointer = AsyncPostgresSaver(pg_pool)
        await checkpointer.setup()
        broker.state.checkpointer = checkpointer
    yield


async def test_solve_problem_happy_path_completes(pg_pool, mock_pipeline_openai):
    import algorunner.worker.tasks as worker_tasks

    task_id = uuid4()
    submission = TaskSubmission(problem_text="two sum", language=Language.EN, examples=[])
    await insert_task(pg_pool, task_id, submission)

    await worker_tasks.solve_problem(str(task_id))

    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    # Phase 3: result shape has approaches, editorial, artifact tracking
    assert "approaches" in record.result
    assert isinstance(record.result["approaches"], list)
    assert "artifact_keys" in record.result
    assert isinstance(record.result["artifact_keys"], list)
    assert "artifacts_incomplete" in record.result
    assert isinstance(record.result["artifacts_incomplete"], bool)


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


async def test_solve_problem_zero_verified_global_timeout_writes_approach_summaries(
    pg_pool, monkeypatch, mock_pipeline_openai
):
    """Worker-path test: zero-verified global timeout writes branch summaries
    before the worker hard-cancel (D-17).

    Settings monkeypatched to trigger timeout:
    - global_timeout_s=4 (4 second budget)
    - editorial_reserve_s=2.0 (2 second reserve, so branches get 2 seconds)
    - Both executors sleep 30 s (so branches timeout at 2-second boundary)

    With a FakeStore recorder, we verify:
    - Task fails with error.code "GLOBAL_TIMEOUT"
    - FakeStore has summary.json for both approaches with status "timed_out"
    - No editorial.json is written (task failed before finalize_success)
    - Call completes in under 4 seconds
    """
    import time
    import algorunner.config as config_module
    import algorunner.worker.tasks as worker_tasks
    from tests.graph.test_persistence import FakeStore

    # Monkeypatch timeout settings
    monkeypatch.setattr(config_module.settings, "global_timeout_s", 4.0)
    monkeypatch.setattr(config_module.settings, "editorial_reserve_s", 2.0)

    # Monkeypatch executors to sleep long enough to trigger branch timeout
    async def _sleep_executor(self, code, tests):
        import asyncio
        await asyncio.sleep(30.0)
        from algorunner.schemas.execution import ExecutionResult
        return ExecutionResult(passed=False, stdout="", stderr="timeout sleep")

    import algorunner.tools.python_executor.subprocess_backend as py_exec
    import algorunner.tools.go_executor.subprocess_backend as go_exec
    monkeypatch.setattr(py_exec.SubprocessPythonExecutor, "run", _sleep_executor)
    monkeypatch.setattr(go_exec.SubprocessGoExecutor, "run", _sleep_executor)

    # Monkeypatch get_artifact_store to return FakeStore
    fake_store = FakeStore()
    monkeypatch.setattr(
        worker_tasks,
        "get_artifact_store",
        lambda: fake_store,
    )

    task_id = uuid4()
    submission = TaskSubmission(problem_text="two sum", language=Language.EN, examples=[])
    await insert_task(pg_pool, task_id, submission)

    start = time.time()
    await worker_tasks.solve_problem(str(task_id))
    elapsed = time.time() - start

    # Verify timing: should complete before hard cap
    assert elapsed < 4.5, f"Expected task to complete before 4.5s, took {elapsed:.1f}s"

    # Verify error: GLOBAL_TIMEOUT
    record = await get_task(pg_pool, task_id)
    assert record is not None
    assert record.status == "failed"
    assert record.error is not None
    assert record.error.code == "GLOBAL_TIMEOUT"

    # Verify artifact trail: both approach summaries written, no editorial
    written_keys = fake_store.written_keys()
    task_id_str = str(task_id)

    # Should have summary.json for both approaches (idx 0, 1)
    summary_0 = f"tasks/{task_id_str}/approaches/0/summary.json"
    summary_1 = f"tasks/{task_id_str}/approaches/1/summary.json"

    assert summary_0 in written_keys, f"Missing {summary_0} in {written_keys}"
    assert summary_1 in written_keys, f"Missing {summary_1} in {written_keys}"

    # No editorial (task failed, never reached finalize_success)
    editorial = f"tasks/{task_id_str}/editorial.json"
    assert editorial not in written_keys

    # Verify summaries have timed_out status
    summary_0_payload = fake_store.get_payload(summary_0)
    assert summary_0_payload is not None
    assert summary_0_payload["status"] == "timed_out"

    summary_1_payload = fake_store.get_payload(summary_1)
    assert summary_1_payload is not None
    assert summary_1_payload["status"] == "timed_out"
