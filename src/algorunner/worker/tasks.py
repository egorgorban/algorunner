"""The Phase 1 placeholder pipeline: no AI logic (D-04), just a
configurable success/fail outcome so both the happy path and the failure
path are exercised end-to-end.

This file is the template Phase 2's real executors extend — keep it fully
async (asyncio.sleep, never time.sleep/blocking subprocess.run) to avoid
establishing a blocking-call precedent (CLAUDE.md "What NOT to Use").
"""

import asyncio  # re-exported: algorunner.graph.build's asyncio.sleep is the
# same shared module object, so tests that monkeypatch worker_tasks.asyncio
# still no-op the sleep now living in graph/build.py (D-06 moved there).
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from algorunner.schemas.task import TaskError, TaskStatus
from algorunner.storage.postgres import get_pool
from algorunner.storage.tasks import (
    get_task,
    update_task_completed,
    update_task_failed,
    update_task_status,
)
from algorunner.worker.broker import broker

# Phase-1-only test hook: a magic string embedded in problem_text simulates
# a failure outcome (D-05). NOT real Analyzer behavior — remove/replace when
# Phase 2 lands.
FAIL_TEST_MARKER = "FAIL_TEST"

_pool = get_pool()


@broker.task
async def solve_problem_stub(task_id: str) -> None:
    # Deferred import: algorunner.graph.build imports FAIL_TEST_MARKER from
    # this module at its own module level, so importing build_stub_graph
    # here (rather than at this module's top level) avoids a circular import
    # between worker.tasks and graph.build.
    from algorunner.graph.build import build_stub_graph

    await _pool.open()  # safe to call again on an already-open pool

    await update_task_status(_pool, UUID(task_id), TaskStatus.ANALYZING_PROBLEM)  # D-09

    task = await get_task(_pool, UUID(task_id))
    problem_text = task.problem_text if task is not None else ""

    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()  # idempotent — safe to call every invocation
    graph = build_stub_graph(checkpointer)

    result_state = await graph.ainvoke(
        {"task_id": task_id, "problem_text": problem_text, "result": None, "error": None},
        config={"configurable": {"thread_id": task_id}},
    )

    error = result_state.get("error")
    if error is not None:
        await update_task_failed(
            _pool,
            UUID(task_id),
            TaskError(code=error["code"], message=error["message"]),
        )
        return

    await update_task_completed(_pool, UUID(task_id), result=result_state.get("result"))
