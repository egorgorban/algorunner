"""Compiled single-node LangGraph StateGraph, checkpointed to Postgres (D-12).

This is a Python 3.14/LangGraph compatibility smoke test wrapping the D-04-D-07
placeholder success/fail logic — not functional pipeline logic. Kept trivial.

RED-phase scaffolding: stub_node is intentionally a no-op below (returns {})
so tests/graph/test_build.py fails on its result/error assertions rather than
on an ImportError, before the real behavior lands in the GREEN commit.
"""

import asyncio

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.graph.state import StubGraphState


async def stub_node(state: StubGraphState) -> dict:
    _ = asyncio  # RED-phase scaffolding placeholder; sleep call lands in GREEN
    return {}


def build_stub_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(StubGraphState)
    builder.add_node("stub", stub_node)
    builder.add_edge(START, "stub")
    builder.add_edge("stub", END)
    return builder.compile(checkpointer=checkpointer)
