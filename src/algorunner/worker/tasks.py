"""The Phase 1 placeholder pipeline: no AI logic (D-04), just a
configurable success/fail outcome so both the happy path and the failure
path are exercised end-to-end.

This file is the template Phase 2's real executors extend — keep it fully
async (asyncio.sleep, never time.sleep/blocking subprocess.run) to avoid
establishing a blocking-call precedent (CLAUDE.md "What NOT to Use").
"""

import asyncio
import random
from uuid import UUID

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
    await _pool.open()  # safe to call again on an already-open pool

    await update_task_status(_pool, UUID(task_id), TaskStatus.ANALYZING_PROBLEM)  # D-09

    task = await get_task(_pool, UUID(task_id))

    await asyncio.sleep(random.uniform(2, 5))  # D-06

    if task is not None and FAIL_TEST_MARKER in task.problem_text:  # D-05
        await update_task_failed(
            _pool,
            UUID(task_id),
            TaskError(code="SIMULATED_FAILURE", message="Task failed via FAIL_TEST marker"),
        )
        return

    await update_task_completed(
        _pool, UUID(task_id), result={"message": "stub pipeline completed"}
    )
