"""Task 1 (plan 02-09): type vocabulary, EntryPoint/StructuredCase contracts,
provided-example conversion (D-10) and the Python/Go renderers, proven through
the REAL SubprocessPythonExecutor and REAL SubprocessGoExecutor (go build)."""

import pytest
from pydantic import ValidationError

from algorunner.graph.harness import (
    ensure_go_imports,
    render_go_program,
    render_python_program,
)
from algorunner.schemas.example_cases import (
    build_normalized_example,
    parse_provided_example,
)
from algorunner.schemas.solution import EntryParam, EntryPoint
from algorunner.schemas.typespec import (
    MAX_CASES,
    coerce_value,
    format_type,
    parse_json_text,
    parse_type,
)
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

# ---------------------------------------------------------------- typespec


@pytest.mark.parametrize(
    "text", ["int", "float", "bool", "str", "list[int]", "list[list[str]]", " list [ int ] "]
)
def test_parse_type_accepts_vocabulary(text):
    assert parse_type(text) is not None


@pytest.mark.parametrize(
    "text",
    ["dict[str, int]", "ListNode", "Optional[int]", "tuple", "list[]", "Int",
     "list[list[list[list[list[int]]]]]"],
)
def test_parse_type_rejects_outside_vocabulary(text):
    with pytest.raises(ValueError):
        parse_type(text)


def test_format_type_is_canonical():
    assert format_type(parse_type(" list [ list[ int ] ] ")) == "list[list[int]]"


def test_coerce_value_rules():
    assert coerce_value(3, parse_type("float")) == 3.0
    assert isinstance(coerce_value(3, parse_type("float")), float)
    for bad, t in [(True, "int"), (1, "bool"), (2.0, "int"), (float("nan"), "float"),
                   (2**63, "int"), ("\ud800", "str"), ("x", "int")]:
        with pytest.raises(ValueError):
            coerce_value(bad, parse_type(t))
    with pytest.raises(ValueError, match=r"args\[0\]\[2\]"):
        coerce_value([[1, 2, "x"]], parse_type("list[list[int]]"), path="args")


def test_parse_json_text_rejects_nan():
    with pytest.raises(ValueError):
        parse_json_text("NaN")
    with pytest.raises(ValueError):
        parse_json_text("{bad")
    assert parse_json_text("[1, 2]") == [1, 2]


# -------------------------------------------------------------- EntryPoint


def _ep(**over) -> EntryPoint:
    fields = dict(
        python_name="two_sum",
        go_name="twoSum",
        params=[EntryParam(name="nums", type="list[int]"), EntryParam(name="target", type="int")],
        return_type="list[int]",
        unordered_result=True,
    )
    fields.update(over)
    return EntryPoint(**fields)


@pytest.mark.parametrize(
    "over",
    [
        {"python_name": "class"},
        {"python_name": "not-ident"},
        {"python_name": "_algorunner_x"},
        {"go_name": "func"},
        {"go_name": "main"},
        {"go_name": "init"},
        {"go_name": "algorunnerX"},
        {"go_name": "2bad"},
        {"params": []},
        {"params": [EntryParam(name="a", type="int"), EntryParam(name="a", type="int")]},
        {"return_type": "dict[str, int]"},
    ],
)
def test_entry_point_rejects(over):
    with pytest.raises(ValidationError):
        _ep(**over)


def test_entry_point_rejects_bad_param_type_and_canonicalizes():
    with pytest.raises(ValidationError):
        EntryParam(name="x", type="Optional[int]")
    assert EntryParam(name="x", type="list [ int ]").type == "list[int]"


def test_make_case_validation_and_normalization():
    ep = _ep(return_type="float", unordered_result=False)
    case = ep.make_case(label="a", origin="generated", args=[[1], 2], expected=3)
    assert case.expected == 3.0 and isinstance(case.expected, float)
    with pytest.raises(ValueError):
        ep.make_case(label="a", origin="generated", args=[[1]], expected=3)
    with pytest.raises(ValueError):
        ep.make_case(label="a", origin="generated", args=[["x"], 2], expected=3)
    with pytest.raises(ValueError):
        ep.make_case(label="a", origin="generated", args=[[1] * 30000, 2], expected=3)


# ------------------------------------------------------- example converter


def test_parse_provided_example_by_name():
    ep = _ep()
    case = parse_provided_example(
        ep, index=0, input_text="nums=[2,7,11,15], target=9", output_text="[0,1]"
    )
    assert case is not None
    assert case.origin == "provided" and case.label == "provided example 0"
    assert case.args == [[2, 7, 11, 15], 9] and case.expected == [0, 1]


def test_parse_provided_example_prefix_spaces_positional_and_strings():
    ep = _ep()
    case = parse_provided_example(
        ep, index=1, input_text="Input: nums = [3, 2, 4], target = 6", output_text="Output: [1, 2]"
    )
    assert case is not None and case.args == [[3, 2, 4], 6]
    ep2 = EntryPoint(
        python_name="f", go_name="f",
        params=[EntryParam(name="words", type="list[str]"), EntryParam(name="sep", type="str")],
        return_type="str", unordered_result=False,
    )
    case2 = parse_provided_example(
        ep2, index=0, input_text='strs = ["a,b", "c"], s = ","', output_text='"a,b,c"'
    )
    assert case2 is not None and case2.args == [["a,b", "c"], ","]  # positional mapping


@pytest.mark.parametrize(
    "inp,out",
    [
        ("numbers are 2, 7, 11, 15 and the target is 9", "the first two"),
        ("nums=[2,7, target=9", "[0,1]"),
        ("nums=[2,7], target=9", "indices 0 and 1"),
        ("nums=[2,7]", "[0,1]"),
        ("nums=[True], target=1", "[0,1]"),
    ],
)
def test_parse_provided_example_returns_none(inp, out):
    assert parse_provided_example(_ep(), index=0, input_text=inp, output_text=out) is None


def test_build_normalized_example():
    ep = _ep()
    case = build_normalized_example(
        ep, index=2, output_text="[0, 1]", args_json="[[2,7,11,15], 9]", expected_json="[0,1]"
    )
    assert case.origin == "provided" and case.args == [[2, 7, 11, 15], 9]
    # non-JSON prose output: equality check skipped, type check remains
    build_normalized_example(
        ep, index=2, output_text="the first two", args_json="[[2,7], 9]", expected_json="[0,1]"
    )
    with pytest.raises(ValueError, match="2"):
        build_normalized_example(
            ep, index=2, output_text="[0,1]", args_json="[[2,7], 9]", expected_json="[1,1]"
        )
    with pytest.raises(ValueError):
        build_normalized_example(
            ep, index=2, output_text="x", args_json='{"a": 1}', expected_json="[0,1]"
        )
    with pytest.raises(ValueError):
        build_normalized_example(
            ep, index=2, output_text="x", args_json="[[2,7], \"9\"]", expected_json="[0,1]"
        )


# ------------------------------------------------------------ ensure_go_imports


def test_ensure_go_imports_only_missing():
    code = 'package main\n\nimport "fmt"\n\nfunc f() { fmt.Println() }\n'
    out = ensure_go_imports(code, ("fmt", "os"))
    assert out.count('"fmt"') == 1 and '"os"' in out
    assert out.index("package main") < out.index('"os"')
    block = 'package main\n\nimport (\n\t"fmt"\n\t"os"\n)\n'
    assert ensure_go_imports(block, ("fmt", "os")) == block
    assert '"sort"' in ensure_go_imports(block, ("fmt", "sort"))


# --------------------------------------------------------------- renderers


def _two_sum_cases(ep):
    data = [
        ("basic", [[2, 7, 11, 15], 9], [0, 1]),
        ("duplicates", [[3, 3], 6], [0, 1]),
        ("negatives", [[-1, -2, -3, -4, -5], -8], [2, 4]),
        ("empty array", [[], 0], []),
    ]
    return [ep.make_case(label=l, origin="generated", args=a, expected=e) for l, a, e in data]


PY_TWO_SUM_REVERSED = (
    "def two_sum(nums, target):\n"
    "    seen = {}\n"
    "    for i, n in enumerate(nums):\n"
    "        if target - n in seen:\n"
    "            return [i, seen[target - n]]\n"
    "        seen[n] = i\n"
    "    return []\n"
)
GO_TWO_SUM_REVERSED = (
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
PY_WRONG = "def two_sum(nums, target):\n    if nums == [3, 3]:\n        raise RuntimeError('boom')\n    return [9, 9]\n"
GO_WRONG = (
    "package main\n\nfunc twoSum(nums []int, target int) []int {\n"
    "\tif len(nums) == 2 && nums[0] == 3 {\n\t\tpanic(\"boom\")\n\t}\n"
    "\treturn []int{9, 9}\n}\n"
)


async def _run_py(code, ep, cases):
    r = render_python_program(code, ep, cases)
    return await SubprocessPythonExecutor().run(r.code, r.tests, timeout_s=30.0)


async def _run_go(code, ep, cases):
    r = render_go_program(code, ep, cases)
    return await SubprocessGoExecutor().run(r.code, r.tests, timeout_s=60.0)


async def test_two_sum_unordered_passes_python():
    ep = _ep()
    res = await _run_py(PY_TWO_SUM_REVERSED, ep, _two_sum_cases(ep))
    assert res.passed, res.stderr
    assert "ALGORUNNER PASS 4/4" in res.stdout


async def test_two_sum_unordered_passes_go():
    ep = _ep()
    res = await _run_go(GO_TWO_SUM_REVERSED, ep, _two_sum_cases(ep))
    assert res.passed, res.stderr
    assert "ALGORUNNER PASS 4/4" in res.stdout


async def test_wrong_and_raising_reported_per_case_in_both_languages():
    ep = _ep()
    cases = _two_sum_cases(ep)
    py = await _run_py(PY_WRONG, ep, cases)
    go = await _run_go(GO_WRONG, ep, cases)
    for res in (py, go):
        assert not res.passed and res.exit_code != 0
        assert "FAIL case 0 (basic)" in res.stderr
        assert "FAIL case 1 (duplicates)" in res.stderr  # raised / panicked
        assert "FAIL case 3 (empty array)" in res.stderr  # later cases still ran
        assert "4 of 4 cases failed" in res.stderr


AWKWARD = ['he said "hi"', "back\\slash", "line1\nline2", "日本語", "astral \U0001F600", "", "%s %d"]


def _echo_ep():
    return EntryPoint(
        python_name="echo", go_name="echo",
        params=[EntryParam(name="xs", type="list[str]")],
        return_type="list[str]", unordered_result=False,
    )


async def test_string_literals_round_trip_in_both_languages():
    ep = _echo_ep()
    cases = [
        ep.make_case(label='evil "label" \\ \n 日', origin="generated", args=[AWKWARD], expected=AWKWARD),
        ep.make_case(label="single", origin="generated", args=[["x"]], expected=["x"]),
    ]
    py = await _run_py("def echo(xs):\n    return list(xs)\n", ep, cases)
    go = await _run_go("package main\n\nfunc echo(xs []string) []string {\n\treturn xs\n}\n", ep, cases)
    assert py.passed, py.stderr
    assert go.passed, go.stderr


async def test_nested_floats_bool_nil_vs_empty_go_and_python():
    ep = EntryPoint(
        python_name="scale", go_name="scale",
        params=[
            EntryParam(name="m", type="list[list[float]]"),
            EntryParam(name="k", type="float"),
            EntryParam(name="flag", type="bool"),
        ],
        return_type="list[list[float]]", unordered_result=False,
    )
    cases = [
        ep.make_case(label="scaled", origin="generated", args=[[[1.0, 2.5], [0.1]], 3, True],
                     expected=[[3.0, 7.5], [0.30000000000000004]]),
        ep.make_case(label="empty", origin="generated", args=[[], 1.0, False], expected=[]),
    ]
    py_code = (
        "def scale(m, k, flag):\n    return [[x * k for x in row] for row in m]\n"
    )
    go_code = (
        "package main\n\nfunc scale(m [][]float64, k float64, flag bool) [][]float64 {\n"
        "\tvar out [][]float64\n"
        "\tfor _, row := range m {\n\t\tr := []float64{}\n"
        "\t\tfor _, x := range row {\n\t\t\tr = append(r, x*k)\n\t\t}\n"
        "\t\tout = append(out, r)\n\t}\n\treturn out\n}\n"
    )
    py = await _run_py(py_code, ep, cases)
    go = await _run_go(go_code, ep, cases)
    assert py.passed, py.stderr
    assert go.passed, go.stderr


def test_renderers_refuse_empty_over_limit_and_invalid_cases():
    ep = _ep()
    good = _two_sum_cases(ep)[0]
    for render in (render_python_program, render_go_program):
        with pytest.raises(ValueError):
            render("x", ep, [])
        with pytest.raises(ValueError):
            render("x", ep, [good] * (MAX_CASES + 1))
        bad = good.model_copy(update={"args": [["x"], 1]})
        with pytest.raises(ValueError):
            render("x", ep, [bad])


def test_renderers_escape_hostile_labels():
    ep = _ep()
    hostile = 'x"); import os; os.system("boom"); ("'
    case = ep.make_case(label=hostile, origin="generated", args=[[1], 1], expected=[0])
    py = render_python_program("def two_sum(a, b):\n    return [0]\n", ep, [case])
    go = render_go_program("package main\n", ep, [case])
    import ast

    imports = [n for n in ast.walk(ast.parse(py.tests)) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert {a.name for n in imports for a in n.names} == {"math", "sys"}
    assert "\n" not in go.tests.split("algorunnerCheck(0, ")[1].split(",")[0]
