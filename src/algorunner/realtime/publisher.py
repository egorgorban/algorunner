"""Redis Pub/Sub publisher for task status events (Pattern 1, Pitfall 8).

Never raises exceptions; failures are logged and execution continues. This
isolation ensures that a Redis outage cannot stall or fail a task or graph node.
Follows the never-raise error handling pattern from graph/context.py emit_status
and storage/artifacts.py put_json.
"""

import logging
from datetime import datetime
from functools import lru_cache
from uuid import UUID

import redis.asyncio

from algorunner.config import settings
from algorunner.realtime.events import StatusEvent, channel_for
from algorunner.schemas.task import TaskStatus

logger = logging.getLogger(__name__)


@lru_cache
def get_publisher_redis() -> redis.asyncio.Redis:
    """Cached Redis client for status publishing (Pitfall 8: short timeouts).

    Short connect and read timeouts prevent an unreachable Redis from stalling
    a worker node. The same client is reused across all status writes in a
    worker process.
    """
    return redis.asyncio.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


async def publish_status(
    task_id: UUID | str, status: TaskStatus, timestamp: datetime
) -> None:
    """Publish a status event to Redis Pub/Sub.

    Catches Exception only; CancelledError still propagates (graph/context.py
    deadline contract). Failures are logged with type(exc).__name__, never raised.

    Args:
        task_id: The task UUID
        status: The new status value
        timestamp: The updated_at from the database write (ensures ordering)
    """
    try:
        event = StatusEvent(status=status, timestamp=timestamp)
        client = get_publisher_redis()
        channel = channel_for(task_id)
        await client.publish(channel, event.model_dump_json())
    except Exception as exc:
        logger.warning(
            f"Failed to publish status {status.value} for task {task_id}: {type(exc).__name__}: {exc}"
        )
