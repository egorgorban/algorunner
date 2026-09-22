"""Parameterized Postgres CRUD for the `tasks` table.

Security note (T-01-01): every statement below uses `%s` placeholders only.
Never string-format/f-string `problem_text`/`examples` (or any other
user-controlled value) into SQL.
"""

from uuid import UUID

from psycopg.rows import class_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

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
        await conn.execute(
            "UPDATE tasks SET status = %s, updated_at = now() WHERE id = %s",
            (status.value, task_id),
        )


async def update_task_completed(
    pool: AsyncConnectionPool, task_id: UUID, result: dict
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE tasks
            SET status = %s, result = %s, updated_at = now()
            WHERE id = %s
            """,
            (TaskStatus.COMPLETED.value, Jsonb(result), task_id),
        )


async def update_task_failed(
    pool: AsyncConnectionPool, task_id: UUID, error: TaskError
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE tasks
            SET status = %s, error = %s, updated_at = now()
            WHERE id = %s
            """,
            (TaskStatus.FAILED.value, Jsonb(error.model_dump()), task_id),
        )
