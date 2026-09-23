"""Pydantic contract for the deterministic Python/Go executor tools' output.

Not LLM-produced (unlike the other Phase 2 schemas) — no min_length
constraints, matching schemas/task.py's precedent of plain typed fields for
data that isn't validating free-form model output.
"""

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    passed: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
