from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

import algorunner.llm.client_factory as client_factory_module
from algorunner.graph.build import build_pipeline_graph
from algorunner.graph.routing import decide_after_analysis
from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor
from tests.graph.test_build import _initial_state

QUESTION = "Which array does the problem operate on?"


def _analysis(needs: bool) -> ProblemAnalysis:
    return ProblemAnalysis(
        constraints=[],
        input_shape="list[int]",
        output_shape="int",
        intent="find something",
        difficulty="easy",
        needs_clarification=needs,
        clarification_question=QUESTION if needs else None,
    )


def _completion(parsed):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))]
    )


async def _setup(pg_pool, monkeypatch, mock_pipeline_openai, analyzer_needs: list[bool]):
    """Reuse the pipeline fixture's canned completions per response type, but
    make the Analyzer's clarification flag follow `analyzer_needs` (last value
    repeats)."""
    fake_client = mock_pipeline_openai
    # Get canned responses from the mock's own dispatch
    default_dispatch = fake_client.default_dispatch
    by_type: dict[str, object] = {}

    # Wrap canned responses in completion envelope
    for name, parsed in fake_client.canned.items():
        by_type[name] = _completion(parsed)

    analyzer_calls: list[list[dict]] = []

    async def dispatch(**kwargs):
        name = kwargs.get("response_format", type(None)).__name__
        if name == "ProblemAnalysis":
            idx = min(len(analyzer_calls), len(analyzer_needs) - 1)
            analyzer_calls.append(kwargs["messages"])
            return _completion(_analysis(analyzer_needs[idx]))
        # Use canned completion if available, else fall back to default dispatch
        if name in by_type:
            return by_type[name]
        return await default_dispatch(**kwargs)

    fake_client.chat.completions.parse = AsyncMock(side_effect=dispatch)
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    ok = ExecutionResult(
        passed=True, stdout="ALGORUNNER PASS 10/10", stderr="", exit_code=0, duration_ms=1
    )
    monkeypatch.setattr(SubprocessPythonExecutor, "run", AsyncMock(return_value=ok))
    monkeypatch.setattr(SubprocessGoExecutor, "run", AsyncMock(return_value=ok))

    checkpointer = AsyncPostgresSaver(pg_pool)
    await checkpointer.setup()
    return build_pipeline_graph(checkpointer), analyzer_calls


def test_decide_after_analysis_routes_on_flag():
    assert decide_after_analysis({"analysis": _analysis(True)}) == "clarification_gate"
    assert decide_after_analysis({"analysis": _analysis(False)}) == "strategist"


async def test_ambiguous_problem_pauses_then_resumes_same_thread(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    graph, analyzer_calls = await _setup(
        pg_pool, monkeypatch, mock_pipeline_openai, [True, False]
    )
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    paused = await graph.ainvoke(
        _initial_state(thread_id, "do the thing"), config=config, durability="sync"
    )
    assert "__interrupt__" in paused
    assert paused["__interrupt__"][0].value == QUESTION
    assert len(analyzer_calls) == 1

    resumed = await graph.ainvoke(Command(resume="my answer"), config=config, durability="sync")
    assert "__interrupt__" not in resumed
    assert resumed["error"] is None
    assert resumed["result"] is not None
    assert resumed["clarification_rounds"] == 1
    assert len(analyzer_calls) == 2
    # the answer reached the re-run Analyzer prompt, delimited as data
    assert "my answer" in analyzer_calls[1][-1]["content"]
    assert QUESTION in analyzer_calls[1][-1]["content"]


async def test_round_cap_forces_assumption_instead_of_third_pause(
    pg_pool, mock_pipeline_openai, monkeypatch
):
    graph, analyzer_calls = await _setup(pg_pool, monkeypatch, mock_pipeline_openai, [True])
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    first = await graph.ainvoke(
        _initial_state(thread_id, "do the thing"), config=config, durability="sync"
    )
    assert "__interrupt__" in first
    second = await graph.ainvoke(Command(resume="a1"), config=config, durability="sync")
    assert "__interrupt__" in second
    third = await graph.ainvoke(Command(resume="a2"), config=config, durability="sync")

    assert "__interrupt__" not in third
    assert third["error"] is None
    assert len(analyzer_calls) == 3
    # Phase 3: assumption_stated is now at state level, not in result
    assumption = third.get("assumption_stated")
    assert isinstance(assumption, str) and assumption
