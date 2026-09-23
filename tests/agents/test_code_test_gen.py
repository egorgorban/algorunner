from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.code_generator.node import CodeGenOutput, code_generator_node
from algorunner.agents.test_generator.node import (
    GeneratedTests,
    TestCase,
    test_generator_node,
)
from algorunner.schemas.solution import Approach


def _base_state(**overrides) -> dict:
    state = {
        "task_id": "test-task",
        "problem_text": "two sum",
        "language": "en",
        "examples": [],
        "analysis": None,
        "clarification_rounds": 0,
        "assumption_stated": None,
        "approaches": [],
        "solution": None,
        "solver_output": None,
        "python_execution": None,
        "go_execution": None,
        "review": None,
        "review_history": [],
        "iterations": 0,
        "max_iterations": 5,
        "result": None,
        "error": None,
    }
    state.update(overrides)
    return state


def _fake_client(parsed, refusal=None):
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=refusal))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(parse=AsyncMock(return_value=completion))
        )
    )


def _solver_output(**overrides) -> dict:
    fields = {
        "approach": Approach(
            name="Hash map lookup", technique="hash map", summary="One pass."
        ),
        "algorithm": "Iterate once, tracking complements in a hash map.",
        "complexity_time": "O(n), one pass with O(1) hash map lookups.",
        "complexity_space": "O(n), the hash map holds up to n entries.",
    }
    fields.update(overrides)
    return fields


def _generated_tests(count: int) -> GeneratedTests:
    return GeneratedTests(
        tests=[TestCase(input=f"in-{i}", output=f"out-{i}") for i in range(count)]
    )


async def test_code_generator_node_produces_solution_with_empty_tests(monkeypatch):
    output = CodeGenOutput(
        code_python="def two_sum(nums, target):\n    return []\n",
        code_go="package main\n\nfunc twoSum(nums []int, target int) []int {\n\treturn nil\n}\n",
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(output))
    state = _base_state(solver_output=_solver_output())

    update = await code_generator_node(state)

    solution = update["solution"]
    assert solution.code_python
    assert solution.code_go
    assert solution.tests == []


async def test_test_generator_node_zero_provided_examples(monkeypatch):
    generated = _generated_tests(10)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(generated))
    solution = SimpleNamespace(
        code_python="def two_sum(nums, target):\n    return []\n",
        model_copy=lambda update: SimpleNamespace(tests=update["tests"]),
    )
    state = _base_state(examples=[], solution=solution)

    update = await test_generator_node(state)

    result_tests = update["solution"].tests
    assert len(result_tests) == 10


async def test_test_generator_node_preserves_provided_examples(monkeypatch):
    generated = _generated_tests(10)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(generated))
    provided_examples = [
        {"input": "nums=[2,7,11,15], target=9", "output": "[0,1]"},
        {"input": "nums=[3,2,4], target=6", "output": "[1,2]"},
    ]
    solution = SimpleNamespace(
        code_python="def two_sum(nums, target):\n    return []\n",
        model_copy=lambda update: SimpleNamespace(tests=update["tests"]),
    )
    state = _base_state(examples=provided_examples, solution=solution)

    update = await test_generator_node(state)

    result_tests = update["solution"].tests
    assert len(result_tests) == 12
    for example in provided_examples:
        assert {"input": example["input"], "output": example["output"]} in result_tests


async def test_test_generator_node_raises_on_shortfall(monkeypatch):
    generated = _generated_tests(5)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(generated))
    provided_examples = [{"input": "nums=[2,7,11,15], target=9", "output": "[0,1]"}]
    solution = SimpleNamespace(
        code_python="def two_sum(nums, target):\n    return []\n",
        model_copy=lambda update: SimpleNamespace(tests=update["tests"]),
    )
    state = _base_state(examples=provided_examples, solution=solution)

    with pytest.raises(ValueError, match="below the required minimum"):
        await test_generator_node(state)
