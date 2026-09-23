"""Segment-level end-to-end proof (plan 02-09, Task 3).

Calls the REAL code_generator_node, test_generator_node, execute_python_node
and execute_go_node in sequence with real python3 and real `go build`; only
`client_factory.get_client` is mocked. Deliberately does not compile the
LangGraph graph (no Postgres), so it stays valid when later plans add the
Reviewer, correction loop and clarification gate.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import algorunner.agents.test_generator.node as test_generator_node_module
import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.code_generator.node import CodeGenOutput, code_generator_node
from algorunner.graph.build import execute_go_node, execute_python_node
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.solution import Approach, EntryParam, EntryPoint

# Module-qualified access to the test generator avoids pytest collecting
# `test_generator_node` / `TestCase` as tests.


def _completion(parsed):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
    )


def _install_client(monkeypatch, code_output, generated):
    parse = AsyncMock(side_effect=[_completion(code_output), _completion(generated)])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake)
    return parse


def _state(problem_text, examples, analysis) -> dict:
    return {
        "task_id": "e2e",
        "problem_text": problem_text,
        "language": "en",
        "examples": examples,
        "analysis": analysis,
        "clarification_rounds": 0,
        "assumption_stated": None,
        "approaches": [],
        "solution": None,
        "solver_output": {
            "approach": Approach(name="Direct", technique="direct", summary="Direct solution."),
            "algorithm": "Implement the function directly.",
            "complexity_time": "O(n)",
            "complexity_space": "O(n)",
        },
        "python_execution": None,
        "go_execution": None,
        "review": None,
        "review_history": [],
        "iterations": 0,
        "max_iterations": 5,
        "result": None,
        "error": None,
    }


async def _run_segment(state: dict) -> dict:
    for node in (
        code_generator_node,
        test_generator_node_module.test_generator_node,
        execute_python_node,
        execute_go_node,
    ):
        state = {**state, **(await node(state))}
    return state


def _tc(label, args, expected):
    return test_generator_node_module.TestCase(
        label=label, args_json=json.dumps(args), expected_json=json.dumps(expected)
    )


def _analysis(input_shape, output_shape):
    return ProblemAnalysis(
        constraints=["small inputs"],
        input_shape=input_shape,
        output_shape=output_shape,
        intent="solve it",
        difficulty="easy",
        needs_clarification=False,
        clarification_question=None,
    )


TWO_SUM_EP = EntryPoint(
    python_name="two_sum",
    go_name="twoSum",
    params=[EntryParam(name="nums", type="list[int]"), EntryParam(name="target", type="int")],
    return_type="list[int]",
    unordered_result=True,
)
# Both solutions return the pair in the OPPOSITE order to the expected values.
TWO_SUM_PY = (
    "def two_sum(nums, target):\n"
    "    seen = {}\n"
    "    for i, n in enumerate(nums):\n"
    "        if target - n in seen:\n"
    "            return [i, seen[target - n]]\n"
    "        seen[n] = i\n"
    "    return []\n"
)
TWO_SUM_GO = (
    "package main\n\n"
    "func twoSum(nums []int, target int) []int {\n"
    "\tseen := map[int]int{}\n"
    "\tfor i, n := range nums {\n"
    "\t\tif j, ok := seen[target-n]; ok {\n"
    "\t\t\treturn []int{i, j}\n"
    "\t\t}\n"
    "\t\tseen[n] = i\n"
    "\t}\n"
    "\treturn nil\n"
    "}\n"
)
TWO_SUM_GENERATED = [
    ("pair at the start", [[1, 2, 3], 3], [0, 1]),
    ("duplicates", [[3, 3], 6], [0, 1]),
    ("negatives", [[-1, -2, -3, -4, -5], -8], [2, 4]),
    ("zeros", [[0, 4, 3, 0], 0], [0, 3]),
    ("minimal length", [[1, 5], 6], [0, 1]),
    ("pair at the end", [[5, 75, 25], 100], [1, 2]),
    ("mixed signs", [[-3, 4, 3, 90], 0], [0, 2]),
    ("last two", [[1, 2, 3, 4], 7], [2, 3]),
    ("negative in pair", [[10, -2, 8], 6], [1, 2]),
    ("large values", [[1000000000, 2, 1000000000], 2000000000], [0, 2]),
]
TWO_SUM_EXAMPLES = [
    {"input": "nums=[2,7,11,15], target=9", "output": "[0,1]"},
    {"input": "nums = [3,2,4], target = 6", "output": "[1,2]"},
]


def _generated(cases, normalized=None):
    return test_generator_node_module.GeneratedTests(
        tests=[_tc(*c) for c in cases], normalized_examples=normalized or []
    )


def _analysis_two_sum():
    return _analysis("list[int] nums, int target", "list[int] of two indices")


async def test_two_sum_with_leetcode_style_examples_no_normalization(monkeypatch):
    parse = _install_client(
        monkeypatch,
        CodeGenOutput(entry_point=TWO_SUM_EP, code_python=TWO_SUM_PY, code_go=TWO_SUM_GO),
        _generated(TWO_SUM_GENERATED),
    )
    state = await _run_segment(_state("two sum", TWO_SUM_EXAMPLES, _analysis_two_sum()))

    assert state["python_execution"].passed, state["python_execution"].stderr
    assert state["go_execution"].passed, state["go_execution"].stderr
    tests = state["solution"].tests
    assert [t.origin for t in tests[:2]] == ["provided", "provided"]
    assert tests[0].args == [[2, 7, 11, 15], 9] and tests[0].expected == [0, 1]
    assert tests[1].args == [[3, 2, 4], 6]
    assert len(tests) == 12
    assert parse.await_count == 2


async def test_unparseable_example_is_normalized_and_placed_first(monkeypatch):
    prose = {
        "input": "Input: numbers are 2, 7, 11, 15 and the target is 9",
        "output": "the indices of 2 and 7",
    }
    normalized = [
        test_generator_node_module.NormalizedExample(
            example_index=0, args_json="[[2, 7, 11, 15], 9]", expected_json="[0, 1]"
        )
    ]
    parse = _install_client(
        monkeypatch,
        CodeGenOutput(entry_point=TWO_SUM_EP, code_python=TWO_SUM_PY, code_go=TWO_SUM_GO),
        _generated(TWO_SUM_GENERATED, normalized),
    )
    state = await _run_segment(_state("two sum", [prose], _analysis_two_sum()))

    assert state["python_execution"].passed, state["python_execution"].stderr
    assert state["go_execution"].passed, state["go_execution"].stderr
    first = state["solution"].tests[0]
    assert first.origin == "provided" and first.args == [[2, 7, 11, 15], 9]

    test_gen_messages = parse.await_args_list[1].kwargs["messages"]
    text = "\n".join(m["content"] for m in test_gen_messages)
    assert "numbers are 2, 7, 11, 15 and the target is 9" in text
    assert TWO_SUM_PY not in text and "seen = {}" not in text
    assert "seen := map" not in text


async def test_list_of_strings_to_string_with_awkward_text(monkeypatch):
    ep = EntryPoint(
        python_name="longest_common_prefix",
        go_name="longestCommonPrefix",
        params=[EntryParam(name="strs", type="list[str]")],
        return_type="str",
        unordered_result=False,
    )
    py = (
        "def longest_common_prefix(strs):\n"
        "    prefix = strs[0]\n"
        "    for s in strs[1:]:\n"
        "        while not s.startswith(prefix):\n"
        "            prefix = prefix[:-1]\n"
        "    return prefix\n"
    )
    go = (
        "package main\n\n"
        "func longestCommonPrefix(strs []string) string {\n"
        "\tprefix := strs[0]\n"
        "\tfor _, s := range strs[1:] {\n"
        "\t\tfor len(s) < len(prefix) || s[:len(prefix)] != prefix {\n"
        "\t\t\tprefix = prefix[:len(prefix)-1]\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn prefix\n"
        "}\n"
    )
    cases = [
        ("contains empty string", [["", "abc"]], ""),
        ("no common prefix", [["dog", "racecar", "car"]], ""),
        ("single element", [["alone"]], "alone"),
        ("non-ascii", [["日本語", "日本"]], "日本"),
        ("double quote", [['a"b', 'a"c']], 'a"'),
        ("identical", [["same", "same"]], "same"),
        ("prefix is whole first word", [["ab", "abc", "abd"]], "ab"),
        ("backslash", [["a\\b", "a\\c"]], "a\\"),
        ("longer common prefix", [["interview", "internet", "interval"]], "inter"),
        ("one char", [["a", "ab"]], "a"),
    ]
    _install_client(
        monkeypatch,
        CodeGenOutput(entry_point=ep, code_python=py, code_go=go),
        _generated([(label, args, want) for label, args, want in cases]),
    )
    examples = [{"input": 'strs = ["flower","flow","flight"]', "output": '"fl"'}]
    state = await _run_segment(
        _state("longest common prefix", examples, _analysis("list[str] strs", "str prefix"))
    )

    assert state["python_execution"].passed, state["python_execution"].stderr
    assert state["go_execution"].passed, state["go_execution"].stderr
    assert state["solution"].tests[0].expected == "fl"


async def test_wrong_solution_fails_both_languages_with_case_diagnostics(monkeypatch):
    wrong_py = "def two_sum(nums, target):\n    return []\n"
    wrong_go = "package main\n\nfunc twoSum(nums []int, target int) []int {\n\treturn []int{}\n}\n"
    _install_client(
        monkeypatch,
        CodeGenOutput(entry_point=TWO_SUM_EP, code_python=wrong_py, code_go=wrong_go),
        _generated(TWO_SUM_GENERATED),
    )
    state = await _run_segment(_state("two sum", TWO_SUM_EXAMPLES, _analysis_two_sum()))

    for key in ("python_execution", "go_execution"):
        result = state[key]
        assert result.passed is False
        assert result.exit_code not in (0, -1)
        assert "FAIL case 0" in result.stderr
        assert "timed out" not in result.stderr
