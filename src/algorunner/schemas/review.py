"""Pydantic contracts for the Reviewer node's structured output.

Mirrors schemas/task.py's conventions (Field(..., min_length=1) on every
required free-text field so structurally-empty LLM output is rejected at the
schema layer).
"""

from typing import Literal

from pydantic import BaseModel, Field

IssueCategory = Literal[
    "algorithm_soundness",
    "correctness",
    "edge_case",
    "complexity",
    "code_quality",
]

Severity = Literal["critical", "minor"]


class Issue(BaseModel):
    category: IssueCategory
    severity: Severity
    description: str = Field(..., min_length=1)


class ReviewResult(BaseModel):
    passed: bool
    issues: list[Issue]
    required_changes: list[str]
    complexity_reasoning: str = Field(..., min_length=1)
    handled_edge_cases: list[str] = Field(default_factory=list)
