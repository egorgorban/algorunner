from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.agents.solver.node import SolverOutput, solver_node
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.solution import Approach, ApproachList


def _base_state(**overrides) -> dict:
    state = {
        "task_id": "test-task",
        "problem_text": "two sum",
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
    state.update(overrides)
    return state


def _fake_client(parsed, refusal=None):
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=refusal))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(parse=AsyncMock(return_value=completion))
        )
    )


def _analysis(**overrides) -> ProblemAnalysis:
    fields = {
        "constraints": ["1 <= n <= 10^4"],
        "input_shape": "list[int], int target",
        "output_shape": "list[int] of two indices",
        "intent": "Find the indices of two numbers that add up to the target",
        "difficulty": "easy",
        "needs_clarification": False,
        "clarification_question": None,
    }
    fields.update(overrides)
    return ProblemAnalysis(**fields)


async def test_solution_strategist_node_returns_tagged_approaches(monkeypatch):
    approaches = ApproachList(
        approaches=[
            Approach(name="Brute force", technique="brute force", summary="Check all pairs."),
            Approach(
                name="Hash map lookup",
                technique="hash map",
                summary="Track complements in a hash map for one pass.",
            ),
        ]
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(approaches))
    state = _base_state(analysis=_analysis())

    update = await solution_strategist_node(state)

    assert len(update["approaches"]) == 2
    assert update["approaches"][0].technique == "brute force"
    assert update["approaches"][1].technique == "hash map"


async def test_solution_strategist_node_raises_on_empty_approaches(monkeypatch):
    empty = ApproachList(approaches=[])
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(empty))
    state = _base_state(analysis=_analysis())

    with pytest.raises(ValueError, match="zero approaches"):
        await solution_strategist_node(state)


async def test_solver_node_returns_algorithm_and_complexity(monkeypatch):
    solver_output = SolverOutput(
        algorithm="Iterate once, tracking complements in a hash map.",
        complexity_time="O(n), one pass with O(1) hash map lookups.",
        complexity_space="O(n), the hash map holds up to n entries.",
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: _fake_client(solver_output))
    approach = Approach(name="Hash map lookup", technique="hash map", summary="One pass.")
    state = _base_state(analysis=_analysis(), approaches=[approach])

    update = await solver_node(state)

    result = update["solver_output"]
    assert result["approach"] == approach
    assert result["algorithm"]
    assert result["complexity_time"]
    assert result["complexity_space"]
