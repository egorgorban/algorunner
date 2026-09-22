from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from algorunner.api.main import app
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
