"""Pydantic contracts for the Solution Strategist/Solver/Code Generator
nodes' structured output.

Mirrors schemas/task.py's conventions (Field(..., min_length=1) on every
required free-text field so structurally-empty LLM output is rejected at the
schema layer).
"""

from pydantic import BaseModel, Field


class Approach(BaseModel):
    name: str = Field(..., min_length=1)
    technique: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)


class Solution(BaseModel):
    approach: Approach
    algorithm: str = Field(..., min_length=1)
    code_python: str = Field(..., min_length=1)
    code_go: str = Field(..., min_length=1)
    tests: list[dict]
    complexity_time: str = Field(..., min_length=1)
    complexity_space: str = Field(..., min_length=1)
