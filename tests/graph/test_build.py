from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.code_generator.node import CodeGenOutput
from algorunner.agents.solver.node import SolverOutput
from algorunner.agents.test_generator.node import GeneratedTests
from algorunner.agents.test_generator.node import TestCase as GoTestCase
from algorunner.graph.build import build_pipeline_graph
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.solution import Approach, ApproachList


async def _checkpointer_for(pg_pool):
    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    return checkpointer


def _initial_state(thread_id: str, problem_text: str) -> dict:
    return {
        "task_id": thread_id,
        "problem_text": problem_text,
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


async def test_build_pipeline_graph_happy_path_sets_analysis_result(
    pg_pool, mock_pipeline_openai
):
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    assert result_state["result"]["analysis"] is not None
    assert result_state["analysis"] is not None


async def test_build_pipeline_graph_persists_checkpoint_row_to_real_postgres(
    pg_pool, mock_pipeline_openai
):
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s", (thread_id,)
            )
            row = await cur.fetchone()
            count = row["count"] if isinstance(row, dict) else row[0]

    assert count >= 1


async def test_build_pipeline_graph_runs_analyzer_strategist_solver_end_to_end(
    pg_pool, mock_pipeline_openai
):
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    assert result_state["approaches"][0].technique == "hash map"
    assert result_state["result"]["solution"]["algorithm"]

    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s", (thread_id,)
            )
            row = await cur.fetchone()
            count = row["count"] if isinstance(row, dict) else row[0]

    assert count >= 1


async def test_build_pipeline_graph_runs_full_pipeline_through_code_and_test_gen(
    pg_pool, mock_pipeline_openai
):
    """Analyzer -> strategist -> solver -> code_generator -> test_generator
    -> finalize_success end-to-end against real Postgres, with each of the
    five LLM-backed nodes mocked at their shared `get_client` call site
    (`mock_pipeline_openai`). Asserts the persisted `result["solution"]` has
    non-empty dual-language code and a merged test list at least as long as
    the mocked generated-test count (Task 2)."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    solution = result_state["result"]["solution"]
    assert solution["code_python"]
    assert solution["code_go"]
    assert len(solution["tests"]) >= 10

    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s", (thread_id,)
            )
            row = await cur.fetchone()
            count = row["count"] if isinstance(row, dict) else row[0]

    assert count >= 1


def _mock_pipeline_openai_known_correct(monkeypatch):
    """Local variant of `conftest.py`'s `mock_pipeline_openai`, used ONLY by
    the execute_python/execute_go integration test below (Task 3, Plan
    02-05). The shared fixture's `GeneratedTests` are deliberately
    placeholder strings (`input="in-0"`, `output="out-0"`) — fine for
    Plan 02-04's assertions (which only check the merged test list's
    length), but not real, evaluable input/output EXPRESSIONS, so running
    them through `_render_test_harness` would fail to parse/compile rather
    than exercise real pass/fail execution.

    This mock's `code_python`/`code_go` implement the SAME trivial,
    scalar-input/output solution (`double`), with test-case `input`/
    `output` strings written as call/value expressions valid in BOTH
    languages simultaneously (`"double(5)"` / `"10"` parses as a real
    Python call AND a real Go call — no list/slice literal-syntax mismatch
    to reconcile). See graph/build.py's `_render_test_harness` docstring
    and this plan's SUMMARY.md for the known limitation this sidesteps:
    `_render_test_harness`'s Go-mode rendering assumes `input`/`output` are
    already valid Go expression syntax, which the current (Plan 02-04,
    unmodified by this plan) Test Generator prompt does not guarantee for
    non-scalar return types."""
    analysis = ProblemAnalysis(
        constraints=["1 <= x <= 10^4"],
        input_shape="int x",
        output_shape="int, x doubled",
        intent="Return double the input integer",
        difficulty="easy",
        needs_clarification=False,
        clarification_question=None,
    )
    approaches = ApproachList(
        approaches=[
            Approach(
                name="Direct multiplication",
                technique="arithmetic",
                summary="Multiply the input by two.",
            )
        ]
    )
    solver_output = SolverOutput(
        algorithm="Multiply the input integer by two and return it.",
        complexity_time="O(1), a single multiplication.",
        complexity_space="O(1), no extra storage.",
    )
    code_gen_output = CodeGenOutput(
        code_python="def double(x):\n    return x * 2\n",
        code_go="package main\n\nfunc double(x int) int {\n\treturn x * 2\n}\n",
    )
    # D-11: >= settings.test_generator_min_tests (10) generated tests are
    # required when fewer than 3 examples are provided (none here) — all
    # scalar int-in/int-out `double(n)` calls so each `input`/`output`
    # string is simultaneously a valid Python and Go expression (see
    # `_mock_pipeline_openai_known_correct`'s docstring above).
    generated_tests = GeneratedTests(
        tests=[
            GoTestCase(input=f"double({n})", output=str(n * 2))
            for n in range(-5, 6)
        ]
    )

    def _completion(parsed):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                parse=AsyncMock(
                    side_effect=[
                        _completion(analysis),
                        _completion(approaches),
                        _completion(solver_output),
                        _completion(code_gen_output),
                        _completion(generated_tests),
                    ]
                )
            )
        )
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)
    return fake_client


async def test_build_pipeline_graph_runs_full_pipeline_through_execution(
    pg_pool, monkeypatch
):
    """Analyzer -> strategist -> solver -> code_generator -> test_generator
    -> execute_python -> execute_go -> finalize_success end-to-end against
    real Postgres (Task 3), with the five LLM-backed nodes mocked to
    produce a KNOWN-CORRECT trivial solution (see
    `_mock_pipeline_openai_known_correct` above) so the executors run for
    real against real, compilable/runnable code — not a placeholder.
    Asserts both `python_execution.passed` and `go_execution.passed` are
    `True`."""
    _mock_pipeline_openai_known_correct(monkeypatch)
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "double a number"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    assert result_state["python_execution"] is not None
    assert result_state["go_execution"] is not None
    assert result_state["python_execution"].passed is True, result_state[
        "python_execution"
    ].stderr
    assert result_state["go_execution"].passed is True, result_state[
        "go_execution"
    ].stderr

    result = result_state["result"]
    assert result["python_execution"]["passed"] is True
    assert result["go_execution"]["passed"] is True
