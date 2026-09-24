import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.agents.test_generator.node as test_generator_node_module
import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.code_generator.node import CodeGenOutput, code_generator_node
from algorunner.agents.code_generator.prompts import build_code_messages
from algorunner.agents.test_generator.prompts import build_test_messages
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.solution import Approach, EntryParam, EntryPoint, Solution
from algorunner.schemas.typespec import MAX_CASES, TYPE_VOCABULARY_DOC

# `test_generator_node_module` is imported (rather than importing
# `test_generator_node`/`TestCase` by name) because both names match pytest's
# default `test_*`/`Test*` collection patterns; module-qualified access
# sidesteps the collision without renaming production code.

PY_CODE = "def two_sum(nums, target):\n    return []\n"
GO_CODE = "package main\n\nfunc twoSum(nums []int, target int) []int {\n\treturn nil\n}\n"
SECRET_IMPL_MARKER = "def two_sum_SECRET_IMPL"


def _entry_point(**over) -> EntryPoint:
    fields = dict(
        python_name="two_sum",
        go_name="twoSum",
        params=[EntryParam(name="nums", type="list[int]"), EntryParam(name="target", type="int")],
        return_type="list[int]",
        unordered_result=True,
    )
    fields.update(over)
    return EntryPoint(**fields)


def _analysis() -> ProblemAnalysis:
    return ProblemAnalysis(
        constraints=["2 <= len(nums) <= 10^4"],
        input_shape="list[int] nums, int target",
        output_shape="list[int] of two indices",
        intent="Find two indices whose values add up to target",
        difficulty="easy",
        needs_clarification=False,
        clarification_question=None,
    )


def _base_state(**overrides) -> dict:
    state = {
        "task_id": "test-task",
        "problem_text": "Given nums and target, return indices of two numbers adding up to target.",
        "language": "en",
        "examples": [],
        "analysis": _analysis(),
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
            name="Hash map lookup",
            technique="hash map",
            summary="One pass.",
            role="optimized",
            rationale="Single pass solution.",
        ),
        "algorithm": "Iterate once, tracking complements in a hash map.",
        "complexity_time": "O(n), one pass with O(1) hash map lookups.",
        "complexity_space": "O(n), the hash map holds up to n entries.",
    }
    fields.update(overrides)
    return fields


def _solution(**over) -> Solution:
    fields = dict(
        approach=Approach(
            name="Hash map lookup",
            technique="hash map",
            summary="One pass.",
            role="optimized",
            rationale="Single pass solution.",
        ),
        algorithm="Iterate once, tracking complements in a hash map.",
        entry_point=_entry_point(),
        code_python=PY_CODE + f"\n# {SECRET_IMPL_MARKER}\n",
        code_go=GO_CODE,
        tests=[],
        complexity_time="O(n)",
        complexity_space="O(n)",
    )
    fields.update(over)
    return Solution(**fields)


# ------------------------------------------------------------ code generator


def _code_output(**over) -> CodeGenOutput:
    fields = dict(entry_point=_entry_point(), code_python=PY_CODE, code_go=GO_CODE)
    fields.update(over)
    return CodeGenOutput(**fields)


async def test_code_generator_node_produces_solution_with_entry_point_and_no_tests(monkeypatch):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_code_output())
    )
    update = await code_generator_node(_base_state(solver_output=_solver_output()))
    solution = update["solution"]
    assert solution.entry_point.python_name == "two_sum"
    assert solution.entry_point.go_name == "twoSum"
    assert solution.tests == []


@pytest.mark.parametrize(
    "over,fragment",
    [
        ({"code_python": "def other(nums, target):\n    return []\n"}, "two_sum"),
        ({"code_python": "class S:\n    def two_sum(self, n, t):\n        return []\n"}, "two_sum"),
        ({"code_go": "package main\n\nfunc other() {}\n"}, "twoSum"),
        ({"code_go": GO_CODE + "\nfunc main() {}\n"}, "main"),
        ({"code_go": GO_CODE.replace("package main\n", "package solution\n")}, "package main"),
    ],
)
async def test_code_generator_node_rejects_bad_code(monkeypatch, over, fragment):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_code_output(**over))
    )
    with pytest.raises(ValueError, match=fragment):
        await code_generator_node(_base_state(solver_output=_solver_output()))


def test_build_code_messages_carries_problem_analysis_and_vocabulary():
    state = _base_state(solver_output=_solver_output())
    text = "\n".join(m["content"] for m in build_code_messages(state))
    assert state["problem_text"] in text
    assert "list[int] nums, int target" in text
    assert "list[int] of two indices" in text
    assert TYPE_VOCABULARY_DOC in text


# ------------------------------------------------------------ test generator


def _tc(label, args, expected):
    return test_generator_node_module.TestCase(
        label=label, args_json=json.dumps(args), expected_json=json.dumps(expected)
    )


def _generated(count: int, normalized=None):
    return test_generator_node_module.GeneratedTests(
        tests=[_tc(f"case {i}", [[i, i + 1], 2 * i + 1], [0, 1]) for i in range(count)],
        normalized_examples=normalized or [],
    )


PROVIDED = [
    {"input": "nums=[2,7,11,15], target=9", "output": "[0,1]"},
    {"input": "nums = [3,2,4], target = 6", "output": "[1,2]"},
]


async def test_test_generator_zero_provided_examples(monkeypatch):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(10))
    )
    update = await test_generator_node_module.test_generator_node(
        _base_state(examples=[], solution=_solution())
    )
    tests = update["solution"].tests
    assert len(tests) == 10
    assert all(t.origin == "generated" for t in tests)


async def test_test_generator_provided_first_in_order_without_normalization(monkeypatch):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(10))
    )
    update = await test_generator_node_module.test_generator_node(
        _base_state(examples=PROVIDED, solution=_solution())
    )
    tests = update["solution"].tests
    assert len(tests) == 12
    assert [t.origin for t in tests[:2]] == ["provided", "provided"]
    assert tests[0].args == [[2, 7, 11, 15], 9] and tests[0].expected == [0, 1]
    assert tests[1].args == [[3, 2, 4], 6]
    assert all(t.origin == "generated" for t in tests[2:])


async def test_test_generator_normalizes_unparseable_example_at_original_position(monkeypatch):
    examples = [
        PROVIDED[0],
        {"input": "numbers are 3, 2, 4 and the target is 6", "output": "the last two"},
        PROVIDED[1],
    ]
    normalized = [
        test_generator_node_module.NormalizedExample(
            example_index=1, args_json="[[3,2,4], 6]", expected_json="[1,2]"
        )
    ]
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(2, normalized))
    )
    update = await test_generator_node_module.test_generator_node(
        _base_state(examples=examples, solution=_solution())
    )
    tests = update["solution"].tests
    assert [t.origin for t in tests] == ["provided"] * 3 + ["generated"] * 2
    assert tests[1].args == [[3, 2, 4], 6]
    assert tests[2].args == [[3, 2, 4], 6] and tests[2].label != tests[1].label


@pytest.mark.parametrize(
    "normalized_indices",
    [[], [0, 0], [5], [0, 1]],
)
async def test_test_generator_rejects_bad_normalization_coverage(monkeypatch, normalized_indices):
    examples = [{"input": "some prose", "output": "more prose"}]
    normalized = [
        test_generator_node_module.NormalizedExample(
            example_index=i, args_json="[[2,7], 9]", expected_json="[0,1]"
        )
        for i in normalized_indices
    ]
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(10, normalized))
    )
    with pytest.raises(ValueError):
        await test_generator_node_module.test_generator_node(
            _base_state(examples=examples, solution=_solution())
        )


async def test_test_generator_rejects_disagreeing_normalization(monkeypatch):
    examples = [{"input": "some prose", "output": "[0,1]"}]
    normalized = [
        test_generator_node_module.NormalizedExample(
            example_index=0, args_json="[[2,7], 9]", expected_json="[1,1]"
        )
    ]
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(10, normalized))
    )
    with pytest.raises(ValueError):
        await test_generator_node_module.test_generator_node(
            _base_state(examples=examples, solution=_solution())
        )


@pytest.mark.parametrize(
    "bad",
    [
        test_generator_node_module.TestCase(label="bad json", args_json="[[1", expected_json="[0]"),
        test_generator_node_module.TestCase(label="bad arity", args_json="[[1]]", expected_json="[0]"),
        test_generator_node_module.TestCase(
            label="bad type", args_json='[["x"], 1]', expected_json="[0]"
        ),
    ],
)
async def test_test_generator_rejects_invalid_generated_case_naming_label(monkeypatch, bad):
    generated = _generated(10)
    generated.tests.append(bad)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(generated))
    with pytest.raises(ValueError, match=bad.label):
        await test_generator_node_module.test_generator_node(
            _base_state(examples=[], solution=_solution())
        )


async def test_test_generator_rejects_over_max_cases(monkeypatch):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(MAX_CASES + 1))
    )
    with pytest.raises(ValueError):
        await test_generator_node_module.test_generator_node(
            _base_state(examples=[], solution=_solution())
        )


async def test_test_generator_raises_on_shortfall(monkeypatch):
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(5))
    )
    with pytest.raises(ValueError, match="below the required minimum"):
        await test_generator_node_module.test_generator_node(
            _base_state(examples=PROVIDED[:1], solution=_solution())
        )


async def test_test_generator_no_floor_with_three_examples(monkeypatch):
    examples = PROVIDED + [{"input": "nums=[3,3], target=6", "output": "[0,1]"}]
    monkeypatch.setattr(
        client_factory_module, "get_client", lambda: _fake_client(_generated(1))
    )
    update = await test_generator_node_module.test_generator_node(
        _base_state(examples=examples, solution=_solution())
    )
    assert len(update["solution"].tests) == 4


def test_build_test_messages_excludes_implementation_includes_signature():
    state = _base_state(examples=PROVIDED, solution=_solution())
    text = "\n".join(m["content"] for m in build_test_messages(state))
    assert state["problem_text"] in text
    assert "2 <= len(nums) <= 10^4" in text
    assert "list[int] of two indices" in text
    assert "two_sum" in text and "list[int]" in text
    assert SECRET_IMPL_MARKER not in text
    assert "return []" not in text
    assert TYPE_VOCABULARY_DOC in text


def test_build_test_messages_lists_pending_examples():
    state = _base_state(solution=_solution())
    pending = [(3, {"input": "PENDING-INPUT-TEXT", "output": "PENDING-OUTPUT", "explanation": None})]
    text = "\n".join(m["content"] for m in build_test_messages(state, pending))
    assert "PENDING-INPUT-TEXT" in text and "3" in text
