"""Pydantic schemas for the task lifecycle — the validated contract crossing
the client -> API, API -> storage, and storage -> API boundaries.

Field names/constraints here are locked by 01-CONTEXT.md decisions
D-01/D-02/D-03/D-07/D-08/D-10 — not a stylistic choice, follow verbatim.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class Language(str, Enum):
    EN = "en"
    RU = "ru"


class Example(BaseModel):
    input: str
    output: str
    explanation: str | None = None


class TaskSubmission(BaseModel):
    problem_text: str = Field(..., max_length=5000)
    language: Language
    examples: list[Example] = Field(default_factory=list, max_length=10)


class TaskStatus(str, Enum):
    """Full future pipeline status vocabulary (D-08) — all 12 values defined
    now even though only QUEUED/ANALYZING_PROBLEM/COMPLETED/FAILED are
    reachable in Phase 1. Stored as a plain VARCHAR(32) column validated by
    this enum, not a native Postgres ENUM type (D-10)."""

    QUEUED = "queued"
    ANALYZING_PROBLEM = "analyzing_problem"
    DESIGNING_SOLUTION = "designing_solution"
    GENERATING_CODE = "generating_code"
    GENERATING_TESTS = "generating_tests"
    EXECUTING_TESTS = "executing_tests"
    REVIEWING = "reviewing"
    CORRECTING = "correcting"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    WRITING_EDITORIAL = "writing_editorial"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskError(BaseModel):
    """Structured error shape (D-07) — never a plain string."""

    code: str
    message: str


class TaskRecord(BaseModel):
    id: UUID
    status: TaskStatus
    problem_text: str
    language: Language
    examples: list[Example]
    result: dict | None = None
    error: TaskError | None = None
    clarification_question: str | None = None
    active_execution_seconds: float = 0.0
    created_at: datetime
    updated_at: datetime


class TaskCreateResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
