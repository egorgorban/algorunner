"""Hand-rolled numbered-SQL-file migration runner.

Explicitly not Alembic/SQLAlchemy for Phase 1's single-table scope
(RESEARCH.md Architecture Pattern 1). Tracks applied migrations in a
`schema_migrations` table so re-running is idempotent.
"""

import asyncio
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from algorunner.storage.postgres import get_pool

# repo_root/migrations — this file lives at src/algorunner/storage/migrate.py,
# so parents[3] is the repo root (parents[0]=storage, [1]=algorunner, [2]=src).
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

_CREATE_SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def apply_pending_migrations(pool: AsyncConnectionPool) -> list[str]:
    """Apply any *.sql files under MIGRATIONS_DIR not yet recorded as applied.

    Returns the list of newly-applied filenames, in the order applied.
    """
    # Safe to call again on an already-open pool.
    await pool.open()

    async with pool.connection() as conn:
        await conn.execute(_CREATE_SCHEMA_MIGRATIONS_TABLE)

        cur = await conn.execute("SELECT filename FROM schema_migrations")
        applied = {row["filename"] for row in await cur.fetchall()}

        newly_applied: list[str] = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text()
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (path.name,),
            )
            newly_applied.append(path.name)

        return newly_applied


async def _main() -> None:
    pool = get_pool()
    await pool.open()
    try:
        applied = await apply_pending_migrations(pool)
        if applied:
            print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
        else:
            print("No pending migrations.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
