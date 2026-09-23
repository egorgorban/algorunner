"""Pydantic contract for the Problem Analyzer node's structured output.

Mirrors schemas/task.py's conventions (Field(..., min_length=1) on every
required free-text field so structurally-empty LLM output is rejected at the
schema layer, before it ever reaches an agent node or an executor tool).
"""

from typing import Literal

from pydantic import BaseModel, Field


class ProblemAnalysis(BaseModel):
    constraints: list[str]
    input_shape: str = Field(..., min_length=1)
    output_shape: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    difficulty: Literal["easy", "medium", "hard"]
    needs_clarification: bool
    clarification_question: str | None = None
