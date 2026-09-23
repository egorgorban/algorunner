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
        "python_execution": None,
        "go_execution": None,
        "review": None,
        "review_history": [],
        "iterations": 0,
        "max_iterations": 5,
        "result": None,
        "error": None,
    }


async def test_build_pipeline_graph_happy_path_sets_analysis_result(pg_pool, mock_openai_parse):
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
    pg_pool, mock_openai_parse
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
