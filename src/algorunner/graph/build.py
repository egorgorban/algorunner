"""Compiled LangGraph StateGraph for the real Phase 2 pipeline, checkpointed
to Postgres (D-12).

As of this plan the pipeline runs Analyzer -> Strategist -> Solver ->
CodeGenerator -> TestGenerator -> ExecutePython -> ExecuteGo ->
`finalize_success`; later plans (02-06/02-07) extend this same graph with
the Reviewer node and correction-loop conditional edges — this module keeps
the injected-checkpointer convention established by Phase 1's stub graph
(the checkpointer is never constructed here, only wired in —
`worker/tasks.py` owns construction).

Replaces Phase 1's `build_stub_graph`/`stub_node` — the Phase-1-only magic-
string failure-simulation hook is retired; real pipeline failure paths
(CR-01 in `worker/tasks.py`) now supersede it.
"""

import re

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algorunner.agents.code_generator.node import code_generator_node
from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.agents.solver.node import solver_node
from algorunner.agents.test_generator.node import test_generator_node
from algorunner.graph.state import GraphState
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

# --- Go import-injection helpers (execute_go_node only) ---
#
# Go requires every `import` to appear before other top-level declarations,
# and re-importing an already-present package in a second `import` block is
# a compile error ("redeclared in this block") while an import that ends up
# unused is ALSO a compile error — so the Go-mode harness's required
# packages (`reflect`, `os`) can only be safely injected into
# `state["solution"].code_go` when they are (a) not already imported and
# (b) actually used by a non-empty rendered harness. This mirrors, but is
# deliberately kept separate from, `go_executor/subprocess_backend.py`'s
# own `_check_go_denylist` import-scanning regexes — that module's contract
# (caller supplies fully self-sufficient `code`/`tests`) is unchanged by
# this plan; only `execute_go_node` needs import-merging, since it is the
# one call site handing the Go executor LLM-generated code it doesn't
# control the imports of.
_GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\(([^)]*)\)", re.DOTALL)
_GO_IMPORT_SINGLE_RE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
_GO_QUOTED_PATH_RE = re.compile(r'"([^"]+)"')

_GO_HARNESS_IMPORTS = ("reflect", "os")


def _existing_go_imports(code: str) -> set[str]:
    paths: list[str] = []
    for block in _GO_IMPORT_BLOCK_RE.findall(code):
        paths.extend(_GO_QUOTED_PATH_RE.findall(block))
    paths.extend(_GO_IMPORT_SINGLE_RE.findall(code))
    return set(paths)


def _ensure_go_imports(code: str, required: tuple[str, ...]) -> str:
    missing = [pkg for pkg in required if pkg not in _existing_go_imports(code)]
    if not missing:
        return code
    import_block = "import (\n" + "".join(f'\t"{pkg}"\n' for pkg in missing) + ")\n"
    lines = code.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip().startswith("package "):
            return "".join(lines[: i + 1]) + "\n" + import_block + "".join(lines[i + 1 :])
    # No `package` line found (malformed code) — prepend defensively; the
    # subsequent `go build` will surface a clear compile error either way.
    return import_block + code


def _render_test_harness(tests: list[dict], *, language: str) -> str:
    """Renders `Solution.tests` (merged provided-examples + generated test
    cases, each `{"input": ..., "output": ...}`) into the runnable
    assert-based harness format each executor's `tests: str` argument
    expects.

    `input`/`output` are expected to already be call/value EXPRESSIONS in
    the target language (e.g. Python: `"two_sum([2, 7, 11, 15], 9)"` /
    `"[0, 1]"`; Go: `"double(5)"` / `"10"`), evaluated/compared directly —
    matching this plan's `<action>`: "evaluates the input and compares to
    expected output, exiting non-zero on first mismatch".

    Deviation from the plan's literal `_render_test_harness(tests: list[dict])
    -> str` signature (Rule 1 — auto-fixed bug): Python and Go source syntax
    are mutually incompatible (a Python `assert` line is not valid Go, and
    Go has no `eval`), so a single no-parameter renderer would silently
    hand one executor source text it can never compile/run. The
    `language` keyword is the minimal change that keeps ONE shared
    walk over `tests` (this is still the single place that format is
    produced — see SUMMARY.md for the full writeup) while emitting
    syntactically valid output for whichever backend calls it.
    """
    if language == "python":
        return "\n".join(f"assert ({t['input']}) == ({t['output']})" for t in tests)
    if language == "go":
        return "\n".join(
            f'if !reflect.DeepEqual({t["input"]}, {t["output"]}) {{\n\tos.Exit(1)\n}}'
            for t in tests
        )
    raise ValueError(f"unsupported language: {language!r}")


async def execute_python_node(state: GraphState) -> dict:
    result = await SubprocessPythonExecutor().run(
        state["solution"].code_python,
        _render_test_harness(state["solution"].tests, language="python"),
    )
    return {"python_execution": result}


async def execute_go_node(state: GraphState) -> dict:
    harness = _render_test_harness(state["solution"].tests, language="go")
    code = state["solution"].code_go
    if harness.strip():
        code = _ensure_go_imports(code, _GO_HARNESS_IMPORTS)
    result = await SubprocessGoExecutor().run(code, harness)
    return {"go_execution": result}


async def finalize_success(state: GraphState) -> dict:
    """Writes the final `result` dict for a successfully completed run.

    Later plans extend this function's body to add `review` fields as more
    nodes land — never replace it wholesale.

    `solution` (dumped, JSON-safe) now supersedes the interim `solver_output`
    key Plan 02-03 added to the persisted `result` dict — `solver_output`
    stays in `GraphState` as an internal field (Code Generator reads it
    directly), it just no longer needs to appear in the final persisted
    result once `solution` fully subsumes it (approach/algorithm/complexity
    plus code_python/code_go/tests). `python_execution`/`go_execution` are
    this plan's addition (EXEC-01/02) — the first point where the pipeline
    persists a REAL, executed pass/fail result, not just generated text.
    """
    return {
        "result": {
            "analysis": state["analysis"].model_dump() if state["analysis"] else None,
            "approaches": (
                [approach.model_dump() for approach in state["approaches"]]
                if state["approaches"]
                else None
            ),
            "solution": state["solution"].model_dump() if state["solution"] else None,
            "python_execution": (
                state["python_execution"].model_dump()
                if state["python_execution"]
                else None
            ),
            "go_execution": (
                state["go_execution"].model_dump() if state["go_execution"] else None
            ),
        }
    }


def build_pipeline_graph(checkpointer: object) -> CompiledStateGraph:
    builder = StateGraph(GraphState)
    builder.add_node("analyzer", problem_analyzer_node)
    builder.add_node("strategist", solution_strategist_node)
    builder.add_node("solver", solver_node)
    builder.add_node("code_generator", code_generator_node)
    builder.add_node("test_generator", test_generator_node)
    builder.add_node("execute_python", execute_python_node)
    builder.add_node("execute_go", execute_go_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_edge(START, "analyzer")
    builder.add_edge("analyzer", "strategist")
    builder.add_edge("strategist", "solver")
    builder.add_edge("solver", "code_generator")
    builder.add_edge("code_generator", "test_generator")
    builder.add_edge("test_generator", "execute_python")
    builder.add_edge("execute_python", "execute_go")
    builder.add_edge("execute_go", "finalize_success")
    builder.add_edge("finalize_success", END)
    return builder.compile(checkpointer=checkpointer)
