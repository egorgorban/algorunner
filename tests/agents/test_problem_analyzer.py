from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.problem_analyzer.node import problem_analyzer_node


def _base_state(problem_text: str) -> dict:
    return {
        "task_id": "test-task",
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


async def test_problem_analyzer_node_returns_parsed_analysis(mock_openai_parse):
    state = _base_state(
        "Given an array of integers, return indices of the two numbers that "
        "add up to a target."
    )

    update = await problem_analyzer_node(state)

    assert update["analysis"] is not None
    assert update["analysis"].difficulty in {"easy", "medium", "hard"}
    assert update["analysis"].needs_clarification is False
    mock_openai_parse.chat.completions.parse.assert_awaited_once()


async def test_problem_analyzer_node_raises_on_refusal(monkeypatch):
    refusal_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=None, refusal="cannot help"))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(parse=AsyncMock(return_value=refusal_completion))
        )
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    state = _base_state("two sum")

    with pytest.raises(ValueError, match="refused or failed to parse"):
        await problem_analyzer_node(state)
