from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.reviewer.node import reviewer_node
from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.review import Issue, ReviewResult
from algorunner.schemas.solution import (
    Approach,
    EntryParam,
    EntryPoint,
    Solution,
    StructuredCase,
)


def _exec(passed: bool, stderr: str = "") -> ExecutionResult:
    return ExecutionResult(
        passed=passed, stdout="", stderr=stderr, exit_code=0 if passed else 1, duration_ms=5
    )


def _solution() -> Solution:
    return Solution(
        approach=Approach(name="Hash map", technique="hash map", summary="One pass."),
        algorithm="Single pass with a complement map.",
        entry_point=EntryPoint(
            python_name="two_sum",
            go_name="twoSum",
            params=[EntryParam(name="nums", type="list[int]"), EntryParam(name="target", type="int")],
            return_type="list[int]",
            unordered_result=True,
        ),
        code_python="def two_sum(nums, target):\n    return []\n",
        code_go="package main\n\nfunc twoSum(nums []int, target int) []int {\n\treturn nil\n}\n",
        tests=[
            StructuredCase(
                label="classic", origin="generated", args=[[2, 7], 9], expected=[0, 1]
            )
        ],
        complexity_time="O(n)",
        complexity_space="O(n)",
    )


def _state(py: ExecutionResult | None, go: ExecutionResult | None, **over) -> dict:
    state = {
        "task_id": "t",
        "problem_text": "two sum",
        "language": "en",
        "examples": [],
        "analysis": None,
        "clarification_rounds": 0,
        "assumption_stated": None,
        "approaches": [],
        "solution": _solution(),
        "solver_output": None,
        "python_execution": py,
        "go_execution": go,
        "review": None,
        "review_history": [],
        "iterations": 0,
        "max_iterations": 5,
        "result": None,
        "error": None,
    }
    state.update(over)
    return state


def _client(parsed: ReviewResult) -> SimpleNamespace:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=completion)))
    )


def _forbid_llm(monkeypatch):
    def boom():
        raise AssertionError("LLM client must not be used when execution failed")

    monkeypatch.setattr(client_factory_module, "get_client", boom)


@pytest.mark.parametrize(
    "py,go",
    [
        (_exec(False, "AssertionError boom"), _exec(True)),
        (_exec(True), _exec(False, "compile error")),
        (None, _exec(True)),
        (_exec(True), None),
    ],
)
async def test_execution_failure_short_circuits_without_llm(monkeypatch, py, go):
    _forbid_llm(monkeypatch)
    update = await reviewer_node(_state(py, go))
    review = update["review"]
    assert review.passed is False
    assert review.issues[0].category == "correctness"
    assert review.issues[0].severity == "critical"
    assert review.required_changes
    assert update["iterations"] == 1
    assert update["review_history"] == [review]


async def test_passing_executions_use_llm_result_and_grow_history(monkeypatch):
    llm_result = ReviewResult(
        passed=True,
        issues=[],
        required_changes=[],
        complexity_reasoning="One loop over n items with O(1) dict operations gives O(n).",
    )
    client = _client(llm_result)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: client)
    prior = ReviewResult(
        passed=False,
        issues=[Issue(category="correctness", severity="critical", description="x")],
        required_changes=["y"],
        complexity_reasoning="n/a",
    )
    update = await reviewer_node(
        _state(_exec(True), _exec(True), review_history=[prior], iterations=1)
    )
    assert update["review"] == llm_result
    assert update["review_history"] == [prior, llm_result]
    assert update["iterations"] == 2
    client.chat.completions.parse.assert_awaited_once()


async def test_minor_issue_does_not_block_pass(monkeypatch):
    llm_result = ReviewResult(
        passed=True,
        issues=[Issue(category="code_quality", severity="minor", description="rename var")],
        required_changes=[],
        complexity_reasoning="Single pass, O(n).",
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _client(llm_result))
    update = await reviewer_node(_state(_exec(True), _exec(True)))
    assert update["review"].passed is True
    assert update["review"].issues[0].severity == "minor"


async def test_llm_refusal_raises(monkeypatch):
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=None, refusal="no"))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=AsyncMock(return_value=completion)))
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: client)
    with pytest.raises(ValueError, match="Reviewer"):
        await reviewer_node(_state(_exec(True), _exec(True)))
