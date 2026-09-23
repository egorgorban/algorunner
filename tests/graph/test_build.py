from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from algorunner.graph.build import build_pipeline_graph


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
    non-empty dual-language code and a structured test list at least as long
    as the mocked generated-test count."""
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


async def test_build_pipeline_graph_runs_full_pipeline_through_execution(
    pg_pool, mock_pipeline_openai
):
    """Full graph against real Postgres, real python3 and real `go build`,
    with only the five LLM calls mocked. The shared fixture's canned solution
    is a correct Two Sum (list[int], int -> list[int]) in both languages, so
    both executions must pass through the structured-case renderers."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    assert result_state["python_execution"] is not None
    assert result_state["go_execution"] is not None
    assert result_state["python_execution"].passed is True, result_state[
        "python_execution"
    ].stderr
    assert result_state["go_execution"].passed is True, result_state["go_execution"].stderr

    result = result_state["result"]
    assert result["python_execution"]["passed"] is True
    assert result["go_execution"]["passed"] is True
    assert result["solution"]["entry_point"]["python_name"] == "two_sum"
    for case in result["solution"]["tests"]:
        assert case["origin"] in ("provided", "generated")
        assert isinstance(case["args"], list)
        assert "input" not in case and "output" not in case
