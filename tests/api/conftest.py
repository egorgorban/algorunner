"""Test fixtures for API tests.

The live_server fixture runs a real uvicorn server on the test event loop,
avoiding the Starlette TestClient's separate loop (Pitfall 3). This allows
real WebSocket and Pub/Sub testing against the same event loop where the
Redis subscription blocks.
"""

import asyncio
import socket

import pytest
import pytest_asyncio
import redis.asyncio
import uvicorn
from psycopg_pool import AsyncConnectionPool

from algorunner.api.main import app
from algorunner.config import settings


@pytest_asyncio.fixture
async def live_server(pg_pool: AsyncConnectionPool):
    """Run a real uvicorn server on the test loop with shared pg_pool and redis.

    Yields the base URL (e.g., "ws://127.0.0.1:12345").
    """
    # Find a free port
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Set app state (bypass lifespan, same as app_client fixture)
    app.state.pg_pool = pg_pool
    app.state.redis = redis.asyncio.Redis.from_url(settings.redis_url)

    # Create and start the server
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        lifespan="off",  # Don't run lifespan; we manage state manually
        log_level="error",  # Suppress uvicorn logs
    )
    server = uvicorn.Server(config)

    # Run server on the same event loop
    server_task = asyncio.create_task(server.serve())

    # Wait for server to start
    while not server.started:
        await asyncio.sleep(0.01)

    base_url = f"ws://127.0.0.1:{port}"

    yield base_url

    # Shutdown
    server.should_exit = True
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except asyncio.TimeoutError:
        pass

    await app.state.redis.aclose()
