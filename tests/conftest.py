import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.code_generator.node import CodeGenOutput
from algorunner.agents.solver.node import SolverOutput
from algorunner.agents.test_generator.node import GeneratedTests, TestCase
from algorunner.api.main import app
from algorunner.schemas.editorial import (
    ApproachProse,
    EditorialDraft,
    UnverifiedMention,
)
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.review import ReviewResult
from algorunner.schemas.solution import Approach, ApproachList, EntryParam, EntryPoint
from algorunner.storage.migrate import apply_pending_migrations
from algorunner.storage.postgres import get_pool


@pytest_asyncio.fixture(scope="session")
async def pg_pool() -> AsyncIterator:
    pool = get_pool()
    await pool.open()
    await apply_pending_migrations(pool)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def app_client(pg_pool) -> AsyncIterator[AsyncClient]:
    # Bypass the FastAPI lifespan (httpx's ASGITransport does not drive the
    # ASGI lifespan protocol) and wire the already-open, migrated pool
    # directly onto app.state, matching what the lifespan would have done.
    app.state.pg_pool = pg_pool
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mock_openai_parse(monkeypatch):
    """Monkeypatches `client_factory.get_client()` to a fake AsyncOpenAI-
    shaped client whose `.chat.completions.parse` is an `AsyncMock` returning
    a canned, successfully-parsed `ProblemAnalysis` — the shape every
    subsequent plan's agent-node unit tests reuse so no real OpenAI call is
    ever made by the test suite.

    Patches the attribute on `algorunner.llm.client_factory` itself (not a
    name imported into a consuming module) — agent nodes call
    `client_factory.get_client()` via the module reference specifically so
    this patch takes effect regardless of import order, mirroring the
    existing `monkeypatch.setattr(<module>.asyncio, "sleep", ...)`
    convention already used in `graph/build.py`/`worker/tasks.py` tests.
    """
    analysis = ProblemAnalysis(
        constraints=["1 <= n <= 10^4"],
        input_shape="list[int], int target",
        output_shape="list[int] of two indices",
        intent="Find the indices of two numbers that add up to the target",
        difficulty="easy",
        needs_clarification=False,
        clarification_question=None,
    )
    canned_completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=analysis, refusal=None))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(parse=AsyncMock(return_value=canned_completion))
        )
    )

    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)
    return fake_client


@pytest.fixture
def mock_pipeline_openai(monkeypatch):
    """Monkeypatches `client_factory.get_client()` for a full
    analyzer -> strategist -> solver -> code_generator -> test_generator
    graph run (Plan 02-03, extended Plan 02-04). All five nodes call the
    same `client_factory.get_client()`, so this fixture drives a single fake
    client's `parse` mock with `side_effect` — one canned response per node,
    in the order the graph actually calls them. Unlike `mock_openai_parse`
    above (analyzer-only, one canned response reused for every call —
    correct for single-node unit tests), a full pipeline invocation needs a
    distinct response per node or a later call receives the wrong Pydantic
    type and blows up with an AttributeError."""
    analysis = ProblemAnalysis(
        constraints=["1 <= n <= 10^4"],
        input_shape="list[int], int target",
        output_shape="list[int] of two indices",
        intent="Find the indices of two numbers that add up to the target",
        difficulty="easy",
        needs_clarification=False,
        clarification_question=None,
    )
    approaches = ApproachList(
        approaches=[
            Approach(
                name="Brute force pairs",
                technique="brute force",
                summary="Check all pairs.",
                role="brute_force",
                rationale="Simple but inefficient baseline.",
            ),
            Approach(
                name="Hash map lookup",
                technique="hash map",
                summary="Track complements in a hash map for one pass.",
                role="optimized",
                rationale="Reduces time complexity with a hash map.",
            ),
        ]
    )
    solver_output = SolverOutput(
        algorithm="Iterate once, tracking complements of each value in a hash map.",
        complexity_time="O(n), one pass with O(1) average hash map lookups.",
        complexity_space="O(n), the hash map holds up to n entries.",
    )
    code_gen_output = CodeGenOutput(
        entry_point=EntryPoint(
            python_name="two_sum",
            go_name="twoSum",
            params=[
                EntryParam(name="nums", type="list[int]"),
                EntryParam(name="target", type="int"),
            ],
            return_type="list[int]",
            unordered_result=True,
        ),
        code_python=(
            "def two_sum(nums, target):\n"
            "    seen = {}\n"
            "    for i, n in enumerate(nums):\n"
            "        if target - n in seen:\n"
            "            return [seen[target - n], i]\n"
            "        seen[n] = i\n"
            "    return []\n"
        ),
        code_go=(
            "package main\n\n"
            "func twoSum(nums []int, target int) []int {\n"
            "\tseen := map[int]int{}\n"
            "\tfor i, n := range nums {\n"
            "\t\tif j, ok := seen[target-n]; ok {\n"
            "\t\t\treturn []int{j, i}\n"
            "\t\t}\n"
            "\t\tseen[n] = i\n"
            "\t}\n"
            "\treturn nil\n"
            "}\n"
        ),
    )
    # Ten labelled cases, each with exactly one solution.
    two_sum_cases = [
        ("classic example", [[2, 7, 11, 15], 9], [0, 1]),
        ("pair in the middle", [[3, 2, 4], 6], [1, 2]),
        ("duplicate values", [[3, 3], 6], [0, 1]),
        ("all negatives", [[-1, -2, -3, -4, -5], -8], [2, 4]),
        ("zeros summing to zero", [[0, 4, 3, 0], 0], [0, 3]),
        ("minimal length", [[1, 5], 6], [0, 1]),
        ("pair at the end", [[5, 75, 25], 100], [1, 2]),
        ("mixed signs", [[-3, 4, 3, 90], 0], [0, 2]),
        ("last two elements", [[1, 2, 3, 4], 7], [2, 3]),
        ("negative element in pair", [[10, -2, 8], 6], [1, 2]),
    ]
    generated_tests = GeneratedTests(
        tests=[
            TestCase(label=label, args_json=json.dumps(args), expected_json=json.dumps(want))
            for label, args, want in two_sum_cases
        ],
        normalized_examples=[],
    )

    # Sixth and final call: the Reviewer (both executions pass for the
    # canned correct Two Sum, so the LLM verdict is consulted and passes).
    passing_review = ReviewResult(
        passed=True,
        issues=[],
        required_changes=[],
        complexity_reasoning="One loop over n items with O(1) dict operations gives O(n) time.",
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
                        _completion(passing_review),
                    ]
                )
            )
        )
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)

    # Store canned EditorialDraft for tests that need it
    editorial_draft = EditorialDraft(
        problem_restatement="Найти два числа в массиве, которые суммируются к целевому значению.",
        approaches=[
            ApproachProse(
                approach_id=0,
                title="Перебор всех пар",
                bridge_from_previous=None,
                intuition="Проверяем все возможные пары.",
                algorithm="Двойной вложенный цикл по массиву.",
                complexity_time="O(n^2)",
                complexity_space="O(1)",
                complexity_justification="Два вложенных цикла.",
                notes=[],
            ),
            ApproachProse(
                approach_id=1,
                title="Хеш-таблица",
                bridge_from_previous="Более эффективно использует дополнение.",
                intuition="Отслеживаем дополнения в хеш-таблице.",
                algorithm="Один проход с хеш-таблицей.",
                complexity_time="O(n)",
                complexity_space="O(n)",
                complexity_justification="Один проход с O(1) хеш-операциями.",
                notes=[],
            ),
        ],
        edge_cases=["Пустой массив", "Массив длины 2"],
        unverified=[],
    )

    def draft_for(ids: list[int]) -> SimpleNamespace:
        """Create a completion with an EditorialDraft containing only the specified approach ids.

        Used by tests where only some approaches are verified (isolation case).
        """
        filtered_approaches = [a for a in editorial_draft.approaches if a.approach_id in ids]
        # Ensure first bridge is None, rest are set
        if filtered_approaches:
            filtered_approaches[0].bridge_from_previous = None
            for approach in filtered_approaches[1:]:
                if approach.bridge_from_previous is None:
                    approach.bridge_from_previous = "Улучшенный подход."

        draft = EditorialDraft(
            problem_restatement=editorial_draft.problem_restatement,
            approaches=filtered_approaches,
            edge_cases=editorial_draft.edge_cases,
            unverified=[],
        )
        return _completion(draft)

    fake_client.editorial_draft = editorial_draft
    fake_client.draft_for = draft_for
    return fake_client
