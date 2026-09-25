"""Pydantic contracts for WebSocket real-time status events (D-02, D-03, D-05).

A client connected to WS /api/v1/tasks/{task_id}/events receives:
1. One SnapshotEvent with the current task state (status, result/error/clarification_question if any)
2. One StatusEvent per later status write to that task
3. A fresh SnapshotEvent on terminal or clarification-refresh statuses
4. Close code 1000 on terminal status

Events are validated and deduplicated by timestamp; out-of-order or duplicate
events are dropped. The `updated_at` field from the database write ensures
timestamp order agrees with commit order.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from algorunner.schemas.task import TaskRecord, TaskStatus


def channel_for(task_id: UUID | str) -> str:
    """Return the Redis Pub/Sub channel name for status events on a task (D-05)."""
    return f"task:{task_id}:status"


# Status values that trigger a snapshot refresh and close (D-02, D-04).
TERMINAL_STATUSES = frozenset([TaskStatus.COMPLETED, TaskStatus.FAILED])
SNAPSHOT_REFRESH_STATUSES = frozenset(
    [TaskStatus.AWAITING_CLARIFICATION, TaskStatus.COMPLETED, TaskStatus.FAILED]
)


class StatusEvent(BaseModel):
    """A status transition on a task (D-03 + type discriminator)."""

    type: Literal["status"] = "status"
    status: TaskStatus
    timestamp: datetime


class SnapshotEvent(BaseModel):
    """Current task state snapshot (D-02)."""

    type: Literal["snapshot"] = "snapshot"
    task: TaskRecord
