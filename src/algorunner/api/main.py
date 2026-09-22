from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import taskiq_fastapi
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

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
app.include_router(tasks_router)


@app.middleware("http")
async def limit_body_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413, content={"detail": "Request body too large"}
                )
        except ValueError:
            pass
    return await call_next(request)
