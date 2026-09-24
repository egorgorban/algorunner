"""Deterministic Russian language check for Editorial Writer output.

Pattern 7 (RESEARCH): Cyrillic-ratio check on prose fields to verify Russian-language output.
Excludes code spans (backticks) and Big-O notation O(...) from the ratio calculation.
"""

import re

from algorunner.schemas.editorial import EditorialDraft

# Cyrillic block U+0400-U+04FF (includes Russian, Ukrainian, Serbian, etc.)
_CYR = re.compile(r"[Ѐ-ӿ]")

# Backtick-delimited code spans (e.g., `variable_name`)
_CODE_SPAN = re.compile(r"`[^`]*`")

# Big-O notation tokens O(...)
_BIG_O = re.compile(r"O\([^)]*(?:\([^)]*\)[^)]*)*\)")


def cyrillic_ratio(text: str) -> tuple[float, int]:
    """Calculate the Cyrillic letter ratio in text.

    Removes code spans (backtick-delimited) and Big-O notation before counting.
    Returns (ratio, letter_count) where:
    - ratio: Cyrillic letters / total letters, or 1.0 if no letters
    - letter_count: total number of alphabetic characters (after removing spans)

    Args:
        text: The text to analyze

    Returns:
        (cyrillic_ratio, total_letter_count)

    Examples:
        cyrillic_ratio("Используем хеш-таблицу, чтобы найти пару за один проход.")
            -> (0.95+, 47) [Russian prose, high ratio]
        cyrillic_ratio("We use a hash map to find the pair in one pass.")
            -> (0.0, 40) [English prose, zero ratio]
        cyrillic_ratio("Вызываем `two_sum_helper` за O(n log n)")
            -> (1.0, 8) [Russian with excluded code span and Big-O]
    """
    # Remove code spans
    cleaned = _CODE_SPAN.sub("", text)
    # Remove Big-O notation
    cleaned = _BIG_O.sub("", cleaned)

    # Count letters
    letters = [c for c in cleaned if c.isalpha()]
    if not letters:
        return 1.0, 0

    cyrillic = len([c for c in letters if _CYR.search(c)])
    return cyrillic / len(letters), len(letters)


def check_russian(
    fields: list[str],
    *,
    aggregate_min: float,
    field_min: float,
    field_min_letters: int = 20,
) -> bool:
    """Check that prose fields meet Russian-language thresholds.

    Passes iff:
    1. The aggregate Cyrillic ratio across all fields is >= aggregate_min, AND
    2. Every field with >= field_min_letters letters has ratio >= field_min

    Args:
        fields: List of prose strings to check
        aggregate_min: Minimum ratio for the aggregate (e.g., 0.6)
        field_min: Minimum ratio for fields with >= field_min_letters (e.g., 0.3)
        field_min_letters: Threshold for per-field checking (default 20)

    Returns:
        True if all conditions are met, False otherwise
    """
    if not fields:
        return True

    total_cyrillic = 0
    total_letters = 0

    for field in fields:
        ratio, letter_count = cyrillic_ratio(field)
        total_cyrillic += int(ratio * letter_count)
        total_letters += letter_count

        # Per-field check: if field is long enough, must meet field_min
        if letter_count >= field_min_letters and ratio < field_min:
            return False

    # Aggregate check
    if total_letters == 0:
        return True
    aggregate_ratio = total_cyrillic / total_letters
    return aggregate_ratio >= aggregate_min


def prose_fields(draft: EditorialDraft) -> list[str]:
    """Extract prose fields from an EditorialDraft for language checking.

    Includes:
    - problem_restatement
    - per-approach: title, bridge_from_previous (if not None), intuition, algorithm, complexity_justification, notes
    - edge_cases
    - unverified notes

    Excludes complexity_time/complexity_space (these are code-like and not prose).

    Args:
        draft: The EditorialDraft to extract from

    Returns:
        List of all prose strings to check
    """
    fields = []

    # Problem restatement
    if draft.problem_restatement:
        fields.append(draft.problem_restatement)

    # Per-approach prose
    for approach in draft.approaches:
        if approach.title:
            fields.append(approach.title)
        if approach.bridge_from_previous is not None:
            fields.append(approach.bridge_from_previous)
        if approach.intuition:
            fields.append(approach.intuition)
        if approach.algorithm:
            fields.append(approach.algorithm)
        if approach.complexity_justification:
            fields.append(approach.complexity_justification)
        # Notes are a list of strings
        for note in (approach.notes or []):
            if note:
                fields.append(note)

    # Edge cases
    for case in (draft.edge_cases or []):
        if case:
            fields.append(case)

    # Unverified approach notes
    for mention in (draft.unverified or []):
        if mention.note:
            fields.append(mention.note)

    return fields
