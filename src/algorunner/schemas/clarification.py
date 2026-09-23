"""Pydantic contracts for the clarification pause/resume flow (D-03).

Mirrors schemas/task.py's minimal-response-model shape (TaskCreateResponse).
"""

from pydantic import BaseModel, Field


class ClarificationQuestion(BaseModel):
    question: str


class ClarificationAnswer(BaseModel):
    answer: str = Field(..., max_length=5000)
