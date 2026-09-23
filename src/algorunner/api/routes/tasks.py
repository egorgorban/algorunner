from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from psycopg_pool import AsyncConnectionPool

from algorunner.api.dependencies import get_pg_pool
from algorunner.schemas.task import TaskCreateResponse, TaskRecord, TaskStatus, TaskSubmission
from algorunner.storage.tasks import get_task, insert_task
from algorunner.worker.tasks import solve_problem

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("", status_code=202, response_model=TaskCreateResponse)
async def create_task(
    body: TaskSubmission, pool: AsyncConnectionPool = Depends(get_pg_pool)
) -> TaskCreateResponse:
    task_id = uuid4()
    # The INSERT must commit before .kiq() is called (Pitfall 3) — with
    # autocommit=True on the pool, insert_task's INSERT is already
    # committed by the time this call returns.
    await insert_task(pool, task_id, body)
    await solve_problem.kiq(str(task_id))
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.QUEUED)


@router.get("/{task_id}", response_model=TaskRecord)
async def get_task_status(
    task_id: UUID, pool: AsyncConnectionPool = Depends(get_pg_pool)
) -> TaskRecord:
    task = await get_task(pool, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
