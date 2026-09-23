from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import algorunner.llm.client_factory as client_factory_module
from algorunner.agents.solver.node import SolverOutput
from algorunner.api.main import app
from algorunner.schemas.problem import ProblemAnalysis
from algorunner.schemas.solution import Approach, ApproachList
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
    analyzer -> strategist -> solver graph run (Plan 02-03). All three nodes
    call the same `client_factory.get_client()`, so this fixture drives a
    single fake client's `parse` mock with `side_effect` — one canned
    response per node, in the order the graph actually calls them. Unlike
    `mock_openai_parse` above (analyzer-only, one canned response reused for
    every call — correct for single-node unit tests), a full pipeline
    invocation needs a distinct response per node or the second/third call
    receives the wrong Pydantic type and blows up with an AttributeError."""
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
                name="Hash map lookup",
                technique="hash map",
                summary="Track complements in a hash map for one pass.",
            )
        ]
    )
    solver_output = SolverOutput(
        algorithm="Iterate once, tracking complements of each value in a hash map.",
        complexity_time="O(n), one pass with O(1) average hash map lookups.",
        complexity_space="O(n), the hash map holds up to n entries.",
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
                    ]
                )
            )
        )
    )
    monkeypatch.setattr(client_factory_module, "get_client", lambda: fake_client)
    return fake_client
