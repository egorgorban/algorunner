"""WebSocket endpoint for real-time task status streaming (API-04, API-05).

Pattern 3 (RESEARCH): subscribe -> snapshot -> timestamp-dedupe -> refresh -> close.

A client connecting to WS /api/v1/tasks/{task_id}/events:
1. Subscribes to the Redis Pub/Sub channel FIRST (before any Postgres read)
2. Reads the current snapshot from Postgres
3. Sends the snapshot to the client
4. Forwards only later status events (timestamp > snapshot.updated_at)
5. On terminal/clarification statuses, sends a fresh snapshot and may close (1000)
6. Malformed messages are dropped; the socket stays open for later valid events
7. When the client disconnects, the subscription is released within 2 s

This guarantees:
- D-02: late clients immediately see current state (snapshot first)
- API-05: no lost or duplicate events (subscribe before snapshot, timestamp dedupe)
- No stale events after fresh state (refresh on clarification/terminal)
- Clean disconnection (PUBSUB NUMSUB reaches 0)

Plan 04-02: adds Origin allowlist (close 4403) and connection cap (close 1013) guards.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from psycopg_pool import AsyncConnectionPool
import redis.asyncio

from algorunner.config import settings
from algorunner.realtime.events import (
    SnapshotEvent,
    StatusEvent,
    TERMINAL_STATUSES,
    SNAPSHOT_REFRESH_STATUSES,
    channel_for,
)
from algorunner.storage.tasks import get_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tasks", tags=["events"])

# Module-level counter for active WebSocket connections (Phase 04 API-04 T-04-02-03).
# Only touched on the event loop, so no lock is needed.
_active_connections = 0


@router.websocket("/{task_id}/events")
async def task_events(
    websocket: WebSocket,
    task_id: UUID,
) -> None:
    """Stream task status events in real-time.

    Plan 04-02 Guards (before accept):
    1. If ws_allowed_origins is non-empty and the Origin header is present and not in the list,
       close with 4403 ("origin not allowed") before accepting.
    2. If _active_connections >= ws_max_connections, close with 1013 ("try again later") before accepting.
    3. An absent Origin header is allowed (non-browser clients don't send one; cross-site hijacking is browser-only).

    Then:
    1. Accept the WebSocket connection
    2. Subscribe to the Redis channel BEFORE reading the snapshot (critical race-condition safety)
    3. Read and send the snapshot
    4. Forward status events with timestamp dedupe
    5. Refresh snapshot on clarification/terminal, then close on terminal

    Connection slot is released in finally block to ensure cleanup on every exit path.
    """
    global _active_connections

    # Phase 04 API-04 WebSocket guards (T-04-02-02/03): check both before accepting

    # Guard 1: Origin allowlist (T-04-02-02)
    if settings.ws_allowed_origins:  # Non-empty list = enforce allowlist
        origin = websocket.headers.get("origin")
        if origin and origin not in settings.ws_allowed_origins:
            # Origin is present and not allowed: close with 4403 and return
            try:
                await websocket.close(code=4403, reason="origin not allowed")
            except Exception:
                pass
            return

    # Guard 2: Connection cap (T-04-02-03)
    if _active_connections >= settings.ws_max_connections:
        # At or over limit: close with 1013 and return
        try:
            await websocket.close(code=1013, reason="try again later")
        except Exception:
            pass
        return

    # Both guards passed: accept and increment the counter
    await websocket.accept()
    _active_connections += 1

    try:
        # Get pool and redis from app state (WebSocket routes don't support Depends injection)
        pool: AsyncConnectionPool = websocket.app.state.pg_pool
        redis_client: redis.asyncio.Redis = websocket.app.state.redis

        # Subscribe FIRST, before any Postgres read (Pattern 3: avoid race between snapshot and first event)
        async with redis_client.pubsub(ignore_subscribe_messages=True) as pubsub:
            await pubsub.subscribe(channel_for(task_id))

            # Now read the snapshot (subscribe is active, so no events are lost)
            task = await get_task(pool, task_id)

            # Unknown task_id: close with 4404
            if task is None:
                await websocket.close(code=4404, reason="task not found")
                return

            # Send the initial snapshot
            snapshot = SnapshotEvent(task=task)
            try:
                await websocket.send_text(snapshot.model_dump_json())
            except Exception as e:
                logger.warning(f"Failed to send snapshot to client: {type(e).__name__}")
                return

            # If the task is already terminal, close after snapshot
            if task.status in TERMINAL_STATUSES:
                try:
                    await websocket.close(code=1000)
                except Exception:
                    pass
                return

            # Track the latest timestamp to deduplicate events
            last_ts: datetime = task.updated_at

            async def forward():
                """Forward status events from Redis, with deduplication and refresh."""
                nonlocal last_ts

                while True:
                    try:
                        message = await pubsub.get_message(timeout=None)
                    except Exception as e:
                        logger.warning(f"Redis subscription error: {type(e).__name__}")
                        return

                    if message is None:
                        # Timeout reached (shouldn't happen with timeout=None, but be safe)
                        continue

                    # Skip subscribe/unsubscribe messages
                    if message["type"] != "message":
                        continue

                    # Validate and parse the message
                    try:
                        event = StatusEvent.model_validate_json(message["data"])
                    except Exception as e:
                        logger.warning(f"Malformed status event on channel: {type(e).__name__}")
                        continue

                    # Deduplicate: drop events that are not newer than what we've already sent
                    if event.timestamp <= last_ts:
                        continue

                    last_ts = event.timestamp

                    # Send the status event to the client
                    try:
                        await websocket.send_text(event.model_dump_json())
                    except Exception as e:
                        logger.warning(f"Failed to send status event to client: {type(e).__name__}")
                        return

                    # On clarification/terminal statuses, send a fresh snapshot
                    if event.status in SNAPSHOT_REFRESH_STATUSES:
                        # Re-read the task from Postgres to get the updated question/result/error
                        task_refreshed = await get_task(pool, task_id)
                        if task_refreshed:
                            fresh_snapshot = SnapshotEvent(task=task_refreshed)
                            try:
                                await websocket.send_text(fresh_snapshot.model_dump_json())
                            except Exception as e:
                                logger.warning(
                                    f"Failed to send refresh snapshot to client: {type(e).__name__}"
                                )
                                return

                        # On terminal status, close with 1000
                        if event.status in TERMINAL_STATUSES:
                            try:
                                await websocket.close(code=1000)
                            except Exception:
                                pass
                            return

            async def drain_client():
                """Receive and ignore client frames; exit on disconnect."""
                try:
                    while True:
                        await websocket.receive_text()
                except WebSocketDisconnect:
                    pass

            # Run forward and drain_client concurrently; stop on first completion
            try:
                forward_task = asyncio.create_task(forward())
                drain_task = asyncio.create_task(drain_client())
                done, pending = await asyncio.wait(
                    [forward_task, drain_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel pending tasks
                for task_to_cancel in pending:
                    task_to_cancel.cancel()

                # Gather results to see if any non-disconnect errors occurred
                for done_task in done:
                    try:
                        await done_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.warning(
                            f"Relay error (closing with 1011): {type(e).__name__}: {e}"
                        )
                        try:
                            await websocket.close(code=1011, reason="internal error")
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Relay setup error: {type(e).__name__}: {e}")
                try:
                    await websocket.close(code=1011, reason="internal error")
                except Exception:
                    pass
    finally:
        # Decrement connection counter on every exit path (finally ensures cleanup)
        _active_connections -= 1
