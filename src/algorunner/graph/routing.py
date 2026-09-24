"""Conditional-edge router for the Reviewer -> correction loop (D-05, D-07,
REV-04, REV-05).

Pure Python: zero LLM calls, zero I/O. The category -> node table is costly to
reverse (it is baked into the graph's conditional-edge structure).

Works with both GraphState (parent) and ApproachState (branch) — both have
the same review, iterations, and max_iterations fields.
"""

from algorunner.graph.state import GraphState

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
    analysis = state["analysis"]
    if analysis is not None and analysis.needs_clarification:
        return "clarification_gate"
    return "strategist"


def decide_after_review(state: GraphState) -> str:
    review = state["review"]
    if review is None:
        # No structured verdict is never treated as success.
        return "finalize_failed"
    if review.passed:
        return "finalize_success"
    if state["iterations"] >= state.get("max_iterations", 5):
        return "finalize_failed"
    critical = [i for i in review.issues if i.severity == "critical"]
    targets = {_CATEGORY_TO_NODE.get(i.category, "solver") for i in critical}
    return next((t for t in _TARGET_PRIORITY if t in targets), "solver")
