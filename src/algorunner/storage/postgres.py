"""Shared PostgreSQL connection pool.

Non-negotiable kwargs (RESEARCH.md Pitfall 1 / CLAUDE.md "What NOT to Use"):
autocommit=True and row_factory=dict_row. Omitting either causes silent
checkpoint-persistence failure or a TypeError on the first checkpoint read.
This same pool (or a class_row(TaskRecord)-shaped cursor over it) backs both
the LangGraph checkpointer (later plan) and storage/tasks.py's task CRUD —
never construct a second, bare psycopg.connect() for either purpose.
"""

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from algorunner.config import settings


def get_pool() -> AsyncConnectionPool:
    """Construct (but do not open) a shared AsyncConnectionPool.

    Callers must `await pool.open()` before use.
    """
    return AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
