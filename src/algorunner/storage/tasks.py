"""Parameterized Postgres CRUD for the `tasks` table.

Security note (T-01-01): every statement below uses `%s` placeholders only.
Never string-format/f-string `problem_text`/`examples` (or any other
user-controlled value) into SQL.

Status writers publish to Redis Pub/Sub after committing to Postgres (Phase 4,
user-resolved write order: D-05, D-01, API-04). Each writer returns updated_at
via RETURNING, then publishes the event after the connection is released back
to the pool.
"""

from uuid import UUID

from psycopg.rows import class_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from algorunner.realtime.publisher import publish_status
from algorunner.schemas.task import TaskError, TaskRecord, TaskStatus, TaskSubmission


async def insert_task(
    pool: AsyncConnectionPool, task_id: UUID, submission: TaskSubmission
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO tasks (id, status, problem_text, language, examples)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                task_id,
                TaskStatus.QUEUED.value,
                submission.problem_text,
                submission.language.value,
                Jsonb([example.model_dump() for example in submission.examples]),
            ),
        )


async def get_task(pool: AsyncConnectionPool, task_id: UUID) -> TaskRecord | None:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
            await cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            return await cur.fetchone()


async def update_task_status(
    pool: AsyncConnectionPool, task_id: UUID, status: TaskStatus
) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = %s, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s
            RETURNING updated_at
            """,
            (status.value, task_id),
        )
        row = await cur.fetchone()

    if row:
        await publish_status(task_id, status, row["updated_at"])


async def update_task_completed(
    pool: AsyncConnectionPool, task_id: UUID, result: dict
) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = %s, result = %s, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s
            RETURNING updated_at
            """,
            (TaskStatus.COMPLETED.value, Jsonb(result), task_id),
        )
        row = await cur.fetchone()

    if row:
        await publish_status(task_id, TaskStatus.COMPLETED, row["updated_at"])


async def update_task_clarification(
    pool: AsyncConnectionPool, task_id: UUID, question: str
) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = %s, clarification_question = %s, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s
            RETURNING updated_at
            """,
            (TaskStatus.AWAITING_CLARIFICATION.value, question, task_id),
        )
        row = await cur.fetchone()

    if row:
        await publish_status(task_id, TaskStatus.AWAITING_CLARIFICATION, row["updated_at"])


async def attempt_consume_clarification(pool: AsyncConnectionPool, task_id: UUID) -> bool:
    """Atomically transition awaiting_clarification -> analyzing_problem.

    Returns True iff this call performed the transition. A missing task, an
    already-resumed task, or a lost race all return False, so exactly one of
    any number of concurrent callers can enqueue the resume. The same UPDATE
    clears the now-answered question so it is never exposed after resume.
    Publishes ANALYZING_PROBLEM status when it wins.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = %s, clarification_question = NULL, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s AND status = %s
            RETURNING updated_at
            """,
            (
                TaskStatus.ANALYZING_PROBLEM.value,
                task_id,
                TaskStatus.AWAITING_CLARIFICATION.value,
            ),
        )
        row = await cur.fetchone()

    if row:
        await publish_status(task_id, TaskStatus.ANALYZING_PROBLEM, row["updated_at"])
        return True
    return False


async def add_active_execution_seconds(
    pool: AsyncConnectionPool, task_id: UUID, delta: float
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE tasks
            SET active_execution_seconds = active_execution_seconds + %s, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s
            """,
            (delta, task_id),
        )


async def update_task_failed(
    pool: AsyncConnectionPool, task_id: UUID, error: TaskError
) -> None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE tasks
            SET status = %s, error = %s, updated_at = GREATEST(clock_timestamp(), updated_at + interval '1 microsecond')
            WHERE id = %s
            RETURNING updated_at
            """,
            (TaskStatus.FAILED.value, Jsonb(error.model_dump()), task_id),
        )
        row = await cur.fetchone()

    if row:
        await publish_status(task_id, TaskStatus.FAILED, row["updated_at"])
