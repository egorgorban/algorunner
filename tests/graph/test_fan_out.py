"""Tests for fan-out/join orchestration and branch hardening (Phase 3, Plan 03-03, Task 2).

Covers: branch isolation, join-once, zero-verified routing, per-branch budget,
failure precedence, idempotent re-invoke, and single-approach runs.

Pure-router tests check the join logic directly.
Whole-graph tests run on real Postgres checkpoints with mocked executors.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.errors import GraphRecursionError

import algorunner.llm.client_factory as client_factory_module
from algorunner.graph.approach import decide_after_join
from algorunner.graph.build import build_pipeline_graph
from algorunner.schemas.outcome import ApproachOutcome, ApproachStatus
from algorunner.schemas.review import Issue, ReviewResult
from algorunner.schemas.solution import Approach, ApproachList
from tests.graph.test_build import _initial_state


# ============================================================================
# Pure-router tests (decide_after_join logic)
# ============================================================================


def _approach(name: str, idx: int = 0, technique: str = "test", role: str = "optimized"):
    """Build a test Approach with required fields."""
    return Approach(
        name=name,
        technique=technique,
        summary="Test approach.",
        role=role,
        rationale="Test rationale.",
    )


def _outcome(approach_idx: int, status: ApproachStatus, error: str | None = None):
    """Build a test ApproachOutcome."""
    return ApproachOutcome(
        approach_idx=approach_idx,
        approach=_approach(f"App {approach_idx}"),
        status=status,
        iterations=1,
        final_solution=None,
        final_review=ReviewResult(passed=True, issues=[], required_changes=[], complexity_reasoning="ok"),
        error=error,
    )


def _state(approach_outcomes: dict[int, ApproachOutcome]) -> dict:
    """Build test state for router."""
    return {"approach_outcomes": approach_outcomes}


def test_router_one_verified_one_errored_routes_success():
    """One branch verified, one errored -> finalize_success (D-05, D-06)."""
    outcomes = {
        0: _outcome(0, "errored", "Code generator refused"),
        1: _outcome(1, "verified"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_success"


def test_router_both_verified_routes_success():
    """Both verified -> finalize_success."""
    outcomes = {
        0: _outcome(0, "verified"),
        1: _outcome(1, "verified"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_success"


def test_router_one_verified_rest_any_status_routes_success():
    """One verified, others exhausted/timed_out/errored -> finalize_success."""
    outcomes = {
        0: _outcome(0, "exhausted"),
        1: _outcome(1, "verified"),
        2: _outcome(2, "timed_out"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_success"


def test_router_all_exhausted_routes_failed():
    """All approaches exhausted -> finalize_failed."""
    outcomes = {
        0: _outcome(0, "exhausted"),
        1: _outcome(1, "exhausted"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_failed"


def test_router_mix_exhausted_and_timed_out_routes_failed():
    """Only exhausted and timed_out (no verified) -> finalize_failed."""
    outcomes = {
        0: _outcome(0, "exhausted"),
        1: _outcome(1, "timed_out"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_failed"


def test_router_all_errored_routes_failed():
    """All approaches errored (none verified) -> finalize_failed."""
    outcomes = {
        0: _outcome(0, "errored", "Gen failed"),
        1: _outcome(1, "errored", "Exec failed"),
    }
    assert decide_after_join(_state(outcomes)) == "finalize_failed"


def test_router_empty_outcomes_routes_failed():
    """No approaches ran -> finalize_failed."""
    outcomes = {}
    assert decide_after_join(_state(outcomes)) == "finalize_failed"


# ============================================================================
# Whole-graph integration tests (dispatcher mocking, real checkpoints)
# ============================================================================


def _review(passed: bool, *issues: Issue):
    """Build a ReviewResult for mocking."""
    return ReviewResult(
        passed=passed,
        issues=list(issues),
        required_changes=[] if passed else ["fix"],
        complexity_reasoning="reasoning",
    )


def _issue(category: str, severity: str = "critical"):
    """Build an Issue for mocking."""
    return Issue(category=category, severity=severity, description=f"{category} problem")


async def test_single_verified_approach_two_approach_run_completes_successfully(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    """With two approaches, one verified and one errored: task completes with result set
    (D-05, D-06; Pitfall 2 - sibling success not discarded)."""
    fake_client = mock_pipeline_openai
    parse = fake_client.chat.completions.parse

    # Drain first five completions (analyzer, strategist, two solvers, one code_gen)
    # to fill by_type, then replace with custom dispatch
    by_type: dict[str, object] = {}
    for _ in range(5):
        completion = await parse()
        by_type[type(completion.choices[0].message.parsed).__name__] = completion

    # Dispatch: first approach (index 0) code generator refuses; second (index 1) passes
    approaches_returned = 0
    first_code_gen_called = False

    async def dispatch(**kwargs):
        nonlocal approaches_returned, first_code_gen_called
        name = kwargs["response_format"].__name__
        if name == "ApproachList":
            approaches_returned += 1
            return by_type["ApproachList"]
        if name == "SolverOutput":
            return by_type["SolverOutput"]
        if name == "CodeGenOutput":
            if not first_code_gen_called:
                first_code_gen_called = True
                # First code_gen (approach 0) refuses
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(parsed=None, refusal="Too hard"))]
                )
            # Second code_gen (approach 1) succeeds
            return by_type["CodeGenOutput"]
        if name == "GeneratedTests":
            return by_type["GeneratedTests"]
        if name == "ReviewResult":
            return by_type["ReviewResult"]
        raise ValueError(f"Unexpected response_format: {name}")

    fake_client.chat.completions.parse = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    graph = build_pipeline_graph(checkpointer)
    thread_id = str(uuid4())

    try:
        result_state = await graph.ainvoke(
            _initial_state(thread_id, "two sum"),
            config={"configurable": {"thread_id": thread_id}},
            durability="sync",
        )
    except GraphRecursionError as e:
        raise AssertionError(f"Hit recursion limit: {e}") from e

    # First approach errored, second verified -> task completes with result
    assert result_state["error"] is None
    assert result_state["result"] is not None
    assert "approaches" in result_state["result"]
    assert len(result_state["result"]["approaches"]) == 2
    assert result_state["result"]["approaches"][0]["status"] == "errored"
    assert result_state["result"]["approaches"][1]["status"] == "verified"


async def test_two_approaches_always_failing_review_exhausts_per_branch_budget(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    """With two approaches and max_iterations=2, reviewer runs 4 times (2 per branch).
    Both outcomes have iterations=2 (D-09; per-branch budget)."""
    fake_client = mock_pipeline_openai
    parse = fake_client.chat.completions.parse

    # Drain first five completions
    by_type: dict[str, object] = {}
    for _ in range(5):
        completion = await parse()
        by_type[type(completion.choices[0].message.parsed).__name__] = completion

    failing = _review(False, _issue("algorithm_soundness"))
    failing_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=failing, refusal=None))]
    )
    calls: list[str] = []

    async def dispatch(**kwargs):
        name = kwargs["response_format"].__name__
        calls.append(name)
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
    except GraphRecursionError as e:
        raise AssertionError(f"Hit recursion limit: {e}") from e

    # Check error and outcome states
    assert result_state["error"]["code"] == "CORRECTION_LOOP_EXHAUSTED"
    assert result_state["result"] is None
    assert "approaches" in result_state
    approaches = result_state["approaches"]
    assert len(approaches) == 2
    # Each approach ran its own max_iterations (2)
    assert approaches[0]["status"] == "exhausted"
    assert approaches[1]["status"] == "exhausted"
    # Reviewer should have been called for each approach x max_iterations = 4 times
    assert calls.count("ReviewResult") == 4


async def test_idempotent_re_invoke_second_run_with_one_approach_has_one_outcome(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    """Re-invoke graph on same thread_id with fresh state and 1 approach
    (vs the canned 2): second run leaves exactly 1 outcome (Pitfall 3).
    Tests the Overwrite({}) reset in solution_strategist_node."""
    fake_client = mock_pipeline_openai
    parse = fake_client.chat.completions.parse

    # Drain the fixture's completions for a first run with 2 approaches
    by_type: dict[str, object] = {}
    for _ in range(5):
        completion = await parse()
        by_type[type(completion.choices[0].message.parsed).__name__] = completion

    # Extract the ApproachList (2 approaches) for the first run
    first_run_approaches = by_type["ApproachList"].choices[0].message.parsed

    # Prepare custom ApproachList with only 1 approach for second run
    one_approach_list = ApproachList(
        approaches=[first_run_approaches.approaches[1]]  # Just the hash map
    )
    one_approach_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=one_approach_list, refusal=None))]
    )

    dispatch_call_count = 0

    async def dispatch(**kwargs):
        nonlocal dispatch_call_count
        name = kwargs["response_format"].__name__
        dispatch_call_count += 1

        # First call to each response type goes to by_type; second call returns the same
        if name == "ApproachList":
            if dispatch_call_count == 1:
                return by_type["ApproachList"]  # First run: 2 approaches
            else:
                return one_approach_completion  # Second run: 1 approach

        if name in by_type:
            return by_type[name]
        raise ValueError(f"Unexpected response_format: {name}")

    fake_client.chat.completions.parse = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    graph = build_pipeline_graph(checkpointer)
    thread_id = str(uuid4())

    # First run: 2 approaches
    try:
        result_state1 = await graph.ainvoke(
            _initial_state(thread_id, "two sum"),
            config={"configurable": {"thread_id": thread_id}},
            durability="sync",
        )
    except GraphRecursionError as e:
        raise AssertionError(f"First run hit recursion limit: {e}") from e

    assert len(result_state1["approaches"]) == 2

    # Second run: same thread_id, fresh initial state, but strategist returns 1 approach
    # The Overwrite({}) in solution_strategist_node should clear stale outcomes
    try:
        result_state2 = await graph.ainvoke(
            _initial_state(thread_id, "two sum"),
            config={"configurable": {"thread_id": thread_id}},
            durability="sync",
        )
    except GraphRecursionError as e:
        raise AssertionError(f"Second run hit recursion limit: {e}") from e

    # Second run should have exactly 1 approach, not 2 (no stale outcome from run 1)
    assert len(result_state2["approaches"]) == 1
    assert result_state2["approaches"][0]["name"] == "Hash map lookup"


async def test_single_approach_yields_one_branch_with_approach_id_zero(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    """With one approach, exactly one branch runs (one SolverOutput call).
    result.approaches has length 1 with approach_id=0 (D-02; STRAT-02 empty edge)."""
    fake_client = mock_pipeline_openai
    parse = fake_client.chat.completions.parse

    # Drain initial completions
    by_type: dict[str, object] = {}
    for _ in range(5):
        completion = await parse()
        by_type[type(completion.choices[0].message.parsed).__name__] = completion

    # Replace ApproachList with single approach
    single_approach_list = ApproachList(
        approaches=[
            Approach(
                name="Hash map",
                technique="hash map",
                summary="One pass.",
                role="optimized",
                rationale="Single pass.",
            )
        ]
    )
    single_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=single_approach_list, refusal=None))]
    )

    calls: list[str] = []

    async def dispatch(**kwargs):
        name = kwargs["response_format"].__name__
        calls.append(name)
        if name == "ApproachList":
            return single_completion
        return by_type[name]

    fake_client.chat.completions.parse = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    graph = build_pipeline_graph(checkpointer)
    thread_id = str(uuid4())

    try:
        result_state = await graph.ainvoke(
            _initial_state(thread_id, "two sum"),
            config={"configurable": {"thread_id": thread_id}},
            durability="sync",
        )
    except GraphRecursionError as e:
        raise AssertionError(f"Hit recursion limit: {e}") from e

    # Exactly one branch ran
    assert calls.count("SolverOutput") == 1
    # result.approaches has one entry with approach_id=0
    assert len(result_state["result"]["approaches"]) == 1
    assert result_state["result"]["approaches"][0]["approach_id"] == 0
