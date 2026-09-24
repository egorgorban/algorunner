"""Runtime context for the pipeline invocation (D-07, D-10, RESEARCH Pattern 9).

The PipelineContext carries the invocation deadline and status sink as LangGraph
Runtime context (never state or configurable). This avoids the primitive-only
constraint on configurable values — context objects propagate to subgraphs
automatically.

Timeline: deadline_monotonic is set once per invocation from remaining budget;
it is recomputed on resume so clarification rounds get fresh deadlines from the
remaining active-execution budget.

Pitfall 9: invoking the graph without context (tests, local dev) must not crash.
All helpers here return None or no-op when context/deadline are absent.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from algorunner.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

StatusSink = Callable[[str, TaskStatus], Awaitable[None]]
"""Async callback to persist status: (task_id, status) -> ()"""


@dataclass(frozen=True)
class PipelineContext:
    """Run-scoped context for the graph invocation.

    deadline_monotonic: absolute monotonic time when this invocation must
        complete, or None if no deadline is enforced (local dev, tests).
        Recomputed on resume to reflect remaining budget.

    editorial_reserve_s: time reserved for the Writer AFTER branches complete.
        Subtracted from remaining budget to compute branch_budget_s.

    status_sink: async callback to persist parent-level status transitions
        (designing_solution, generating_code, writing_editorial) to Postgres.
        Never called if None.
    """

    deadline_monotonic: float | None = None
    editorial_reserve_s: float = 240.0
    status_sink: StatusSink | None = None


def branch_budget_s(ctx: PipelineContext | None) -> float | None:
    """Remaining time budget for a branch (deadline - now - editorial_reserve).

    Returns:
        - None if context or deadline is None (no deadline, unbounded budget)
        - A float (possibly negative or zero) if deadline is set

    Pitfall 9: safe to call with None context (returns None).
    """
    if ctx is None or ctx.deadline_monotonic is None:
        return None
    remaining = ctx.deadline_monotonic - time.monotonic() - ctx.editorial_reserve_s
    return remaining


def remaining_s(ctx: PipelineContext | None) -> float | None:
    """Remaining time budget for the entire invocation (deadline - now).

    Returns:
        - None if context or deadline is None (no deadline, unbounded)
        - A float (possibly negative) if deadline is set

    Used to bound the Writer node's LLM call. Pitfall 9: safe with None context.
    """
    if ctx is None or ctx.deadline_monotonic is None:
        return None
    return ctx.deadline_monotonic - time.monotonic()


async def emit_status(
    ctx: PipelineContext | None, task_id: str, status: TaskStatus
) -> None:
    """Emit a status update via the sink if present.

    No-op if context or sink is None. Exceptions are logged and never raised
    (Pattern 11: a failed status write is logged, never fails the task).

    Pitfall 9: safe to call with None context.
    """
    if ctx is None or ctx.status_sink is None:
        return

    try:
        await ctx.status_sink(task_id, status)
    except Exception as exc:
        logger.warning(
            f"Failed to emit status {status.value} for task {task_id}: {type(exc).__name__}: {exc}"
        )
