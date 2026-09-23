from algorunner.graph.routing import decide_after_review
from algorunner.schemas.review import Issue, ReviewResult


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
