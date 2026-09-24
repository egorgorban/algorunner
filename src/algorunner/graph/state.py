"""LangGraph state schema for the Phase 3 multi-approach pipeline (D-08, D-13).

Phase 3 introduces the per-approach branch pattern (RESEARCH Pattern 1). The
parent `GraphState` holds the problem context and the dict of outcomes,
one per approach. Each branch receives an `ApproachInput` (the Send payload),
which becomes the parent for `ApproachState` — the branch's working state.

The per-solution fields (solution, solver_output, python_execution, go_execution,
review, review_history, iterations) have been REMOVED from the parent GraphState
and now exist only per branch in ApproachState (promotion decision). This keeps
parent state clean and makes per-approach timing/isolation natural.

The one reducer exception: `approach_outcomes` uses `merge_outcomes` instead of
the default update semantics (RESEARCH Pattern 1, Pitfall 3). A re-invoke of the
parent graph would duplicate outcomes if we used `operator.add`; the reducer
merges left and right dicts instead, which is idempotent for a new
(re-invoked) parent invoking the same thread_id.
"""

import operator
from typing import Annotated, TypedDict

from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.outcome import ApproachOutcome
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.review import ReviewResult
from algorunner.schemas.solution import Approach, Solution


def merge_outcomes(left: dict[int, ApproachOutcome], right: dict[int, ApproachOutcome]) -> dict[int, ApproachOutcome]:
    """Idempotent merge for approach_outcomes (RESEARCH Pattern 1, Pitfall 3).

    On a re-invoke of the parent graph with the same thread_id, new branches
    are invoked alongside existing checkpoints. The reducer combines them by
    merging both dicts, preferring right (new) over left (prior). This is the
    only exception to TypedDict's default update semantics in GraphState.
    """
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict):
    """Parent graph state for Phase 3 multi-approach pipeline.

    Holds the problem context, the dict of approach outcomes (one per attempted
    approach, indexed by approach_idx), and the terminal result or error.
    All per-solution working state (solver_output, execution results, etc.) is
    removed here and now lives only in ApproachState per branch.
    """

    task_id: str
    problem_text: str
    language: str
    examples: list[dict]
    analysis: ProblemAnalysis | None
    clarification_rounds: int
    clarification_answer: str | None
    assumption_stated: str | None
    approaches: list[Approach]
    max_iterations: int
    # The only reducer field: merge_outcomes is idempotent under re-invoke.
    approach_outcomes: Annotated[dict[int, ApproachOutcome], merge_outcomes]
    result: dict | None
    error: dict | None


class ApproachInput(TypedDict):
    """Input to a per-approach branch (Send payload from fan_out_approaches).

    A subset of GraphState plus the approach_idx identifying which approach
    this branch will elaborate. Becomes the base for ApproachState.
    """

    task_id: str
    approach_idx: int
    approach: Approach
    problem_text: str
    examples: list[dict]
    analysis: ProblemAnalysis | None
    assumption_stated: str | None
    max_iterations: int


class ApproachState(ApproachInput):
    """Branch state for one per-approach subgraph execution.

    Extends ApproachInput with all the working state that Phase 2 kept in
    GraphState: solver_output, solution, execution results, review history.
    Each branch has its own isolated copies of these fields, indexed by
    approach_idx and never written back to the parent until outcome_from_final.

    No reducers on any per-solution field: nodes explicitly return
    `{..., solver_output: new_value, ...}` and graph edges handle composition.
    """

    solver_output: dict | None
    solution: Solution | None
    python_execution: ExecutionResult | None
    go_execution: ExecutionResult | None
    review: ReviewResult | None
    review_history: list[ReviewResult]
    iterations: int
