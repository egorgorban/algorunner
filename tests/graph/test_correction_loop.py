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
    fake_client = mock_pipeline_openai
    parse = fake_client.chat.completions.parse
    # Drain the fixture's five first-pass completions (analyzer, strategist,
    # solver, code_generator, test_generator); the sixth (passing review) is
    # unused because the dispatcher below replaces the whole mock.
    by_type: dict[str, object] = {}
    for _ in range(5):
        completion = await parse()
        by_type[type(completion.choices[0].message.parsed).__name__] = completion

    failing = ReviewResult(
        passed=False,
        issues=[_issue("algorithm_soundness")],
        required_changes=["rethink the algorithm"],
        complexity_reasoning="Not convinced the pass is single.",
    )
    failing_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=failing, refusal=None))]
    )
    calls: list[str] = []
    solver_prompts: list[list[dict]] = []

    async def dispatch(**kwargs):
        name = kwargs["response_format"].__name__
        calls.append(name)
        if name == "SolverOutput":
            solver_prompts.append(kwargs["messages"])
        if name == "ReviewResult":
            return failing_completion
        return by_type[name]

    fake_client.chat.completions.parse = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

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

    assert result_state["error"]["code"] == "CORRECTION_LOOP_EXHAUSTED"
    assert result_state["result"] is None
    assert result_state["iterations"] == 2
    assert len(result_state["review_history"]) == 2
    assert calls.count("SolverOutput") > 1  # loop really re-entered the solver
    assert calls.count("ReviewResult") == 2
    # full history reached the second solver prompt (D-06, REV-04)
    assert "Attempt 1" in solver_prompts[1][-1]["content"]
    assert "Attempt 1" not in solver_prompts[0][-1]["content"]
