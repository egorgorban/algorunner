"""Per-approach subgraph and fan-out/fan-in orchestration for Phase 3 (D-08, RESEARCH Patterns 2-4).

The per-approach subgraph (`build_approach_graph`) reuses every Phase 2 node
and the decide_after_review router unchanged, but operates on `ApproachState`
instead of GraphState. Each branch is compiled without its own checkpointer —
it inherits the parent's, and its checkpoints land in the parent's saver under
a `run_approach:<uuid>` namespace (RESEARCH Pattern 2).

The fan-out function `fan_out_approaches` yields one Send per approach from the
Strategist's list, dispatching to the `run_approach` node. The pure `decide_after_join`
router runs AFTER all branches complete (a plain edge collects them; RESEARCH Pattern 1,
Pitfall 1) and decides success or failure based on whether any outcome is verified.

The `decide_after_join` router lives here, not in graph/routing.py, because it
depends on the ApproachStatus vocabulary defined in schemas/outcome.py (placed
at module load, not per-node like the per-solution routers).

Plan 03-05: adds deadline handling to run_approach, executor semaphore, and context_schema.

Later plans extend this file:
- Plan 03-03: adds Strategist reset logic (Pitfall 3) and curation (STRAT-02)
- Plan 03-04: changes "finalize_success" to "editorial_writer" in decide_after_join
- Plan 03-05: adds per-branch timeout to run_approach
"""

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send
from langgraph.runtime import Runtime

from algorunner.agents.code_generator.node import code_generator_node
from algorunner.agents.reviewer.node import reviewer_node
from algorunner.agents.solver.node import solver_node
from algorunner.agents.test_generator.node import test_generator_node
from algorunner.config import settings
from algorunner.graph.context import PipelineContext, branch_budget_s, emit_status, persist
from algorunner.graph.harness import render_go_program, render_python_program
from algorunner.graph.routing import decide_after_review
from algorunner.graph.state import ApproachInput, ApproachState
from algorunner.storage.artifacts import iteration_key, summary_key
from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.outcome import ApproachOutcome
from algorunner.schemas.task import TaskStatus
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

logger = logging.getLogger(__name__)

# Moved from build.py, unchanged except for type annotation (GraphState -> ApproachState)
_GO_TIMEOUT_S = 30.0
_PASS_MARKER = "ALGORUNNER PASS"

# Executor semaphore for Pitfall 5: cap concurrent Python/Go subprocesses per
# worker process. Keyed by concurrency limit to support monkeypatching in tests.
_executor_semaphores: dict[int, asyncio.Semaphore] = {}


def _executor_slot() -> asyncio.Semaphore:
    """Get or create the executor semaphore for the current concurrency limit.

    Returns the semaphore gated by settings.executor_max_concurrency.
    Lazily creates a new semaphore the first time a given limit is used, so tests
    can monkeypatch the setting and get a fresh semaphore.

    Pitfall 5: This prevents executor starvation when multiple branches run in parallel.
    The tools/process.py trust model (shared uid 65534) remains unchanged.
    """
    limit = settings.executor_max_concurrency
    if limit not in _executor_semaphores:
        _executor_semaphores[limit] = asyncio.Semaphore(limit)
    return _executor_semaphores[limit]


def _with_status(
    node: Callable[[dict], Awaitable[dict]],
    status_for: Callable[[dict], TaskStatus | None],
) -> Callable[[dict, Runtime[PipelineContext]], Awaitable[dict]]:
    """Wrapper that emits a status before invoking a state-only node.

    Args:
        node: An async node function with signature (state: dict) -> dict
        status_for: A function that maps state to TaskStatus or None. When None,
            no status is emitted.

    Returns:
        An async node with signature (state: dict, runtime: Runtime[PipelineContext]) -> dict
        that emits the status (if status_for returns one) before calling the original node.

    The wrapper copies the original node's __name__ for debugging.
    """

    async def wrapped(state: dict, runtime: Runtime[PipelineContext]) -> dict:
        status = status_for(state)
        if status is not None:
            await emit_status(runtime.context, state["task_id"], status)
        return await node(state)

    wrapped.__name__ = node.__name__
    return wrapped


def _require_pass_marker(result: ExecutionResult) -> ExecutionResult:
    """T-02-09-04: exit code 0 alone is not proof the harness ran every case
    (generated code could call exit() at import time). A pass must also carry
    the harness's `ALGORUNNER PASS n/n` line."""
    if result.passed and _PASS_MARKER not in result.stdout:
        return result.model_copy(
            update={
                "passed": False,
                "stderr": result.stderr
                + "\nharness pass marker missing: the test harness did not run to completion",
            }
        )
    return result


async def execute_python_node(state: ApproachState, runtime: Runtime[PipelineContext]) -> dict:
    """Execute Python code with executor concurrency bounded per worker process.

    Emits EXECUTING_TESTS status before running the executor.

    Pitfall 5: acquires _executor_slot before running to ensure no more than
    settings.executor_max_concurrency Python/Go processes are in flight.
    """
    await emit_status(runtime.context, state["task_id"], TaskStatus.EXECUTING_TESTS)
    solution = state["solution"]
    program = render_python_program(solution.code_python, solution.entry_point, solution.tests)
    async with _executor_slot():
        result = await SubprocessPythonExecutor().run(program.code, program.tests)
    return {"python_execution": _require_pass_marker(result)}


async def execute_go_node(state: ApproachState, runtime: Runtime[PipelineContext]) -> dict:
    """Execute Go code with executor concurrency bounded per worker process.

    Pitfall 5: acquires _executor_slot before running to ensure no more than
    settings.executor_max_concurrency Python/Go processes are in flight.
    """
    solution = state["solution"]
    program = render_go_program(solution.code_go, solution.entry_point, solution.tests)
    async with _executor_slot():
        result = await SubprocessGoExecutor().run(
            program.code, program.tests, timeout_s=_GO_TIMEOUT_S
        )
    return {"go_execution": _require_pass_marker(result)}


async def persist_iteration_node(state: ApproachState, runtime: Runtime[PipelineContext]) -> dict:
    """Persist iteration artifacts after the reviewer (solution, python_exec, go_exec, review).

    Runs after the reviewer node, which increments state["iterations"], making it 1-based.
    Concurrently persists the four artifacts for (task_id, approach_idx, n):
    - solution.json from state["solution"].model_dump()
    - python_exec.json from state["python_execution"].model_dump()
    - go_exec.json from state["go_execution"].model_dump()
    - review.json from state["review"].model_dump()

    Any None payloads are skipped. Storage failures are logged and recorded as incomplete
    in the recorder (D-17, D-19). Returns {} (no state changes).

    Runs outside the async.wait_for timeout in run_approach, so it does not interfere
    with branch deadline handling.
    """
    ctx = runtime.context
    task_id = state.get("task_id")
    approach_idx = state.get("approach_idx")
    n = state.get("iterations")  # 1-based, already incremented by reviewer

    if not all([task_id, approach_idx is not None, n]):
        return {}

    # Build concurrent writes for the four artifacts
    async def write_artifact(kind, payload):
        if payload is None:
            return
        await persist(
            ctx,
            lambda: iteration_key(task_id, approach_idx, n, kind),
            payload.model_dump() if hasattr(payload, 'model_dump') else payload,
        )

    payloads = {
        "solution": state.get("solution"),
        "python_exec": state.get("python_execution"),
        "go_exec": state.get("go_execution"),
        "review": state.get("review"),
    }

    await asyncio.gather(*[write_artifact(k, v) for k, v in payloads.items()])
    return {}


def initial_branch_state(inp: ApproachInput) -> ApproachState:
    """Construct the initial ApproachState from an ApproachInput (Send payload).

    Copies all ApproachInput fields and initializes working state to None/empty.
    """
    return {
        **inp,
        "solver_output": None,
        "solution": None,
        "python_execution": None,
        "go_execution": None,
        "review": None,
        "review_history": [],
        "iterations": 0,
    }


def outcome_from_final(inp: ApproachInput, final: dict) -> ApproachOutcome:
    """Construct an ApproachOutcome from the branch's final state.

    Status is "verified" ONLY when:
    - final["review"] is not None
    - review.passed is True
    - final["solution"] is not None
    - both python_execution and go_execution exist with passed=True

    Any other path yields "exhausted" (iteration limit hit).
    Core Value: defense in depth requires all three signals (review, solution, both executions).
    """
    review = final.get("review")
    solution = final.get("solution")
    python_exec = final.get("python_execution")
    go_exec = final.get("go_execution")

    # All signals present and passing
    if (
        review is not None
        and review.passed
        and solution is not None
        and python_exec is not None
        and python_exec.passed
        and go_exec is not None
        and go_exec.passed
    ):
        status = "verified"
    else:
        status = "exhausted"

    return ApproachOutcome(
        approach_idx=inp["approach_idx"],
        approach=inp["approach"],
        status=status,
        iterations=final.get("iterations", 0),
        final_solution=solution,
        final_review=review,
        error=None,
    )


async def run_approach(state: ApproachInput, runtime: Runtime[PipelineContext]) -> dict:
    """Execute one per-approach branch with deadline and executor concurrency control.

    Emits GENERATING_CODE status (idempotent across branches).

    Checks if the branch budget is already exhausted (deadline - now - reserve <= 0).
    If so, returns a timed_out outcome without invoking the subgraph.

    Otherwise, invokes the approach subgraph with asyncio.wait_for at the branch
    budget timeout. On TimeoutError, returns a timed_out outcome (D-10).

    On GraphBubbleUp, re-raises (RESEARCH Pattern 2). On other exceptions,
    returns an errored outcome. A GraphRecursionError inside the branch becomes
    an errored outcome (not a graph failure).

    Returns the outcome wrapped in approach_outcomes[approach_idx].

    Pitfall 9: safe to call without context (no deadline → unbounded budget).
    """
    approach_idx = state["approach_idx"]
    ctx = runtime.context

    try:
        # Emit GENERATING_CODE status (idempotent across branches)
        await emit_status(ctx, state["task_id"], TaskStatus.GENERATING_CODE)

        # Check if the branch deadline is already in the past
        budget = branch_budget_s(ctx)
        if budget is not None and budget <= 0:
            return {
                "approach_outcomes": {
                    approach_idx: ApproachOutcome.not_verified(
                        approach_idx=approach_idx,
                        approach=state["approach"],
                        status="timed_out",
                        error="branch deadline reached before start",
                    )
                }
            }

        # Invoke the subgraph bounded by branch_budget_s timeout (or unbounded if None)
        graph = get_approach_graph()
        branch_state = initial_branch_state(state)

        if budget is not None:
            final = await asyncio.wait_for(
                graph.ainvoke(branch_state),
                timeout=budget,
            )
        else:
            final = await graph.ainvoke(branch_state)

        outcome = outcome_from_final(state, final)

    except GraphBubbleUp:
        raise
    except asyncio.TimeoutError:
        outcome = ApproachOutcome.not_verified(
            approach_idx=approach_idx,
            approach=state["approach"],
            status="timed_out",
            error="branch deadline reached",
        )
    except Exception as exc:
        outcome = ApproachOutcome.not_verified(
            approach_idx=approach_idx,
            approach=state["approach"],
            status="errored",
            error=f"{type(exc).__name__}: {exc}",
        )

    # Persist approach summary on every path (D-17, including the global-timeout path).
    # The summary is written outside the subgraph wait_for, so it lands within the
    # editorial_reserve_s window before the worker's hard cancel (D-17).
    task_id = state["task_id"]
    summary_payload = {
        "approach_idx": outcome.approach_idx,
        "name": outcome.approach.name,
        "technique": outcome.approach.technique,
        "role": outcome.approach.role,
        "status": outcome.status,
        "iterations": outcome.iterations,
        "error": outcome.error,
    }
    await persist(
        ctx,
        lambda: summary_key(task_id, approach_idx),
        summary_payload,
    )

    return {"approach_outcomes": {approach_idx: outcome}}


def build_approach_graph(checkpointer: object | None = None) -> CompiledStateGraph:
    """Build the per-approach subgraph with Phase 2 nodes and routers.

    Nodes: solver, code_generator, test_generator, execute_python, execute_go, reviewer,
    persist_iteration (Plan 03-08: writes iteration artifacts after reviewer).
    Edges form the Phase 2 linear chain with decide_after_review routing back to solver
    or code_generator on failure, or to persist_iteration then END on success.

    Plan 04-02: Adds status emission for D-04 status taxonomy:
    - solver and code_generator emit CORRECTING when state["iterations"] > 0 (correction iterations)
    - test_generator emits GENERATING_TESTS (always)
    - execute_python emits EXECUTING_TESTS as first statement
    - reviewer emits REVIEWING (always)
    - execute_go emits no status

    Compiled WITHOUT a checkpointer argument — the subgraph inherits the parent's
    checkpointer via the checkpointer passed to build_pipeline_graph.

    Has context_schema=PipelineContext to receive runtime context from parent.
    """
    builder = StateGraph(ApproachState, context_schema=PipelineContext)

    # Wrap nodes that emit status. State-only nodes (solver, code_generator, test_generator, reviewer)
    # are wrapped with _with_status to receive runtime context and emit status.
    # execute_python_node already takes runtime and emits status inline.
    # execute_go_node does not emit status.

    # Solver emits CORRECTING only on correction iterations (iterations > 0)
    solver_with_status = _with_status(
        solver_node,
        lambda state: TaskStatus.CORRECTING if state.get("iterations", 0) > 0 else None,
    )

    # Code generator emits CORRECTING only on correction iterations
    code_gen_with_status = _with_status(
        code_generator_node,
        lambda state: TaskStatus.CORRECTING if state.get("iterations", 0) > 0 else None,
    )

    # Test generator always emits GENERATING_TESTS
    test_gen_with_status = _with_status(
        test_generator_node,
        lambda state: TaskStatus.GENERATING_TESTS,
    )

    # Reviewer always emits REVIEWING
    reviewer_with_status = _with_status(
        reviewer_node,
        lambda state: TaskStatus.REVIEWING,
    )

    builder.add_node("solver", solver_with_status)
    builder.add_node("code_generator", code_gen_with_status)
    builder.add_node("test_generator", test_gen_with_status)
    builder.add_node("execute_python", execute_python_node)
    builder.add_node("execute_go", execute_go_node)
    builder.add_node("reviewer", reviewer_with_status)
    builder.add_node("persist_iteration", persist_iteration_node)

    builder.add_edge(START, "solver")
    builder.add_edge("solver", "code_generator")
    builder.add_edge("code_generator", "test_generator")
    builder.add_edge("test_generator", "execute_python")
    builder.add_edge("execute_python", "execute_go")
    builder.add_edge("execute_go", "reviewer")

    # Route from reviewer: on success/exhaustion, persist and exit; on failure, retry
    builder.add_conditional_edges(
        "reviewer",
        decide_after_review,
        {
            "finalize_success": "persist_iteration",
            "finalize_failed": "persist_iteration",
            "solver": "solver",
            "code_generator": "code_generator",
        },
    )

    # Persist iteration artifacts, then exit
    builder.add_edge("persist_iteration", END)

    return builder.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_approach_graph() -> CompiledStateGraph:
    """Return a cached compiled per-approach subgraph (no checkpointer).

    Caches the subgraph so multiple branches can reuse the same compiled graph object.
    The parent graph passes the checkpointer at its own compile time; this subgraph
    is compiled without one and inherits via the parent.
    """
    return build_approach_graph()


def fan_out_approaches(state: dict) -> list[Send]:
    """Fan-out router: emit one Send per approach in the Strategist's list.

    Pure function. Raises ValueError if the approaches list is empty
    (the graph must never end without either a result or error).

    Each Send carries an ApproachInput with task_id, approach_idx, approach,
    problem_text, examples, analysis, assumption_stated, max_iterations.
    """
    approaches = state.get("approaches", [])
    if not approaches:
        raise ValueError("fan_out_approaches: no approaches to dispatch")

    return [
        Send(
            "run_approach",
            {
                "task_id": state["task_id"],
                "approach_idx": idx,
                "approach": approach,
                "problem_text": state["problem_text"],
                "examples": state.get("examples", []),
                "analysis": state.get("analysis"),
                "assumption_stated": state.get("assumption_stated"),
                "max_iterations": state.get("max_iterations", 5),
            },
        )
        for idx, approach in enumerate(approaches)
    ]


def decide_after_join(state: dict) -> str:
    """Join router: decide success or failure after all branches complete.

    Pure function, zero I/O. Returns "editorial_writer" if any outcome in
    approach_outcomes has status "verified", else "finalize_failed".

    This router lives in graph/approach.py (not graph/routing.py) because
    it depends on the ApproachStatus vocabulary from schemas/outcome.py,
    which is a module-level constant set at import time (like the per-node
    routers, but logically grouped with the orchestration).

    Plan 03-04: routes to "editorial_writer" on verified outcome.
    """
    outcomes = state.get("approach_outcomes", {})
    if any(outcome.status == "verified" for outcome in outcomes.values()):
        return "editorial_writer"
    return "finalize_failed"
