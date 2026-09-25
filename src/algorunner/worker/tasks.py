"""The real Phase 2 worker task entry point: invokes the LangGraph pipeline
end-to-end for a submitted problem.

Renamed from Phase 1's `solve_problem_stub` (D-04's throwaway placeholder is
retired — see `graph/build.py`). Bakes in, directly in this rewrite rather
than as a later patch:

- CR-01 (01-REVIEW.md): the whole body is wrapped in try/except — any
  unhandled exception is written to the task row as a structured
  `TaskError`, then re-raised (so taskiq's own error/retry visibility is
  preserved), instead of leaving the task stuck at a non-terminal status
  forever.
- CR-02 (01-REVIEW.md): a `task_id` with no matching Postgres row logs an
  error and returns without proceeding — never fabricates a false
  "completed" result for a task that never really ran.

Stays fully async (never blocking `subprocess.run()`/`time.sleep`) —
CLAUDE.md "What NOT to Use", carried forward from Phase 1's docstring. The
Phase 1 stub's `asyncio.sleep`-based D-06 simulated delay is gone along with
the stub node itself — the real Analyzer's OpenAI call is the actual latency
now.

CR-03 (01-REVIEW.md): the checkpointer is no longer constructed/`.setup()`-
called here per invocation (that raced under concurrent first-time calls).
It is reused from `broker.state.checkpointer`, set exactly once at
WORKER_STARTUP by `worker/broker.py`'s `_on_worker_startup` hook.

Plan 03-05: adds PipelineContext with deadline and status_sink; _invoke_with_budget
now builds context and passes it to ainvoke with recursion_limit.
"""

import asyncio
import logging
import time
from uuid import UUID

from langgraph.types import Command

from algorunner.config import settings
from algorunner.graph.context import PipelineContext
from algorunner.schemas.task import TaskError, TaskStatus
from algorunner.storage.artifacts import ArtifactRecorder, get_artifact_store
from algorunner.storage.postgres import get_pool
from algorunner.storage.tasks import (
    add_active_execution_seconds,
    get_task,
    update_task_clarification,
    update_task_completed,
    update_task_failed,
    update_task_status,
)
from algorunner.worker.broker import broker

logger = logging.getLogger(__name__)

_pool = get_pool()


async def _pg_status_sink(task_id: str, status: TaskStatus) -> None:
    """Persist status transitions to Postgres (Pattern 11: logged, never raises).

    Called from emit_status via the status_sink callback for parent-level and
    per-branch statuses:
    - Parent level: designing_solution, generating_code, writing_editorial
    - Per-branch (Plan 04-02): generating_tests, executing_tests, reviewing, correcting

    After writing to Postgres, publishes a status event to Redis pub/sub
    (storage.publish_status, per 04-01). Exceptions are logged and never propagated.

    Postgres remains the source of truth; a failed write is non-blocking.
    """
    try:
        await update_task_status(_pool, UUID(task_id), status)
    except Exception as exc:
        logger.warning(
            f"Failed to update status to {status.value} for task {task_id}: {type(exc).__name__}: {exc}"
        )


async def _handle_result_or_pause(task_id: str, result_state: dict) -> None:
    """Persist the outcome of a graph invocation: a clarification pause, a
    terminal failure, or a completed result."""
    interrupts = result_state.get("__interrupt__")
    if interrupts:
        await update_task_clarification(_pool, UUID(task_id), interrupts[0].value)
        return

    error = result_state.get("error")
    if error is not None:
        await update_task_failed(
            _pool,
            UUID(task_id),
            TaskError(code=error["code"], message=error["message"]),
        )
        return

    await update_task_completed(_pool, UUID(task_id), result=result_state.get("result"))


async def _invoke_with_budget(graph, payload, config: dict, task_id: str) -> dict | None:
    """Run one graph invocation bounded by the remaining global time budget
    (D-07, D-10, INFRA-04). The budget is cumulative ACTIVE execution time across
    all invocations (initial run and clarification resumes); time parked in
    awaiting_clarification is never counted because it only accrues around
    the ainvoke call itself.

    Builds a PipelineContext with:
    - deadline_monotonic: monotonic time when this invocation must complete
    - editorial_reserve_s: time reserved for the Writer after branches
    - status_sink: async callback to persist parent-level status to Postgres

    Passes context= and recursion_limit to ainvoke. Returns None if the budget
    is exhausted (the task is already marked FAILED with GLOBAL_TIMEOUT).

    The deadline is recomputed on every invocation so clarification resumes get
    a fresh deadline from the remaining active-execution budget.
    """
    task = await get_task(_pool, UUID(task_id))
    used = task.active_execution_seconds if task is not None else 0.0
    remaining = settings.global_timeout_s - used
    timeout_error = TaskError(code="GLOBAL_TIMEOUT", message="Solve time budget exhausted")
    if remaining <= 0:
        await update_task_failed(_pool, UUID(task_id), timeout_error)
        return None

    # Build context with deadline, status sink, and artifact recorder (D-17..D-20)
    deadline = time.monotonic() + remaining
    artifacts = ArtifactRecorder(get_artifact_store())
    ctx = PipelineContext(
        deadline_monotonic=deadline,
        editorial_reserve_s=settings.editorial_reserve_s,
        status_sink=_pg_status_sink,
        artifacts=artifacts,
    )

    # Update config with recursion limit (8 * max_iterations + 30)
    config = {
        **config,
        "recursion_limit": 8 * settings.max_iterations + 30,
    }

    started = time.monotonic()
    try:
        return await asyncio.wait_for(
            graph.ainvoke(
                payload,
                config,
                context=ctx,
                # ainvoke()'s default durability is "async", which can lose a
                # just-completed checkpoint write on worker crash. "sync"
                # preserves the "resume from last completed node" guarantee.
                durability="sync",
            ),
            timeout=remaining,
        )
    except asyncio.TimeoutError:
        await update_task_failed(_pool, UUID(task_id), timeout_error)
        return None
    finally:
        await add_active_execution_seconds(_pool, UUID(task_id), time.monotonic() - started)


@broker.task
async def solve_problem(task_id: str) -> None:
    # Deferred import: preserves the worker.tasks <-> graph.build
    # module-boundary convention established in Phase 1 (graph/build.py no
    # longer imports anything from this module now that the Phase-1-only
    # magic-string failure marker is retired, but keeping the import
    # function-local avoids re-litigating that boundary for no reason).
    from algorunner.graph.build import build_pipeline_graph

    await _pool.open()  # safe to call again on an already-open pool

    try:
        await update_task_status(_pool, UUID(task_id), TaskStatus.ANALYZING_PROBLEM)

        task = await get_task(_pool, UUID(task_id))
        if task is None:  # CR-02
            logger.error("solve_problem: task %s not found, aborting", task_id)
            return

        # CR-03: reuse the process-wide checkpointer constructed once at
        # WORKER_STARTUP (worker/broker.py's _on_worker_startup) instead of
        # constructing a fresh one and calling .setup() per invocation.
        graph = build_pipeline_graph(broker.state.checkpointer)

        initial_state = {
            "task_id": task_id,
            "problem_text": task.problem_text,
            "language": task.language.value,
            "examples": [example.model_dump() for example in task.examples],
            "analysis": None,
            "clarification_rounds": 0,
            "clarification_answer": None,
            "assumption_stated": None,
            "clarifications": [],
            "approaches": [],
            "max_iterations": settings.max_iterations,
            "approach_outcomes": {},
            "editorial": None,
            "editorial_warnings": [],
            "result": None,
            "error": None,
        }
        result_state = await _invoke_with_budget(
            graph, initial_state, {"configurable": {"thread_id": task_id}}, task_id
        )
        if result_state is None:
            return

        await _handle_result_or_pause(task_id, result_state)
    except Exception as exc:  # CR-01
        await update_task_failed(
            _pool,
            UUID(task_id),
            TaskError(code="UNHANDLED_EXCEPTION", message=str(exc)),
        )
        raise


@broker.task
async def resume_task_with_clarification(task_id: str, answer: str) -> None:
    """Resume the SAME checkpointed thread with the user's clarification
    answer (INTAKE-05) — never restarts the pipeline."""
    from algorunner.graph.build import build_pipeline_graph

    await _pool.open()

    try:
        graph = build_pipeline_graph(broker.state.checkpointer)
        result_state = await _invoke_with_budget(
            graph, Command(resume=answer), {"configurable": {"thread_id": task_id}}, task_id
        )
        if result_state is None:
            return
        await _handle_result_or_pause(task_id, result_state)
    except Exception as exc:  # CR-01
        await update_task_failed(
            _pool,
            UUID(task_id),
            TaskError(code="UNHANDLED_EXCEPTION", message=str(exc)),
        )
        raise
