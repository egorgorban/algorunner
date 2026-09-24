"""Tests for the Editorial Writer agent: contract, prompt, assembly and node.

Follows the TDD cycle: RED tests first, then GREEN implementation, then REFACTOR.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.editorial_writer.assembly import (
    UNVERIFIED_FALLBACK_NOTE,
    assemble_editorial,
    extract_big_o,
    validate_draft,
)
from algorunner.agents.editorial_writer.node import editorial_writer_node
from algorunner.schemas.editorial import (
    ApproachProse,
    Editorial,
    EditorialApproach,
    EditorialDraft,
    UnverifiedMention,
)
from algorunner.schemas.outcome import ApproachOutcome, ApproachStatus
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.review import ReviewResult
from algorunner.schemas.solution import (
    Approach,
    ApproachRole,
    EntryPoint,
    EntryParam,
    Solution,
    StructuredCase,
)


def _approach(
    *,
    name: str = "Test approach",
    technique: str = "test technique",
    summary: str = "Test summary",
    role: ApproachRole = "brute_force",
    rationale: str = "Test rationale",
) -> Approach:
    """Helper to construct an Approach with reasonable defaults."""
    return Approach(
        name=name,
        technique=technique,
        summary=summary,
        role=role,
        rationale=rationale,
    )


def _solution(
    approach: Approach | None = None,
    algorithm: str = "Test algorithm",
    code_python: str = "def solve(): pass",
    code_go: str = "func Solve() {}",
    complexity_time: str = "O(n)",
    complexity_space: str = "O(1)",
) -> Solution:
    """Helper to construct a Solution with reasonable defaults."""
    if approach is None:
        approach = _approach()
    return Solution(
        approach=approach,
        algorithm=algorithm,
        entry_point=EntryPoint(
            python_name="solve",
            go_name="Solve",
            params=[EntryParam(name="arr", type="list[int]")],
            return_type="int",
            unordered_result=False,
        ),
        code_python=code_python,
        code_go=code_go,
        tests=[],
        complexity_time=complexity_time,
        complexity_space=complexity_space,
    )


def _outcome(
    approach_idx: int = 0,
    approach: Approach | None = None,
    status: ApproachStatus = "verified",
    final_solution: Solution | None = None,
    final_review: ReviewResult | None = None,
) -> ApproachOutcome:
    """Helper to construct an ApproachOutcome with reasonable defaults."""
    if approach is None:
        approach = _approach(role="brute_force" if approach_idx == 0 else "optimized")
    if final_solution is None:
        final_solution = _solution(approach)
    if status == "verified" and final_review is None:
        final_review = ReviewResult(
            passed=True,
            issues=[],
            required_changes=[],
            complexity_reasoning="Reasonable complexity",
        )
    return ApproachOutcome(
        approach_idx=approach_idx,
        approach=approach,
        status=status,
        iterations=1,
        final_solution=final_solution,
        final_review=final_review,
        error=None,
    )


def _analysis(**overrides) -> ProblemAnalysis:
    """Helper to create ProblemAnalysis with reasonable defaults."""
    fields = {
        "intent": "Test intent",
        "constraints": [],
        "input_shape": "list[int], int",
        "output_shape": "list[int]",
        "difficulty": "easy",
        "needs_clarification": False,
        "clarification_question": None,
    }
    fields.update(overrides)
    return ProblemAnalysis(**fields)


def _fake_client(parsed, refusal=None):
    """Create a mock OpenAI client that returns a specific parsed value."""
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=refusal))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(parse=AsyncMock(return_value=completion))
        )
    )


class TestExtractBigO:
    """Tests for extract_big_o function."""

    def test_extract_balanced_parenthesis(self):
        """extract_big_o returns the first balanced O(...) token."""
        result = extract_big_o("O(n log(n)) time, sort then scan")
        assert result == "O(n log(n))"

    def test_extract_simple_O_n(self):
        """extract_big_o works with simple O(n)."""
        result = extract_big_o("O(n) linear time complexity")
        assert result == "O(n)"

    def test_extract_nested_parenthesis(self):
        """extract_big_o handles nested parentheses."""
        result = extract_big_o("Time complexity is O(n^2) or worse")
        assert result == "O(n^2)"

    def test_extract_none_when_no_big_o(self):
        """extract_big_o returns None when no O(...) token found."""
        result = extract_big_o("linear time complexity")
        assert result is None

    def test_extract_complex_expression(self):
        """extract_big_o extracts complex nested expressions."""
        result = extract_big_o("O(n log(n log(n))) with constant factors")
        assert result == "O(n log(n log(n)))"


class TestValidateDraft:
    """Tests for validate_draft function."""

    def test_validate_draft_accepts_valid(self):
        """validate_draft accepts a valid draft."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 0",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 1",
                    bridge_from_previous="Why this approach",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(1)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        # Should not raise
        validate_draft(draft, verified_ids={0, 1}, unverified_ids=set())

    def test_validate_draft_rejects_duplicate_id(self):
        """validate_draft raises for duplicated approach ids."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 0",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=0,  # duplicate
                    title="Approach 0 again",
                    bridge_from_previous="Why",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(1)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        with pytest.raises(ValueError, match="duplicate"):
            validate_draft(draft, verified_ids={0}, unverified_ids=set())

    def test_validate_draft_rejects_missing_id(self):
        """validate_draft raises when approach id set differs from verified."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 0",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        # draft has {0}, but verified_ids expects {0, 1}
        with pytest.raises(ValueError, match="approach_id set differs"):
            validate_draft(draft, verified_ids={0, 1}, unverified_ids=set())

    def test_validate_draft_rejects_blank_bridge_at_position_1(self):
        """validate_draft raises for a blank bridge after position 0."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 0",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 1",
                    bridge_from_previous="",  # blank at position 1 - should fail
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(1)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        with pytest.raises(ValueError, match="blank bridge"):
            validate_draft(draft, verified_ids={0, 1}, unverified_ids=set())

    def test_validate_draft_rejects_unverified_mention_outside_set(self):
        """validate_draft raises for unverified mention id outside unverified_ids."""
        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 0",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[
                UnverifiedMention(approach_id=99, note="Some note")  # 99 not in unverified_ids
            ],
        )
        with pytest.raises(ValueError, match="approach_id"):
            validate_draft(draft, verified_ids={0}, unverified_ids={2})


class TestAssembleEditorial:
    """Tests for assemble_editorial function."""

    def test_assemble_editorial_injects_code_byte_for_byte(self):
        """assemble_editorial copies code_python/code_go verbatim from outcomes."""
        approach1 = _approach(name="Approach 1", role="brute_force")
        approach2 = _approach(name="Approach 2", role="optimized")
        solution1 = _solution(approach1, code_python="def brute(): pass", code_go="func Brute() {}")
        solution2 = _solution(approach2, code_python="def optimized(): pass", code_go="func Optimized() {}")
        outcome1 = _outcome(0, approach1, final_solution=solution1)
        outcome2 = _outcome(1, approach2, final_solution=solution2)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 1",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 2",
                    bridge_from_previous="Better approach",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = _analysis()
        outcomes = {0: outcome1, 1: outcome2}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].code_python == "def brute(): pass"
        assert editorial.approaches[0].code_go == "func Brute() {}"
        assert editorial.approaches[1].code_python == "def optimized(): pass"
        assert editorial.approaches[1].code_go == "func Optimized() {}"

    def test_assemble_editorial_preserves_draft_order(self):
        """assemble_editorial preserves approach order from draft."""
        approach1 = _approach(role="brute_force")
        approach2 = _approach(role="optimized")
        outcome1 = _outcome(0, approach1)
        outcome2 = _outcome(1, approach2)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=1,  # intentionally not in ascending order
                    title="Approach 2",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=0,
                    title="Approach 1",
                    bridge_from_previous="Different approach",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = _analysis()
        outcomes = {0: outcome1, 1: outcome2}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].approach_id == 1
        assert editorial.approaches[1].approach_id == 0

    def test_assemble_editorial_forces_first_bridge_none(self):
        """assemble_editorial forces the first approach's bridge to None."""
        approach1 = _approach(role="brute_force")
        outcome1 = _outcome(0, approach1)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach",
                    bridge_from_previous="Should be None",  # should be forced to None
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].bridge_from_previous is None

    def test_assemble_editorial_extracts_big_o(self):
        """assemble_editorial extracts Big-O from complexity claims."""
        approach1 = _approach(role="brute_force")
        solution1 = _solution(approach1, complexity_time="O(n^2) time, nested loop", complexity_space="O(1) space")
        outcome1 = _outcome(0, approach1, final_solution=solution1)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="Quadratic",  # Writer's text without Big-O
                    complexity_space="Constant",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].complexity_time == "O(n^2)"
        assert editorial.approaches[0].complexity_space == "O(1)"

    def test_assemble_editorial_injects_difficulty_and_tags(self):
        """assemble_editorial injects difficulty and tags deterministically."""
        approach1 = _approach(name="Brute force pairs", technique="brute force", role="brute_force")
        approach2 = _approach(name="Hash map approach", technique="hash map", role="optimized")
        outcome1 = _outcome(0, approach1)
        outcome2 = _outcome(1, approach2)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 1",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 2",
                    bridge_from_previous="Better",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(n)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = _analysis(difficulty="hard")
        outcomes = {0: outcome1, 1: outcome2}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.difficulty == "hard"
        assert set(editorial.tags) == {"brute force", "hash map"}

    def test_assemble_editorial_injects_role_from_outcome(self):
        """assemble_editorial sets role from the outcome's approach."""
        approach1 = _approach(role="brute_force")
        approach2 = _approach(role="optimized")
        outcome1 = _outcome(0, approach1)
        outcome2 = _outcome(1, approach2)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach 1",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Approach 2",
                    bridge_from_previous="Better",
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = _analysis()
        outcomes = {0: outcome1, 1: outcome2}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].role == "brute_force"
        assert editorial.approaches[1].role == "optimized"

    def test_assemble_editorial_adds_unverified_with_fallback(self):
        """assemble_editorial adds unverified approaches with fallback note."""
        approach0 = _approach(name="Verified approach", role="brute_force")
        approach1 = _approach(name="Errored approach", role="optimized")
        outcome0 = _outcome(0, approach0)
        outcome1 = ApproachOutcome(
            approach_idx=1,
            approach=approach1,
            status="errored",
            iterations=2,
            final_solution=None,
            final_review=None,
            error="Test error",
        )

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Verified",
                    bridge_from_previous=None,
                    intuition="Intuition",
                    algorithm="Algorithm",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],  # No mention for approach 1
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome0, 1: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert len(editorial.unverified_approaches) == 1
        assert editorial.unverified_approaches[0].approach_id == 1
        assert editorial.unverified_approaches[0].status == "errored"
        assert editorial.unverified_approaches[0].note == UNVERIFIED_FALLBACK_NOTE

    def test_assemble_editorial_single_approach_with_bridge_none(self):
        """assemble_editorial handles single verified approach."""
        approach1 = _approach(role="brute_force")
        outcome1 = _outcome(0, approach1)

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
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert len(editorial.approaches) == 1
        assert editorial.approaches[0].bridge_from_previous is None

    def test_assemble_editorial_model_dump_ordering(self):
        """EditorialApproach.model_dump() keys appear in fixed order."""
        approach1 = _approach(role="brute_force")
        outcome1 = _outcome(0, approach1)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Approach",
                    bridge_from_previous=None,
                    intuition="Intuition text",
                    algorithm="Algorithm text",
                    complexity_time="O(n)",
                    complexity_space="O(1)",
                    complexity_justification="Justification text",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)
        dumped = editorial.approaches[0].model_dump()

        # Check order: intuition, algorithm, code_python, code_go, complexity_time, complexity_space, complexity_justification
        keys = list(dumped.keys())
        intuition_idx = keys.index("intuition")
        algorithm_idx = keys.index("algorithm")
        code_python_idx = keys.index("code_python")
        code_go_idx = keys.index("code_go")
        complexity_time_idx = keys.index("complexity_time")
        complexity_space_idx = keys.index("complexity_space")
        complexity_justification_idx = keys.index("complexity_justification")

        assert (
            intuition_idx
            < algorithm_idx
            < code_python_idx
            < code_go_idx
            < complexity_time_idx
            < complexity_space_idx
            < complexity_justification_idx
        )

    def test_assemble_editorial_empty_notes_survives(self):
        """EditorialApproach with empty notes list serializes correctly."""
        approach1 = _approach(role="brute_force")
        outcome1 = _outcome(0, approach1)

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
                    complexity_justification="Justification",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )
        analysis = ProblemAnalysis(
            intent="Test",
            constraints=[],
            input_shape="list[int], int",
            output_shape="list[int]",
            difficulty="easy",
            needs_clarification=False,
            clarification_question=None,
        )
        outcomes = {0: outcome1}

        editorial = assemble_editorial(draft, analysis, outcomes)

        assert editorial.approaches[0].notes == []


class TestEditorialWriterNode:
    """Tests for the editorial_writer_node function."""

    async def test_editorial_writer_node_calls_parse_without_code(self, monkeypatch):
        """editorial_writer_node does not include code in the parse messages."""
        approach1 = _approach(name="Brute force pairs", role="brute_force")
        approach2 = _approach(name="Hash map lookup", role="optimized")
        outcome1 = _outcome(0, approach1)
        outcome2 = _outcome(1, approach2)

        draft = EditorialDraft(
            problem_restatement="Problem",
            approaches=[
                ApproachProse(
                    approach_id=0,
                    title="Brute force pairs",
                    bridge_from_previous=None,
                    intuition="Проверяем все пары",
                    algorithm="Двойной цикл",
                    complexity_time="O(n^2)",
                    complexity_space="O(1)",
                    complexity_justification="Вложенные циклы",
                    notes=[],
                ),
                ApproachProse(
                    approach_id=1,
                    title="Hash map lookup",
                    bridge_from_previous="Использует хеш-таблицу",
                    intuition="Отслеживаем дополнения",
                    algorithm="Один проход",
                    complexity_time="O(n)",
                    complexity_space="O(n)",
                    complexity_justification="Хеш-таблица",
                    notes=[],
                ),
            ],
            edge_cases=[],
            unverified=[],
        )

        monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(draft))

        # Mock call_structured to capture messages
        captured_messages = []

        async def mock_call_structured(client, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            response = await _fake_client(draft).chat.completions.parse()
            return response

        monkeypatch.setattr(
            "algorunner.agents.editorial_writer.node.call_structured",
            mock_call_structured,
        )

        state = {
            "problem_text": "Two sum problem",
            "language": "en",
            "analysis": _analysis(intent="Find two numbers"),
            "assumption_stated": None,
            "approach_outcomes": {0: outcome1, 1: outcome2},
        }

        result = await editorial_writer_node(state)

        # Check that the result has editorial
        assert "editorial" in result
        assert result["editorial"].approaches[0].role == "brute_force"
        assert result["editorial"].approaches[1].role == "optimized"

        # Check that code_python and code_go don't appear in messages
        message_text = " ".join(str(m) for m in captured_messages)
        assert outcome1.final_solution.code_python not in message_text
        assert outcome1.final_solution.code_go not in message_text
        assert outcome2.final_solution.code_python not in message_text
        assert outcome2.final_solution.code_go not in message_text

        # Check that roles and rationales are in messages
        assert "brute_force" in message_text or "brute force" in message_text
        assert "optimized" in message_text
        assert "Rationale" in message_text

    async def test_editorial_writer_node_raises_on_refusal(self, monkeypatch):
        """editorial_writer_node raises ValueError on refusal."""
        approach1 = _approach(role="brute_force")
        outcome1 = _outcome(0, approach1)

        monkeypatch.setattr(
            client_factory_module, "get_client", lambda: _fake_client(None, refusal="I can't do this")
        )

        state = {
            "problem_text": "Problem",
            "language": "en",
            "analysis": _analysis(),
            "assumption_stated": None,
            "approach_outcomes": {0: outcome1},
        }

        with pytest.raises(ValueError, match="Editorial Writer refused"):
            await editorial_writer_node(state)

    async def test_editorial_writer_node_raises_when_no_verified(self, monkeypatch):
        """editorial_writer_node raises when no approaches are verified."""
        approach1 = _approach(role="brute_force")
        outcome1 = ApproachOutcome(
            approach_idx=0,
            approach=approach1,
            status="errored",
            iterations=1,
            final_solution=None,
            final_review=None,
            error="Test error",
        )

        monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(None))

        state = {
            "problem_text": "Problem",
            "language": "en",
            "analysis": _analysis(),
            "assumption_stated": None,
            "approach_outcomes": {0: outcome1},
        }

        with pytest.raises(ValueError, match="no verified"):
            await editorial_writer_node(state)
