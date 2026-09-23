"""Compiled LangGraph StateGraph for the real Phase 2 pipeline, checkpointed
to Postgres (D-12).

As of this plan the pipeline runs Analyzer -> Strategist -> Solver ->
`finalize_success`; later plans (02-04..02-07) extend this same graph with
CodeGen/TestGen/Reviewer nodes and the correction-loop conditional edges —
this module keeps the injected-checkpointer convention established by
Phase 1's stub graph (the checkpointer is never constructed here, only wired
in — `worker/tasks.py` owns construction).

Replaces Phase 1's `build_stub_graph`/`stub_node` — the Phase-1-only magic-
string failure-simulation hook is retired; real pipeline failure paths
(CR-01 in `worker/tasks.py`) now supersede it.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.agents.solver.node import solver_node
from algorunner.graph.state import GraphState


def _json_safe_solver_output(solver_output: dict | None) -> dict | None:
    """`solver_output["approach"]` holds the live `Approach` pydantic
    instance (Plan 02-04's Code Generator reads it directly from
    `GraphState`), which is not JSON-serializable — `result` below is
    persisted to Postgres as JSONB by `worker/tasks.py`'s
    `update_task_completed`, so it must be dumped here, mirroring how
    `approaches` is dumped just below."""
    if solver_output is None:
        return None
    return {**solver_output, "approach": solver_output["approach"].model_dump()}


async def finalize_success(state: GraphState) -> dict:
    """Writes the final `result` dict for a successfully completed run.

    Later plans extend this function's body to add `solution`/`review`
    fields as more nodes land — never replace it wholesale.
    """
    return {
        "result": {
            "analysis": state["analysis"].model_dump() if state["analysis"] else None,
            "approaches": (
                [approach.model_dump() for approach in state["approaches"]]
                if state["approaches"]
                else None
            ),
            "solver_output": _json_safe_solver_output(state.get("solver_output")),
        }
    }


def build_pipeline_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(GraphState)
    builder.add_node("analyzer", problem_analyzer_node)
    builder.add_node("strategist", solution_strategist_node)
    builder.add_node("solver", solver_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_edge(START, "analyzer")
    builder.add_edge("analyzer", "strategist")
    builder.add_edge("strategist", "solver")
    builder.add_edge("solver", "finalize_success")
    builder.add_edge("finalize_success", END)
    return builder.compile(checkpointer=checkpointer)
