from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.errors import GraphRecursionError

import algorunner.llm.client_factory as client_factory_module
from algorunner.graph.build import build_pipeline_graph
from algorunner.graph.routing import decide_after_review
from algorunner.schemas.review import Issue, ReviewResult
from tests.graph.test_build import _initial_state


def _review(passed: bool, *issues: Issue) -> ReviewResult:
    return ReviewResult(
        passed=passed,
        issues=list(issues),
        required_changes=[] if passed else ["fix"],
        complexity_reasoning="reasoning",
    )


def _issue(category: str, severity: str = "critical") -> Issue:
    return Issue(category=category, severity=severity, description=f"{category} problem")


def _state(review: ReviewResult | None, iterations: int, max_iterations: int = 5) -> dict:
    return {"review": review, "iterations": iterations, "max_iterations": max_iterations}


def test_routing_passed_finalizes_success():
    assert decide_after_review(_state(_review(True), 1)) == "finalize_success"


def test_routing_passed_with_minor_issue_is_still_success():
    review = _review(True, _issue("code_quality", "minor"))
    assert decide_after_review(_state(review, 1)) == "finalize_success"


def test_routing_exactly_at_max_iterations_terminates():
    review = _review(False, _issue("algorithm_soundness"))
    assert decide_after_review(_state(review, 5, 5)) == "finalize_failed"


def test_routing_beyond_max_iterations_terminates():
    review = _review(False, _issue("algorithm_soundness"))
    assert decide_after_review(_state(review, 9, 5)) == "finalize_failed"


def test_routing_soundness_issue_routes_to_solver():
    review = _review(False, _issue("algorithm_soundness"))
    assert decide_after_review(_state(review, 4, 5)) == "solver"


def test_routing_code_quality_only_routes_to_code_generator():
    review = _review(False, _issue("code_quality"))
    assert decide_after_review(_state(review, 4, 5)) == "code_generator"


def test_routing_solver_has_priority_over_code_generator():
    review = _review(False, _issue("code_quality"), _issue("algorithm_soundness"))
    assert decide_after_review(_state(review, 1)) == "solver"


def test_routing_missing_review_is_never_success():
    assert decide_after_review(_state(None, 1)) == "finalize_failed"


# ------------------------------------------------- whole-graph integration


async def test_always_failing_review_exhausts_max_iterations_cleanly(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    """Single-approach correction loop: with max_iterations=2 and always-failing review,
    the branch exhausts after 2 iterations; per-approach outcome is 'exhausted', with
    Solver called twice and full history in second Solver prompt (Phase-3 per-branch D-06)."""

    # Wrap the dispatcher to handle the single-approach scenario
    default_dispatch = mock_pipeline_openai.default_dispatch
    calls: list[str] = []
    solver_prompts: list[list[dict]] = []

    failing = ReviewResult(
        passed=False,
        issues=[_issue("algorithm_soundness")],
        required_changes=["rethink the algorithm"],
        complexity_reasoning="Not convinced the pass is single.",
    )
    failing_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=failing, refusal=None))]
    )

    async def custom_dispatch(**kwargs):
        name = kwargs.get("response_format", type(None)).__name__
        calls.append(name)

        # Override ApproachList to return a single approach (hash map)
        if name == "ApproachList":
            single_approach = mock_pipeline_openai.canned["ApproachList"].__class__(
                approaches=[mock_pipeline_openai.canned["ApproachList"].approaches[1]]  # "Hash map lookup"
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=single_approach, refusal=None))]
            )

        # Override ReviewResult to always fail
        if name == "ReviewResult":
            return failing_completion

        # Track Solver prompts for history check
        if name == "SolverOutput":
            solver_prompts.append(kwargs.get("messages", []))

        # Use default dispatch for everything else
        return await default_dispatch(**kwargs)

    mock_pipeline_openai.chat.completions.parse = AsyncMock(side_effect=custom_dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: mock_pipeline_openai)

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    graph = build_pipeline_graph(checkpointer)
    thread_id = str(uuid4())
    state = _initial_state(thread_id, "two sum")
    state["max_iterations"] = 2

    try:
        result_state = await graph.ainvoke(
            state, config={"configurable": {"thread_id": thread_id}}, durability="sync"
        )
    except GraphRecursionError:
        raise AssertionError("correction loop hit the recursion limit") from None

    # Single approach exhausted - phase 3 error format
    assert result_state["error"]["code"] == "CORRECTION_LOOP_EXHAUSTED"
    assert "0 of 1 approaches verified:" in result_state["error"]["message"]
    assert result_state["result"] is None

    # Per-approach outcome verification
    outcomes = result_state.get("approach_outcomes", {})
    assert 0 in outcomes  # single approach at index 0
    outcome = outcomes[0]
    assert outcome.status == "exhausted"
    assert outcome.iterations == 2
    assert outcome.final_review is not None
    assert outcome.final_review.passed is False

    # Solver re-entered the loop
    assert calls.count("SolverOutput") > 1
    assert calls.count("ReviewResult") == 2

    # Full history in second solver prompt (D-06: Attempt 1 label)
    assert len(solver_prompts) >= 2
    assert "Attempt 1" in solver_prompts[1][-1]["content"]
    assert "Attempt 1" not in solver_prompts[0][-1]["content"]
