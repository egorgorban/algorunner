from fastapi import Request
from psycopg_pool import AsyncConnectionPool


async def get_pg_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pg_pool
