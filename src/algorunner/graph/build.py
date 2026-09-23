"""Compiled LangGraph StateGraph for the real Phase 2 pipeline, checkpointed
to Postgres (D-12).

As of this plan the pipeline runs Analyzer -> Strategist -> Solver ->
CodeGenerator -> TestGenerator -> ExecutePython -> ExecuteGo -> Reviewer,
then a bounded correction loop (`decide_after_review`) back to the Solver or
Code Generator, ending in `finalize_success` or `finalize_failed`. This
module keeps the injected-checkpointer convention established by Phase 1's stub graph
(the checkpointer is never constructed here, only wired in -
`worker/tasks.py` owns construction).

The execute nodes are thin wrappers: `graph/harness.py` renders the
language-neutral `Solution.tests` into the `(code, tests)` strings the
unchanged executors accept (D-00c, EXEC-03).

Replaces Phase 1's `build_stub_graph`/`stub_node` - the Phase-1-only magic-
string failure-simulation hook is retired; real pipeline failure paths
(CR-01 in `worker/tasks.py`) now supersede it.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from algorunner.agents.code_generator.node import code_generator_node
from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.agents.reviewer.node import reviewer_node
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.agents.solver.node import solver_node
from algorunner.agents.test_generator.node import test_generator_node
from algorunner.graph.harness import render_go_program, render_python_program
from algorunner.graph.routing import decide_after_analysis, decide_after_review
from algorunner.graph.state import GraphState
from algorunner.schemas.execution import ExecutionResult
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

# F8: applies to `go build` and the binary run independently. A fresh-cache
# build of the harness measured ~3s locally; the 10s executor default leaves
# too little margin on a CPU-limited container, and a spurious timeout on a
# correct solution would be a false verification failure.
_GO_TIMEOUT_S = 30.0

_PASS_MARKER = "ALGORUNNER PASS"


def _require_pass_marker(result: ExecutionResult) -> ExecutionResult:
    """T-02-09-04: exit code 0 alone is not proof the harness ran every case
    (generated code could call exit() at import time). A pass must also carry
    the harness's `ALGORUNNER PASS n/n` line."""
    if result.passed and _PASS_MARKER not in result.stdout:
        return result.model_copy(
            update={
                "passed": False,
                "stderr": result.stderr
                + "\nharness pass marker missing: the test harness did not run to completion",
            }
        )
    return result


async def execute_python_node(state: GraphState) -> dict:
    solution = state["solution"]
    program = render_python_program(solution.code_python, solution.entry_point, solution.tests)
    result = await SubprocessPythonExecutor().run(program.code, program.tests)
    return {"python_execution": _require_pass_marker(result)}


async def execute_go_node(state: GraphState) -> dict:
    solution = state["solution"]
    program = render_go_program(solution.code_go, solution.entry_point, solution.tests)
    result = await SubprocessGoExecutor().run(
        program.code, program.tests, timeout_s=_GO_TIMEOUT_S
    )
    return {"go_execution": _require_pass_marker(result)}


async def clarification_gate_node(state: GraphState) -> dict:
    # Zero-logic on purpose: on resume only this trivial node re-executes,
    # never the Analyzer's LLM call (RESEARCH Pattern 2).
    answer = interrupt(state["analysis"].clarification_question)
    return {
        "clarification_answer": answer,
        "clarification_rounds": state["clarification_rounds"] + 1,
    }


async def finalize_success(state: GraphState) -> dict:
    """Writes the final `result` dict for a successfully completed run.

    Later plans extend this function's body to add `review` fields as more
    nodes land - never replace it wholesale.

    `solution` (dumped, JSON-safe) supersedes the interim `solver_output`
    key; it now carries the entry point and the structured tests.
    `python_execution`/`go_execution` are the first REAL, executed pass/fail
    results the pipeline persists (EXEC-01/02).
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
            "review": state["review"].model_dump() if state["review"] else None,
            "assumption_stated": state.get("assumption_stated"),
        }
    }


async def finalize_failed(state: GraphState) -> dict:
    """Terminal FAILED result once the correction loop is exhausted (REV-05)."""
    review = state["review"]
    issues = [i.description for i in review.issues] if review else []
    return {
        "error": {
            "code": "CORRECTION_LOOP_EXHAUSTED",
            "message": f"Failed after {state['iterations']} iteration(s); last issues: {issues}",
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
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_node("finalize_failed", finalize_failed)
    builder.add_edge(START, "analyzer")
    builder.add_node("clarification_gate", clarification_gate_node)
    builder.add_conditional_edges(
        "analyzer",
        decide_after_analysis,
        {"clarification_gate": "clarification_gate", "strategist": "strategist"},
    )
    builder.add_edge("clarification_gate", "analyzer")
    builder.add_edge("strategist", "solver")
    builder.add_edge("solver", "code_generator")
    builder.add_edge("code_generator", "test_generator")
    builder.add_edge("test_generator", "execute_python")
    builder.add_edge("execute_python", "execute_go")
    builder.add_edge("execute_go", "reviewer")
    builder.add_conditional_edges(
        "reviewer",
        decide_after_review,
        {
            "finalize_success": "finalize_success",
            "finalize_failed": "finalize_failed",
            "solver": "solver",
            "code_generator": "code_generator",
        },
    )
    builder.add_edge("finalize_success", END)
    builder.add_edge("finalize_failed", END)
    return builder.compile(checkpointer=checkpointer)
