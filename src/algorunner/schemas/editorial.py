"""Pydantic contracts for the Editorial Writer agent's structured output.

Follows the pattern established in schemas/review.py: LLM-authored models use
Field(..., min_length=1) on every required free-text field so structurally-empty
LLM output is rejected at the schema layer. Assembled models (after the Writer
node and assembly step) use plain typed fields.
"""

from typing import Literal

from pydantic import BaseModel, Field

from algorunner.schemas.solution import ApproachRole


class ApproachProse(BaseModel):
    """LLM-authored prose for one approach from the Editorial Writer draft."""

    approach_id: int
    title: str = Field(..., min_length=1)
    bridge_from_previous: str | None
    intuition: str = Field(..., min_length=1)
    algorithm: str = Field(..., min_length=1)
    complexity_time: str = Field(..., min_length=1)
    complexity_space: str = Field(..., min_length=1)
    complexity_justification: str = Field(..., min_length=1)
    notes: list[str]


class UnverifiedMention(BaseModel):
    """LLM-authored mention of an unverified approach from the Editorial Writer draft."""

    approach_id: int
    note: str = Field(..., min_length=1)


class EditorialDraft(BaseModel):
    """The Editorial Writer LLM's structured response (response_format container).

    Contains the draft editorial with LLM-authored prose, ordered by the Writer's
    choice. This is validated by assembly.validate_draft then transformed into
    an Editorial via assembly.assemble_editorial.
    """

    problem_restatement: str = Field(..., min_length=1)
    approaches: list[ApproachProse]
    edge_cases: list[str]
    unverified: list[UnverifiedMention]


class EditorialApproach(BaseModel):
    """Assembled, final editorial approach with injected code and difficulty metadata.

    Fields appear in fixed order in model_dump(): intuition, algorithm,
    code_python, code_go, complexity_time, complexity_space, complexity_justification.
    """

    approach_id: int
    role: ApproachRole
    technique: str
    title: str
    bridge_from_previous: str | None
    intuition: str
    algorithm: str
    code_python: str
    code_go: str
    complexity_time: str
    complexity_space: str
    complexity_justification: str
    notes: list[str]

    def model_dump(self, **kwargs):
        """Override model_dump to enforce field order."""
        full_dump = super().model_dump(**kwargs)
        # Reorder to match the spec: intuition first, then algorithm, code_python, code_go,
        # then complexity fields, then complexity_justification
        ordered = {}

        # Add fields in the required order
        for key in [
            "approach_id",
            "role",
            "technique",
            "title",
            "bridge_from_previous",
            "intuition",
            "algorithm",
            "code_python",
            "code_go",
            "complexity_time",
            "complexity_space",
            "complexity_justification",
            "notes",
        ]:
            if key in full_dump:
                ordered[key] = full_dump[key]

        return ordered


class UnverifiedApproach(BaseModel):
    """Assembled mention of an unverified approach in the final Editorial."""

    approach_id: int
    name: str
    status: Literal["exhausted", "timed_out", "errored"]
    note: str


class Editorial(BaseModel):
    """The final, assembled Editorial with injected code, difficulty, tags and role.

    This is the API-visible contract that Phase 4 renders. Code fields are
    byte-identical to the executed, reviewed Solutions. Difficulty, tags, role
    and Big-O notation are injected deterministically. Prose fields come from
    the Writer's one structured-output call.
    """

    problem_restatement: str
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str]
    approaches: list[EditorialApproach]
    edge_cases: list[str]
    unverified_approaches: list[UnverifiedApproach]
