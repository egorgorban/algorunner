"""Pydantic contract for per-approach outcomes in the Phase 3 multi-approach pipeline.

Not LLM-produced (unlike most Phase 2/3 schemas) — the outcome aggregates real
execution results and the review decision, neither of which is free-form text.
Plain typed fields per schemas/execution.py precedent, no min_length constraints.
"""

from typing import Literal

from pydantic import BaseModel

from algorunner.schemas.review import ReviewResult
from algorunner.schemas.solution import Approach, Solution

ApproachStatus = Literal["verified", "exhausted", "timed_out", "errored"]


class ApproachOutcome(BaseModel):
    """The terminal outcome of one per-approach branch execution.

    A branch's approach is "verified" only when its final review passed, a
    final Solution exists, and both its Python and Go executions passed
    (Core Value defense in depth). Every other ending is "exhausted"
    (correction loop max_iterations hit), "timed_out" (worker deadline),
    or "errored" (exception).
    """

    approach_idx: int
    approach: Approach
    status: ApproachStatus
    iterations: int
    final_solution: Solution | None
    final_review: ReviewResult | None
    error: str | None

    @classmethod
    def not_verified(
        cls,
        *,
        approach_idx: int,
        approach: Approach,
        status: Literal["timed_out", "errored"],
        error: str | None = None,
    ) -> "ApproachOutcome":
        """Construct an unverified outcome (e.g., for early timeout or exception).

        Sets iterations=0 and both finals to None. Truncates error to 500 chars
        (matching reviewer/node.py's stderr truncation for consistency).
        """
        truncated_error = error[:500] if error else None
        return cls(
            approach_idx=approach_idx,
            approach=approach,
            status=status,
            iterations=0,
            final_solution=None,
            final_review=None,
            error=truncated_error,
        )
