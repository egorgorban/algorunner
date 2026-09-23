"""Shared PostgreSQL connection pool.

Non-negotiable kwargs (RESEARCH.md Pitfall 1 / CLAUDE.md "What NOT to Use"):
autocommit=True and row_factory=dict_row. Omitting either causes silent
checkpoint-persistence failure or a TypeError on the first checkpoint read.
This same pool (or a class_row(TaskRecord)-shaped cursor over it) backs both
the LangGraph checkpointer and storage/tasks.py's task CRUD — never
construct a second, bare psycopg.connect() for either purpose.

WR-01 (01-REVIEW.md): `get_pool()` is memoized with `functools.lru_cache` so
every caller across the process (worker/broker.py's `_on_worker_startup`,
worker/tasks.py, api/main.py's lifespan) shares one `AsyncConnectionPool`
instead of each constructing its own — the process previously held two
independent, unmemoized pools.
"""

from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from algorunner.config import settings


@lru_cache
def get_pool() -> AsyncConnectionPool:
    """Construct (but do not open) the shared, process-wide
    AsyncConnectionPool. Memoized — every call returns the identical
    instance within a process.

    Callers must `await pool.open()` before use (safe to call again on an
    already-open pool).
    """
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
