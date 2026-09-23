from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from psycopg_pool import AsyncConnectionPool

from algorunner.api.dependencies import get_pg_pool
from algorunner.schemas.clarification import ClarificationAnswer, ClarificationQuestion
from algorunner.schemas.task import TaskCreateResponse, TaskRecord, TaskStatus, TaskSubmission
from algorunner.storage.tasks import attempt_consume_clarification, get_task, insert_task
from algorunner.worker.tasks import resume_task_with_clarification, solve_problem

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


@router.get("/{task_id}/clarification", response_model=ClarificationQuestion)
async def get_clarification_question(
    task_id: UUID, pool: AsyncConnectionPool = Depends(get_pg_pool)
) -> ClarificationQuestion:
    task = await get_task(pool, task_id)
    if task is None or task.status != TaskStatus.AWAITING_CLARIFICATION:
        raise HTTPException(status_code=404, detail="No pending clarification for this task")
    return ClarificationQuestion(question=task.clarification_question or "")


@router.post("/{task_id}/clarification", status_code=202, response_model=TaskCreateResponse)
async def answer_clarification(
    task_id: UUID,
    body: ClarificationAnswer,
    pool: AsyncConnectionPool = Depends(get_pg_pool),
) -> TaskCreateResponse:
    # The atomic status transition is the source of truth; enqueue strictly
    # after it succeeds so only one resume can ever be enqueued.
    consumed = await attempt_consume_clarification(pool, task_id)
    if not consumed:
        raise HTTPException(status_code=409, detail="Task is not awaiting clarification")
    await resume_task_with_clarification.kiq(str(task_id), body.answer)
    return TaskCreateResponse(task_id=task_id, status=TaskStatus.ANALYZING_PROBLEM)
