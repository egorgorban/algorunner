from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import taskiq_fastapi
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from algorunner.api.routes.config import router as config_router
from algorunner.api.routes.tasks import router as tasks_router
from algorunner.storage.migrate import run_migrations_with_lock
from algorunner.storage.postgres import get_pool
from algorunner.worker.broker import broker

# T-01-03 (DoS): reject request bodies over this size before Pydantic
# body-parsing ever runs — client -> API is the primary trust boundary,
# ASVS L1 requires mitigation (not just acceptance) for this medium-severity
# threat.
MAX_BODY_BYTES = 100_000


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_pool()
    await pool.open()
    app.state.pg_pool = pool

    await run_migrations_with_lock(pool)

    taskiq_fastapi.init(broker, "algorunner.api.main:app")

    if not broker.is_worker_process:
        await broker.startup()

    try:
        yield
    finally:
        if not broker.is_worker_process:
            await broker.shutdown()
        await pool.close()


app = FastAPI(title="AlgoRunner", lifespan=lifespan)
app.include_router(config_router)
app.include_router(tasks_router)


@app.middleware("http")
async def limit_body_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # CR-04: count actual streamed bytes rather than trusting Content-Length
    # (absent/malformed on a chunked or deliberately-mislabeled request would
    # otherwise bypass this check entirely). Aborts the read loop the moment
    # the running total exceeds MAX_BODY_BYTES — never buffers a full
    # oversized body in memory.
    body_chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        body_chunks.append(chunk)

    # Re-inject the already-consumed body for downstream Pydantic parsing.
    # Starlette's BaseHTTPMiddleware wraps `request` in a `_CachedRequest`
    # whose `wrapped_receive()` replays `request._body` to the rest of the
    # ASGI chain when set — the same mechanism `Request.body()` uses
    # internally. Setting it here (instead of calling `.body()`, which would
    # re-consume `.stream()` a second time) makes the already-read chunks
    # visible to FastAPI's route handler without buffering twice.
    request._body = b"".join(body_chunks)

    return await call_next(request)
