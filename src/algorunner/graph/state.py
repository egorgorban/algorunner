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
    # Plan 02-07: the user's answer to the Analyzer's clarification question,
    # set by `clarification_gate_node` on resume (additive field).
    clarification_answer: str | None
    assumption_stated: str | None
    approaches: list[Approach]
    solution: Solution | None
    # Plan 02-03's Solver returns a partial-elaboration shape here (approach +
    # algorithm + complexity, no code/tests yet) — Plan 02-04's Code
    # Generator folds this into a real `Solution` once code_python/code_go/
    # tests exist. The one additive edit to this file since Plan 02-02's
    # "full 16-field shape, never touched again" framing — the Solver/Code
    # Generator split was not knowable until this plan's design decision.
    solver_output: dict | None
    python_execution: ExecutionResult | None
    go_execution: ExecutionResult | None
    review: ReviewResult | None
    review_history: list[ReviewResult]
    iterations: int
    max_iterations: int
    result: dict | None
    error: dict | None
