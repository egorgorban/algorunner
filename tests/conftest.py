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
    """Dispatcher-based mock for Phase 3 multi-approach pipeline (Pitfall 4).

    Dispatches on `kwargs["response_format"].__name__` to support both
    per-approach branches and shared analysis. The canned ApproachList has
    TWO approaches: index 0 is "Brute force pairs" and index 1 is "Hash map lookup".

    SolverOutput and CodeGenOutput vary by approach (detected from message content).
    ProblemAnalysis, GeneratedTests, and ReviewResult are shared across approaches.

    Exposes on the returned fake client:
    - default_dispatch: the async dispatch function (for test wrappers)
    - calls: list of response_format names in call order
    - canned: dict from response_format name to the shared parsed object
    - canned_code: dict from approach name to CodeGenOutput
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

    approaches_list = ApproachList(
        approaches=[
            Approach(
                name="Brute force pairs",
                technique="brute force",
                summary="Check every pair of indices.",
                role="brute_force",
                rationale="Provides an instructive baseline approach.",
            ),
            Approach(
                name="Hash map lookup",
                technique="hash map",
                summary="Track complements in a hash map for one pass.",
                role="optimized",
                rationale="Achieves O(n) time with a single pass.",
            ),
        ]
    )

    # Brute force approach: nested loops
    brute_force_solver = SolverOutput(
        algorithm="Iterate with two nested loops over indices to find a pair summing to target.",
        complexity_time="O(n^2), two nested loops over the array.",
        complexity_space="O(1), only loop indices are stored.",
    )
    brute_force_code = CodeGenOutput(
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
            "    for i in range(len(nums)):\n"
            "        for j in range(i + 1, len(nums)):\n"
            "            if nums[i] + nums[j] == target:\n"
            "                return [i, j]\n"
            "    return []\n"
        ),
        code_go=(
            "package main\n\n"
            "func twoSum(nums []int, target int) []int {\n"
            "\tfor i := 0; i < len(nums); i++ {\n"
            "\t\tfor j := i + 1; j < len(nums); j++ {\n"
            "\t\t\tif nums[i]+nums[j] == target {\n"
            "\t\t\t\treturn []int{i, j}\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\t}\n"
            "\treturn nil\n"
            "}\n"
        ),
    )

    # Hash map approach
    hash_map_solver = SolverOutput(
        algorithm="Iterate once, tracking complements of each value in a hash map.",
        complexity_time="O(n), one pass with O(1) average hash map lookups.",
        complexity_space="O(n), the hash map holds up to n entries.",
    )
    hash_map_code = CodeGenOutput(
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

    # Ten labelled cases, shared across both approaches
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

    # Track calls for test inspection
    calls_list = []

    async def dispatch(**kwargs) -> SimpleNamespace:
        """Dispatcher that returns different responses based on response_format name.

        Tracks calls in calls_list[]. Detects approach from message content
        for SolverOutput/CodeGenOutput.
        """
        response_format = kwargs.get("response_format")
        format_name = response_format.__name__ if response_format else "unknown"
        calls_list.append(format_name)

        if format_name == "ProblemAnalysis":
            return _completion(analysis)
        elif format_name == "ApproachList":
            return _completion(approaches_list)
        elif format_name == "SolverOutput":
            # Detect approach from message content
            messages = kwargs.get("messages", [])
            content = ""
            for msg in messages:
                if isinstance(msg, dict):
                    content += msg.get("content", "")
            if "Brute force pairs" in content:
                return _completion(brute_force_solver)
            else:
                return _completion(hash_map_solver)
        elif format_name == "CodeGenOutput":
            # Detect approach from message content
            messages = kwargs.get("messages", [])
            content = ""
            for msg in messages:
                if isinstance(msg, dict):
                    content += msg.get("content", "")
            if "Brute force pairs" in content:
                return _completion(brute_force_code)
            else:
                return _completion(hash_map_code)
        elif format_name == "GeneratedTests":
            return _completion(generated_tests)
        elif format_name == "ReviewResult":
            return _completion(passing_review)
        else:
            raise ValueError(f"Unexpected response_format: {format_name}")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                parse=AsyncMock(side_effect=dispatch)
            )
        )
    )

    # Expose for test access
    fake_client.default_dispatch = dispatch
    fake_client.calls = calls_list
    fake_client.canned = {
        "ProblemAnalysis": analysis,
        "ApproachList": approaches_list,
        "GeneratedTests": generated_tests,
        "ReviewResult": passing_review,
    }
    fake_client.canned_code = {
        "Brute force pairs": brute_force_code,
        "Hash map lookup": hash_map_code,
    }

    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)
    return fake_client
