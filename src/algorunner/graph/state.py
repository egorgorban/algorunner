"""LangGraph state schema for the Phase 1 stub graph (D-12).

This is a Python 3.14/LangGraph compatibility smoke test, not functional
pipeline logic — keep the shape trivial. Phase 2 replaces this with the real
Analyzer/Solver/etc. state.
"""

from typing import TypedDict


class StubGraphState(TypedDict):
    task_id: str
    problem_text: str
    result: dict | None
    error: dict | None
