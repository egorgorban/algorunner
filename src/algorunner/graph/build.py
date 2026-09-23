"""Compiled LangGraph StateGraph for the real Phase 2 pipeline, checkpointed
to Postgres (D-12).

As of this plan the pipeline runs Analyzer -> Strategist -> Solver ->
CodeGenerator -> TestGenerator -> `finalize_success`; later plans
(02-05..02-07) extend this same graph with the deterministic executors,
Reviewer node, and correction-loop conditional edges — this module keeps
the injected-checkpointer convention established by Phase 1's stub graph
(the checkpointer is never constructed here, only wired in —
`worker/tasks.py` owns construction).

Replaces Phase 1's `build_stub_graph`/`stub_node` — the Phase-1-only magic-
string failure-simulation hook is retired; real pipeline failure paths
(CR-01 in `worker/tasks.py`) now supersede it.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.agents.code_generator.node import code_generator_node
from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.agents.solver.node import solver_node
from algorunner.agents.test_generator.node import test_generator_node
from algorunner.graph.state import GraphState


async def finalize_success(state: GraphState) -> dict:
    """Writes the final `result` dict for a successfully completed run.

    Later plans extend this function's body to add `review` fields as more
    nodes land — never replace it wholesale.

    `solution` (dumped, JSON-safe) now supersedes the interim `solver_output`
    key Plan 02-03 added to the persisted `result` dict — `solver_output`
    stays in `GraphState` as an internal field (Code Generator reads it
    directly), it just no longer needs to appear in the final persisted
    result once `solution` fully subsumes it (approach/algorithm/complexity
    plus code_python/code_go/tests).
    """
    return {
        "result": {
            "analysis": state["analysis"].model_dump() if state["analysis"] else None,
            "approaches": (
                [approach.model_dump() for approach in state["approaches"]]
                if state["approaches"]
                else None
            ),
            "solution": state["solution"].model_dump() if state["solution"] else None,
        }
    }


def build_pipeline_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(GraphState)
    builder.add_node("analyzer", problem_analyzer_node)
    builder.add_node("strategist", solution_strategist_node)
    builder.add_node("solver", solver_node)
    builder.add_node("code_generator", code_generator_node)
    builder.add_node("test_generator", test_generator_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_edge(START, "analyzer")
    builder.add_edge("analyzer", "strategist")
    builder.add_edge("strategist", "solver")
    builder.add_edge("solver", "code_generator")
    builder.add_edge("code_generator", "test_generator")
    builder.add_edge("test_generator", "finalize_success")
    builder.add_edge("finalize_success", END)
    return builder.compile(checkpointer=checkpointer)
