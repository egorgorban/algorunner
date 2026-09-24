"""Deterministic assembly of the Editorial Writer's LLM draft into a final Editorial.

This module handles:
- Extracting Big-O notation from complexity claims
- Validating the LLM draft against the verified approach set
- Injecting code (byte-identical from executed Solutions), difficulty, tags, and role
- Ensuring ordering and bridge consistency
"""

import re
from typing import Literal

from algorunner.schemas.editorial import (
    Editorial,
    EditorialApproach,
    EditorialDraft,
    UnverifiedApproach,
)
from algorunner.schemas.outcome import ApproachOutcome, ApproachStatus
from algorunner.schemas.problem import ProblemAnalysis

# Fallback note for unverified approaches when the LLM draft provides no mention
UNVERIFIED_FALLBACK_NOTE = "Этот подход был опробован, но не прошёл автоматическую проверку, поэтому код не приводится."


def extract_big_o(text: str) -> str | None:
    """Extract the first balanced-parenthesis O(...) token from text.

    Examples:
        extract_big_o("O(n log(n)) time, sort then scan") -> "O(n log(n))"
        extract_big_o("linear time") -> None
    """
    if not text:
        return None

    # Find the first occurrence of "O("
    start_idx = text.find("O(")
    if start_idx == -1:
        return None

    # Now extract the balanced parentheses starting from "O("
    i = start_idx + 2  # Skip "O("
    paren_count = 1
    end_idx = -1

    while i < len(text) and paren_count > 0:
        if text[i] == "(":
            paren_count += 1
        elif text[i] == ")":
            paren_count -= 1
            if paren_count == 0:
                end_idx = i
                break
        i += 1

    if end_idx != -1:
        return text[start_idx : end_idx + 1]

    return None


def validate_draft(
    draft: EditorialDraft,
    verified_ids: set[int],
    unverified_ids: set[int],
) -> None:
    """Validate the LLM draft against the verified and unverified approach sets.

    Raises ValueError if:
    - Approach ids are duplicated
    - The approach id set differs from verified_ids
    - An unverified mention id is outside unverified_ids
    - A bridge is blank at any position >= 1
    """
    # Extract approach ids from draft
    draft_ids = [approach.approach_id for approach in draft.approaches]

    # Check for duplicates
    if len(draft_ids) != len(set(draft_ids)):
        raise ValueError("approach ids are duplicated in the draft")

    # Check that approach_id set matches verified_ids
    if set(draft_ids) != verified_ids:
        raise ValueError("approach_id set differs from verified_ids")

    # Check that unverified mentions are valid
    for mention in draft.unverified:
        if mention.approach_id not in unverified_ids:
            raise ValueError(f"unverified mention approach_id {mention.approach_id} not in unverified_ids")

    # Check that bridges are non-blank after position 0
    for idx, approach in enumerate(draft.approaches):
        if idx > 0 and (approach.bridge_from_previous is None or approach.bridge_from_previous.strip() == ""):
            raise ValueError(f"blank bridge at position {idx}")


def assemble_editorial(
    draft: EditorialDraft,
    analysis: ProblemAnalysis,
    outcomes: dict[int, ApproachOutcome],
) -> Editorial:
    """Assemble the LLM draft into a final Editorial with injected metadata.

    Calls validate_draft first, then builds EditorialApproach entries in draft order,
    injecting code (byte-for-byte), Big-O notation, difficulty, tags and role.

    Args:
        draft: The LLM-authored draft from EditorialWriter
        analysis: The problem analysis containing difficulty
        outcomes: Map of approach_id to ApproachOutcome (contains final solutions)

    Returns:
        Editorial with all fields populated and validated
    """
    # Separate verified and non-verified outcomes
    verified_ids = {id for id, outcome in outcomes.items() if outcome.status == "verified"}
    unverified_ids = {id for id, outcome in outcomes.items() if outcome.status != "verified"}

    # Validate the draft
    validate_draft(draft, verified_ids, unverified_ids)

    # Build editorial approaches in draft order
    editorial_approaches = []
    techniques_in_order = []

    for idx, prose in enumerate(draft.approaches):
        outcome = outcomes[prose.approach_id]
        solution = outcome.final_solution

        # Extract Big-O from the solution's complexity claims, falling back to prose text
        complexity_time = extract_big_o(solution.complexity_time) or prose.complexity_time
        complexity_space = extract_big_o(solution.complexity_space) or prose.complexity_space

        # Force the first approach's bridge to None
        bridge = None if idx == 0 else prose.bridge_from_previous

        # Create the assembled approach
        editorial_approach = EditorialApproach(
            approach_id=prose.approach_id,
            role=outcome.approach.role,
            technique=outcome.approach.technique,
            title=prose.title,
            bridge_from_previous=bridge,
            intuition=prose.intuition,
            algorithm=prose.algorithm,
            code_python=solution.code_python,
            code_go=solution.code_go,
            complexity_time=complexity_time,
            complexity_space=complexity_space,
            complexity_justification=prose.complexity_justification,
            notes=prose.notes,
        )
        editorial_approaches.append(editorial_approach)
        techniques_in_order.append(outcome.approach.technique)

    # Build unverified approaches (those in outcomes but not in draft)
    unverified_approaches = []
    for approach_idx, outcome in sorted(outcomes.items(), key=lambda x: x[0]):
        if outcome.status != "verified":
            # Find if there's a mention in the draft
            draft_mention = None
            for mention in draft.unverified:
                if mention.approach_id == approach_idx:
                    draft_mention = mention
                    break

            note = draft_mention.note if draft_mention else UNVERIFIED_FALLBACK_NOTE
            unverified_approach = UnverifiedApproach(
                approach_id=approach_idx,
                name=outcome.approach.name,
                status=outcome.status,  # type: ignore
                note=note,
            )
            unverified_approaches.append(unverified_approach)

    # Create and return the final Editorial
    return Editorial(
        problem_restatement=draft.problem_restatement,
        difficulty=analysis.difficulty,
        tags=techniques_in_order,  # De-duplicated by virtue of iterating draft in order
        approaches=editorial_approaches,
        edge_cases=draft.edge_cases,
        unverified_approaches=unverified_approaches,
    )
