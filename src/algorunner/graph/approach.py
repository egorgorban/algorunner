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

Later plans extend this file:
- Plan 03-03: adds Strategist reset logic (Pitfall 3) and curation (STRAT-02)
- Plan 03-04: changes "finalize_success" to "editorial_writer" in decide_after_join
- Plan 03-05: adds per-branch timeout to run_approach
"""

import logging
import traceback
from functools import lru_cache
from typing import Any

from langgraph.errors import GraphBubbleUp

logger = logging.getLogger(__name__)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from algorunner.agents.code_generator.node import code_generator_node
from algorunner.agents.reviewer.node import reviewer_node
from algorunner.agents.solver.node import solver_node
from algorunner.agents.test_generator.node import test_generator_node
from algorunner.graph.harness import render_go_program, render_python_program
from algorunner.graph.routing import decide_after_review
from algorunner.graph.state import ApproachInput, ApproachState
from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.outcome import ApproachOutcome
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

# Moved from build.py, unchanged except for type annotation (GraphState -> ApproachState)
_GO_TIMEOUT_S = 30.0
_PASS_MARKER = "ALGORUNNER PASS"


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


async def execute_python_node(state: ApproachState) -> dict:
    solution = state["solution"]
    program = render_python_program(solution.code_python, solution.entry_point, solution.tests)
    result = await SubprocessPythonExecutor().run(program.code, program.tests)
    return {"python_execution": _require_pass_marker(result)}


async def execute_go_node(state: ApproachState) -> dict:
    solution = state["solution"]
    program = render_go_program(solution.code_go, solution.entry_point, solution.tests)
    result = await SubprocessGoExecutor().run(
        program.code, program.tests, timeout_s=_GO_TIMEOUT_S
    )
    return {"go_execution": _require_pass_marker(result)}


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


async def run_approach(state: ApproachInput) -> dict:
    """Execute one per-approach branch.

    Invokes the approach subgraph with no explicit checkpoint coordinate or
    thread_id, so checkpoints land in the parent's saver under the inherited
    namespace (RESEARCH Pattern 2). The subgraph inherits the parent's checkpointer.

    Returns the outcome wrapped in approach_outcomes[approach_idx].
    On exception, catches everything except GraphBubbleUp (which must propagate),
    and BaseException (CancelledError must propagate for worker timeout).
    """
    approach_idx = state["approach_idx"]
    approach_name = state["approach"].name
    logger.info(f"run_approach: Starting branch for approach {approach_idx} ({approach_name})")
    logger.debug(f"run_approach: Input state keys: {list(state.keys())}")

    try:
        graph = get_approach_graph()
        branch_state = initial_branch_state(state)
        logger.debug(f"run_approach: Initial branch state keys: {list(branch_state.keys())}")
        logger.debug(f"run_approach: review={branch_state.get('review')}, iterations={branch_state.get('iterations')}")

        final = await graph.ainvoke(branch_state)
        logger.info(f"run_approach: Branch {approach_idx} completed successfully")
        outcome = outcome_from_final(state, final)
    except GraphBubbleUp:
        logger.error(f"run_approach: GraphBubbleUp in branch {approach_idx}")
        raise
    except Exception as exc:
        logger.error(f"run_approach: Exception in branch {approach_idx}: {type(exc).__name__}: {exc}")
        logger.error(f"run_approach: Full traceback:\n{traceback.format_exc()}")
        outcome = ApproachOutcome.not_verified(
            approach_idx=approach_idx,
            approach=state["approach"],
            status="errored",
            error=f"{type(exc).__name__}: {exc}",
        )

    return {"approach_outcomes": {approach_idx: outcome}}


def build_approach_graph(checkpointer: object | None = None) -> CompiledStateGraph:
    """Build the per-approach subgraph with Phase 2 nodes and routers.

    Nodes: solver, code_generator, test_generator, execute_python, execute_go, reviewer.
    Edges form the Phase 2 linear chain with decide_after_review routing back to solver
    or code_generator on failure, or to END on success.

    Compiled WITHOUT a checkpointer argument — the subgraph inherits the parent's
    checkpointer via the checkpointer passed to build_pipeline_graph.
    """
    builder = StateGraph(ApproachState)
    builder.add_node("solver", solver_node)
    builder.add_node("code_generator", code_generator_node)
    builder.add_node("test_generator", test_generator_node)
    builder.add_node("execute_python", execute_python_node)
    builder.add_node("execute_go", execute_go_node)
    builder.add_node("reviewer", reviewer_node)

    builder.add_edge(START, "solver")
    builder.add_edge("solver", "code_generator")
    builder.add_edge("code_generator", "test_generator")
    builder.add_edge("test_generator", "execute_python")
    builder.add_edge("execute_python", "execute_go")
    builder.add_edge("execute_go", "reviewer")

    builder.add_conditional_edges(
        "reviewer",
        decide_after_review,
        {
            "finalize_success": END,
            "finalize_failed": END,
            "solver": "solver",
            "code_generator": "code_generator",
        },
    )

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

    Pure function, zero I/O. Returns "finalize_success" if any outcome in
    approach_outcomes has status "verified", else "finalize_failed".

    This router lives in graph/approach.py (not graph/routing.py) because
    it depends on the ApproachStatus vocabulary from schemas/outcome.py,
    which is a module-level constant set at import time (like the per-node
    routers, but logically grouped with the orchestration).

    Plan 03-04 will change the success label to "editorial_writer".
    """
    outcomes = state.get("approach_outcomes", {})
    if any(outcome.status == "verified" for outcome in outcomes.values()):
        return "finalize_success"
    return "finalize_failed"
