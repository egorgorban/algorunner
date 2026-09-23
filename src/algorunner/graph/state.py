"""LangGraph state schema for the real Phase 2 pipeline (D-12).

This is the full, final Phase 2 shape — all fields are defined now even
though most remain unused until later plans (02-03..02-07) populate them, so
this file does not need to be touched again as more nodes land.

Plain `TypedDict`, no `Annotated`/reducer fields (RESEARCH.md Pattern 4):
every list-valued field (e.g. `review_history`) is built via explicit
`state[...] + [new_item]` returns from node functions, never an
automatic-accumulation reducer — `max_iterations` already bounds these lists,
so a reducer would add complexity for no benefit.

Replaces Phase 1's `StubGraphState` smoke-test stub.
"""

from typing import TypedDict

from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.review import ReviewResult
from algorunner.schemas.solution import Approach, Solution


class GraphState(TypedDict):
    task_id: str
    problem_text: str
    language: str
    examples: list[dict]
    analysis: ProblemAnalysis | None
    clarification_rounds: int
    assumption_stated: str | None
    approaches: list[Approach]
    solution: Solution | None
    python_execution: ExecutionResult | None
    go_execution: ExecutionResult | None
    review: ReviewResult | None
    review_history: list[ReviewResult]
    iterations: int
    max_iterations: int
    result: dict | None
    error: dict | None
