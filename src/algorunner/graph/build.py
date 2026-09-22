"""Compiled single-node LangGraph StateGraph, checkpointed to Postgres (D-12).

This is a Python 3.14/LangGraph compatibility smoke test wrapping the D-04-D-07
placeholder success/fail logic — not functional pipeline logic. Kept trivial.
"""

import asyncio
import random

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.graph.state import StubGraphState
from algorunner.worker.tasks import FAIL_TEST_MARKER


async def stub_node(state: StubGraphState) -> dict:
    await asyncio.sleep(random.uniform(2, 5))  # D-06, moved here from worker/tasks.py

    if FAIL_TEST_MARKER in state["problem_text"]:  # D-05
        return {
            "error": {
                "code": "SIMULATED_FAILURE",
                "message": "Task failed via FAIL_TEST marker",
            }
        }

    return {"result": {"message": "stub pipeline completed"}}


def build_stub_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(StubGraphState)
    builder.add_node("stub", stub_node)
    builder.add_edge(START, "stub")
    builder.add_edge("stub", END)
    return builder.compile(checkpointer=checkpointer)
