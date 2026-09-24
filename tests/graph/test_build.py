"""Tests for Phase 3 multi-approach parent graph (D-08, D-13)."""

from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from algorunner.graph.build import build_pipeline_graph


async def _checkpointer_for(pg_pool):
    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    return checkpointer


def _initial_state(thread_id: str, problem_text: str) -> dict:
    """Initial GraphState for Phase 3: parent shape, no per-solution keys."""
    return {
        "task_id": thread_id,
        "problem_text": problem_text,
        "language": "en",
        "examples": [],
        "analysis": None,
        "clarification_rounds": 0,
        "clarification_answer": None,
        "assumption_stated": None,
        "approaches": [],
        "max_iterations": 5,
        "approach_outcomes": {},
        "result": None,
        "error": None,
    }


async def test_build_pipeline_graph_happy_path_sets_analysis_result(
    pg_pool, mock_pipeline_openai
):
    """Happy path: analyzer runs, analysis is set, error is None."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None
    assert result_state["analysis"] is not None


async def test_build_pipeline_graph_persists_checkpoint_row_to_real_postgres(
    pg_pool, mock_pipeline_openai
):
    """Checkpoints persist to Postgres, including branch checkpoints."""
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

    # At least one checkpoint (actual count will be higher for multi-step graph)
    assert count >= 1

    # Verify that at least one checkpoint has run_approach: namespace
    async with pg_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM checkpoints WHERE thread_id = %s AND checkpoint_ns LIKE 'run_approach:%'",
                (thread_id,),
            )
            row = await cur.fetchone()
            run_approach_count = row["count"] if isinstance(row, dict) else row[0]

    assert run_approach_count >= 1


async def test_build_pipeline_graph_runs_analyzer_strategist_solver_end_to_end(
    pg_pool, mock_pipeline_openai
):
    """Analyzer -> strategist -> solver runs, two approaches fan out, both executed."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    # No error on success
    assert result_state["error"] is None

    # Two approaches returned by strategist
    assert len(result_state["approaches"]) == 2
    techniques = sorted([a.technique for a in result_state["approaches"]])
    assert techniques == ["brute force", "hash map"]

    # Both approaches have outcomes
    outcomes = result_state["approach_outcomes"]
    assert len(outcomes) == 2
    assert 0 in outcomes
    assert 1 in outcomes

    # Approaches were detected correctly in solver (message content)
    assert mock_pipeline_openai.calls.count("SolverOutput") == 2


async def test_build_pipeline_graph_runs_full_pipeline_through_code_and_test_gen(
    pg_pool, mock_pipeline_openai
):
    """Full pipeline: code and test generation for two approaches."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None

    # Check result.approaches index (D-13)
    result = result_state["result"]
    assert "approaches" in result
    approaches_index = result["approaches"]
    assert len(approaches_index) == 2

    # Check order and content
    assert approaches_index[0]["approach_id"] == 0
    assert approaches_index[0]["name"] == "Brute force pairs"
    assert approaches_index[1]["approach_id"] == 1
    assert approaches_index[1]["name"] == "Hash map lookup"

    # No per-solution keys in result (D-13 promote decision)
    assert "solution" not in result
    assert "analysis" not in result

    # Both code generators ran (one per approach)
    assert mock_pipeline_openai.calls.count("CodeGenOutput") == 2
    assert mock_pipeline_openai.calls.count("GeneratedTests") == 2


async def test_build_pipeline_graph_runs_full_pipeline_through_execution(
    pg_pool, mock_pipeline_openai
):
    """Full graph: real Python/Go execution, both approaches verify, reviewer passes."""
    checkpointer = await _checkpointer_for(pg_pool)
    graph = build_pipeline_graph(checkpointer)

    thread_id = str(uuid4())
    result_state = await graph.ainvoke(
        _initial_state(thread_id, "two sum"),
        config={"configurable": {"thread_id": thread_id}},
        durability="sync",
    )

    assert result_state["error"] is None

    # Both approaches verified (status="verified")
    outcomes = result_state["approach_outcomes"]
    for idx in [0, 1]:
        assert idx in outcomes
        outcome = outcomes[idx]
        assert outcome.status == "verified", f"Approach {idx} status: {outcome.status}"
        assert outcome.iterations == 1
        assert outcome.final_review is not None
        assert outcome.final_review.passed is True
        assert outcome.final_solution is not None

        # Both executions passed for each approach
        assert outcome.final_solution.code_python
        assert outcome.final_solution.code_go
        assert len(outcome.final_solution.tests) >= 10

    # Result carries verified approaches index
    result = result_state["result"]
    approaches_index = result["approaches"]
    for idx in [0, 1]:
        assert approaches_index[idx]["status"] == "verified"
        assert approaches_index[idx]["iterations"] == 1

    # Code was executed correctly (brute force and hash map both work)
    assert mock_pipeline_openai.calls.count("ReviewResult") == 2

    # Verify that solutions carry the correct code for each approach
    brute_code = mock_pipeline_openai.canned_code["Brute force pairs"].code_python
    hash_code = mock_pipeline_openai.canned_code["Hash map lookup"].code_python

    brute_outcome = outcomes[0]
    hash_outcome = outcomes[1]

    assert brute_outcome.final_solution.code_python == brute_code
    assert hash_outcome.final_solution.code_python == hash_code
