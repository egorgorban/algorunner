import redis.asyncio
from starlette.requests import HTTPConnection
from psycopg_pool import AsyncConnectionPool


async def get_pg_pool(conn: HTTPConnection) -> AsyncConnectionPool:
    return conn.app.state.pg_pool


async def get_redis(conn: HTTPConnection) -> redis.asyncio.Redis:
    return conn.app.state.redis
