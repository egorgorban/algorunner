from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import algorunner.llm.client_factory as client_factory_module
from algorunner.api.main import app
from algorunner.schemas.problem import ProblemAnalysis
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
