"""Reviewer graph node.

P1 prohibition: a real execution failure is never overridden by an LLM's
opinion. If either the Python or the Go execution did not pass (or is
absent), the review is synthesized deterministically and the LLM is never
called. Only when both passed does the LLM evaluate soundness, edge cases,
complexity reasoning and quality.

Every call appends exactly one entry to `review_history` and increments
`iterations` by exactly one (T-02-06-02: this is what bounds the loop).
"""

from algorunner.agents.reviewer.prompts import build_review_messages
from algorunner.graph.state import ApproachState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.review import Issue, ReviewResult


def _execution_failure_review(state: ApproachState, py_ok: bool, go_ok: bool) -> ReviewResult:
    py = state["python_execution"]
    go = state["go_execution"]
    py_err = (py.stderr if py else "")[:500]
    go_err = (go.stderr if go else "")[:500]
    return ReviewResult(
        passed=False,
        issues=[
            Issue(
                category="correctness",
                severity="critical",
                description=(
                    f"Execution failed - python_passed={py_ok}, go_passed={go_ok}. "
                    f"python_stderr={py_err!r} go_stderr={go_err!r}"
                ),
            )
        ],
        required_changes=[
            "Fix the failing implementation(s) so both Python and Go pass all generated/provided tests"
        ],
        complexity_reasoning=(
            "Not assessed - execution failed before a complexity review could be performed"
        ),
    )


async def reviewer_node(state: ApproachState) -> dict:
    py = state["python_execution"]
    go = state["go_execution"]
    py_ok = py is not None and py.passed
    go_ok = go is not None and go.passed

    if not (py_ok and go_ok):
        result = _execution_failure_review(state, py_ok, go_ok)
    else:
        completion = await call_structured(
            client_factory.get_client(),
            model=client_factory.model_for("reviewer"),
            messages=build_review_messages(state),
            response_format=ReviewResult,
        )
        message = completion.choices[0].message
        if message.parsed is None:
            raise ValueError(f"Reviewer refused or failed to parse: {message.refusal}")
        result = message.parsed

    return {
        "review": result,
        "review_history": state["review_history"] + [result],
        "iterations": state["iterations"] + 1,
    }
