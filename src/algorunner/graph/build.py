"""Compiled LangGraph StateGraph for the real Phase 2 pipeline, checkpointed
to Postgres (D-12).

As of this plan the pipeline is a single real node (Analyzer) followed by a
`finalize_success` node; later plans (02-03..02-07) extend this same graph
with Strategist/Solver/CodeGen/TestGen/Reviewer nodes and the correction-loop
conditional edges — this module keeps the injected-checkpointer convention
established by Phase 1's stub graph (the checkpointer is never constructed
here, only wired in — `worker/tasks.py` owns construction).

Replaces Phase 1's `build_stub_graph`/`stub_node` — the Phase-1-only magic-
string failure-simulation hook is retired; real pipeline failure paths
(CR-01 in `worker/tasks.py`) now supersede it.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.graph.state import GraphState


async def finalize_success(state: GraphState) -> dict:
    """Writes the final `result` dict for a successfully completed run.

    Later plans extend this function's body to add `solution`/`review`
    fields as more nodes land — never replace it wholesale.
    """
    return {
        "result": {
            "analysis": state["analysis"].model_dump() if state["analysis"] else None,
        }
    }


def build_pipeline_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(GraphState)
    builder.add_node("analyzer", problem_analyzer_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_edge(START, "analyzer")
    builder.add_edge("analyzer", "finalize_success")
    builder.add_edge("finalize_success", END)
    return builder.compile(checkpointer=checkpointer)
