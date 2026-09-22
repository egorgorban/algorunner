from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

import algorunner.graph.build as graph_build
from algorunner.graph.build import build_stub_graph


async def _checkpointer_for(pg_pool):
    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    return checkpointer


async def test_build_stub_graph_happy_path_sets_result(pg_pool, monkeypatch):
    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(graph_build.asyncio, "sleep", _no_sleep)

    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_stub_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        {"task_id": thread_id, "problem_text": "two sum", "result": None, "error": None},
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result_state["result"] is not None
    assert result_state["error"] is None


async def test_build_stub_graph_fail_test_marker_sets_error(pg_pool, monkeypatch):
    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(graph_build.asyncio, "sleep", _no_sleep)

    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_stub_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        {
            "task_id": thread_id,
            "problem_text": "two sum FAIL_TEST",
            "result": None,
            "error": None,
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result_state["result"] is None
    assert result_state["error"] is not None
    assert result_state["error"]["code"] == "SIMULATED_FAILURE"


async def test_build_stub_graph_persists_checkpoint_row_to_real_postgres(pg_pool, monkeypatch):
    async def _no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(graph_build.asyncio, "sleep", _no_sleep)

    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_stub_graph(checkpointer)

    thread_id = str(uuid4())
    await graph.ainvoke(
        {"task_id": thread_id, "problem_text": "two sum", "result": None, "error": None},
        config={"configurable": {"thread_id": thread_id}},
    )

    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s", (thread_id,)
            )
            row = await cur.fetchone()
            count = row["count"] if isinstance(row, dict) else row[0]

    assert count >= 1
