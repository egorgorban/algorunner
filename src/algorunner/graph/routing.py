"""Conditional-edge routers for the Editorial Writer and correction loop (D-16, D-05, D-07,
REV-04, REV-05).

Pure Python: zero LLM calls, zero I/O. The category -> node table is costly to
reverse (it is baked into the graph's conditional-edge structure).

Works with both GraphState (parent) and ApproachState (branch) — both have
the same review, iterations, and max_iterations fields.
"""

from algorunner.graph.state import ApproachState, GraphState

_CATEGORY_TO_NODE = {
    "algorithm_soundness": "solver",
    "correctness": "solver",
    "edge_case": "solver",
    "complexity": "solver",
    "code_quality": "code_generator",
}

# Fixed precedence among correction targets: a soundness fix (solver) subsumes
# a code-only fix, since the solver's re-run regenerates code and tests too.
_TARGET_PRIORITY = ["solver", "code_generator"]


def decide_after_analysis(state: GraphState) -> str:
    """Route after analysis: clarification_gate if clarification needed, else record_analysis.

    Plan 03-05: changed destination from "strategist" to "record_analysis" to emit
    DESIGNING_SOLUTION status (Pattern 11, D-10).
    """
    analysis = state.get("analysis")
    if analysis is not None and analysis.needs_clarification:
        return "clarification_gate"
    return "record_analysis"


def decide_after_review(state: ApproachState) -> str:
    """Route after review in a per-approach branch (D-05, D-07, REV-04, REV-05).

    The annotation changed from GraphState to ApproachState because this router
    runs only inside the per-approach subgraph (not the parent graph).
    """
    review = state.get("review")
    if review is None:
        # No structured verdict is never treated as success.
        return "finalize_failed"
    if review.passed:
        return "finalize_success"
    if state.get("iterations", 0) >= state.get("max_iterations", 5):
        return "finalize_failed"
    critical = [i for i in review.issues if i.severity == "critical"]
    targets = {_CATEGORY_TO_NODE.get(i.category, "solver") for i in critical}
    return next((t for t in _TARGET_PRIORITY if t in targets), "solver")


def decide_after_writer(state: GraphState) -> str:
    """Route after Editorial Writer: finalize_success if editorial is set and no error,
    else end (fail the task).

    The Writer returns {"editorial": ..., "editorial_warnings": [...]} on success
    (editorial is always present even if warnings exist) or {"error": ...} on
    structural failure. The error dict goes to finalize_failed via the error handling
    in _handle_result_or_pause.
    """
    if state.get("editorial") is not None and state.get("error") is None:
        return "finalize_success"
    return "end"
