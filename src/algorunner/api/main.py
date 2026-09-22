from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import taskiq_fastapi
from fastapi import FastAPI

from algorunner.api.routes.tasks import router as tasks_router
from algorunner.storage.postgres import get_pool
from algorunner.worker.broker import broker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_pool()
    await pool.open()
    app.state.pg_pool = pool

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
