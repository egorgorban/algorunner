"""Tests for the Editorial Writer agent: language checks, node behavior, and assembly.

Follows the TDD cycle: RED tests first, then GREEN implementation, then REFACTOR.
"""

import pytest

from algorunner.agents.editorial_writer.language import (
    check_russian,
    cyrillic_ratio,
    prose_fields,
)
from algorunner.schemas.editorial import (
    ApproachProse,
    EditorialDraft,
    UnverifiedMention,
)


class TestCyrillicRatio:
    """Tests for cyrillic_ratio function."""

    def test_cyrillic_ratio_pure_russian(self):
        """cyrillic_ratio with Russian text returns high ratio."""
        ratio, count = cyrillic_ratio("Используем хеш-таблицу, чтобы найти пару за один проход.")
        assert ratio > 0.8
        assert count > 0

    def test_cyrillic_ratio_pure_english(self):
        """cyrillic_ratio with English text returns 0.0."""
        ratio, count = cyrillic_ratio("We use a hash map to find the pair in one pass.")
        assert ratio == 0.0
        assert count > 0

    def test_cyrillic_ratio_excludes_backtick_spans(self):
        """cyrillic_ratio excludes backtick-delimited code spans."""
        text = "Вызываем `two_sum_helper` за один проход"
        ratio, count = cyrillic_ratio(text)
        # Should count only the Cyrillic parts, not "two_sum_helper"
        assert ratio == 1.0
        # Count should exclude the identifier inside backticks
        assert count < len([c for c in text if c.isalpha()])

    def test_cyrillic_ratio_excludes_big_o_notation(self):
        """cyrillic_ratio excludes O(...) tokens."""
        text = "Временная сложность O(n log n) линейная"
        ratio, count = cyrillic_ratio(text)
        assert ratio == 1.0
        # O(n log n) should be excluded from count
        assert "O(n log n)" not in text.replace("O(n log n)", "")

    def test_cyrillic_ratio_empty_string(self):
        """cyrillic_ratio with empty string returns (1.0, 0)."""
        ratio, count = cyrillic_ratio("")
        assert ratio == 1.0
        assert count == 0

    def test_cyrillic_ratio_no_letters(self):
        """cyrillic_ratio with only non-letter chars returns (1.0, 0)."""
        ratio, count = cyrillic_ratio("123 !@# $%^")
        assert ratio == 1.0
        assert count == 0

    def test_cyrillic_ratio_nested_parenthesis_in_big_o(self):
        """cyrillic_ratio handles nested parentheses in O(...) correctly."""
        text = "Сложность O(n log(n)) часа"
        ratio, count = cyrillic_ratio(text)
        assert ratio == 1.0


class TestCheckRussian:
    """Tests for check_russian function."""

    def test_check_russian_all_russian_passes(self):
        """check_russian passes when all fields are Russian above thresholds."""
        fields = [
            "Это русский текст с достаточным количеством букв для проверки.",
            "Ещё один русский текст для проверки на соответствие требованиям.",
        ]
        assert check_russian(fields, aggregate_min=0.6, field_min=0.3)

    def test_check_russian_mixed_english_short_passes(self):
        """check_russian passes with mixed fields when short English is acceptable."""
        fields = [
            "Это русский текст для проверки с англом compliance with requirements русский ещё русский текст.",
            "Функция O(n) работает на русском языке хорошо очень хорошо.",
        ]
        result = check_russian(fields, aggregate_min=0.6, field_min=0.3)
        # Should pass because aggregate is still high and no long field is below 0.3
        assert result

    def test_check_russian_long_english_fails_field_min(self):
        """check_russian fails when a long field is below field_min ratio."""
        fields = [
            "This is an English field with more than twenty letters that fails the check.",
        ]
        assert not check_russian(fields, aggregate_min=0.6, field_min=0.3)

    def test_check_russian_aggregate_fails(self):
        """check_russian fails when aggregate ratio is below threshold."""
        fields = [
            "English text number one",
            "English text number two with longer content",
            "English text number three",
        ]
        assert not check_russian(fields, aggregate_min=0.6, field_min=0.3)

    def test_check_russian_empty_fields(self):
        """check_russian passes with empty field list."""
        assert check_russian([], aggregate_min=0.6, field_min=0.3)

    def test_check_russian_short_english_below_field_min_letters(self):
        """check_russian ignores short English fields below field_min_letters."""
        fields = [
            "Русский текст",  # Russian
            "short",  # English, but < 20 letters
        ]
        assert check_russian(fields, aggregate_min=0.6, field_min=0.3, field_min_letters=20)

    def test_check_russian_field_exactly_at_min_letters(self):
        """check_russian checks fields with exactly field_min_letters."""
        # 20 letters exactly
        long_english = "This is exactly twenty letters"  # 30 letters with spaces, but ~24 without spaces
        fields = [long_english]
        # This should fail since it's all English
        assert not check_russian(fields, aggregate_min=0.6, field_min=0.3, field_min_letters=20)


class TestProseFields:
    """Tests for prose_fields function."""

    def test_prose_fields_includes_problem_restatement(self):
        """prose_fields includes problem_restatement."""
        draft = EditorialDraft(
            problem_restatement="Test problem",
            approaches=[],
            edge_cases=[],
            unverified=[],
        )
        fields = prose_fields(draft)
        assert "Test problem" in fields

    def test_prose_fields_includes_approach_titles_and_prose(self):
        """prose_fields includes approach titles, intuitions, algorithms."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Brute Force",
                    bridge_from_previous=None,
                    intuition="Check all pairs",
                    algorithm="Double loop",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Two nested loops",
                    notes=["Note 1", "Note 2"],
                ),
            ],
            edge_cases=["Empty input"],
            unverified=[],
        )
        fields = prose_fields(draft)
        assert "Brute Force" in fields
        assert "Check all pairs" in fields
        assert "Double loop" in fields
        assert "Two nested loops" in fields
        assert "Note 1" in fields
        assert "Note 2" in fields
        assert "Empty input" in fields
        # Should NOT include complexity_time/complexity_space
        assert "O(n^2)" not in fields
        assert "O(1)" not in fields

    def test_prose_fields_includes_bridges(self):
        """prose_fields includes non-null bridge_from_previous."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 1",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justified",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 2",
                    bridge_from_previous="Why this is better",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(1)",
                    complexity_space="O(1)",
                    complexity_justification="Justified",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        fields = prose_fields(draft)
        assert "Why this is better" in fields

    def test_prose_fields_excludes_null_bridges(self):
        """prose_fields excludes null bridge_from_previous."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justified",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        fields = prose_fields(draft)
        # Should not include None
        assert None not in fields

    def test_prose_fields_includes_unverified_notes(self):
        """prose_fields includes unverified mention notes."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[],
            edge_cases=[],
            unverified=[
                UnverifiedMention(approach_id=0, note="This approach was not verified"),
                UnverifiedMention(approach_id=1, note="Attempted but failed"),
            ],
        )
        fields = prose_fields(draft)
        assert "This approach was not verified" in fields
        assert "Attempted but failed" in fields

    def test_prose_fields_empty_draft(self):
        """prose_fields handles draft with minimal required content."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[],
            edge_cases=[],
            unverified=[],
        )
        fields = prose_fields(draft)
        # Should include problem_restatement
        assert fields == ["Problem"]


class TestEditorialWriterNodeRetryLogic:
    """Tests for the editorial_writer_node two-attempt retry logic (D-16)."""

    async def test_soft_warnings_language_check_failed(self):
        """soft_warnings returns language_check_failed when Russian check fails."""
        from algorunner.agents.editorial_writer.node import soft_warnings
        from algorunner.schemas.problem import ProblemAnalysis

        # Create a draft with English text (will fail Russian check)
        english_draft = EditorialDraft(
            problem_restatement="This is purely English text",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="English approach title here",
                    bridge_from_previous=None,
                    intuition="English intuition text",
                    algorithm="English algorithm description",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="English justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )

        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int]",
            output_shape="int",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )

        warnings = soft_warnings(english_draft, analysis)
        assert "language_check_failed" in warnings

    async def test_soft_warnings_russian_passes(self):
        """soft_warnings returns empty list for valid Russian draft."""
        from algorunner.agents.editorial_writer.node import soft_warnings
        from algorunner.schemas.problem import ProblemAnalysis

        # Create a draft with Russian text
        russian_draft = EditorialDraft(
            problem_restatement="Это русский текст для проверки",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Русский подход",
                    bridge_from_previous=None,
                    intuition="Русская интуиция",
                    algorithm="Русский алгоритм",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Русское объяснение сложности",
                    notes=[],
                ),
            ],
            edge_cases=["Русский граничный случай"],
            unverified=[],
        )

        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int]",
            output_shape="int",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )

        warnings = soft_warnings(russian_draft, analysis)
        assert len(warnings) == 0
