"""Tests for the Redis Pub/Sub publisher (Pattern 1, never-raise)."""

from datetime import datetime
from uuid import uuid4

import pytest
import redis.asyncio

from algorunner.config import settings
from algorunner.realtime.events import StatusEvent, channel_for
from algorunner.realtime.publisher import publish_status, get_publisher_redis
from algorunner.schemas.task import TaskStatus


@pytest.mark.asyncio
async def test_publish_status_delivers_to_redis():
    """publish_status delivers a valid StatusEvent to the Redis channel."""
    task_id = uuid4()
    status = TaskStatus.ANALYZING_PROBLEM
    timestamp = datetime.utcnow()

    # Subscribe with a separate client to receive the message
    subscriber = redis.asyncio.Redis.from_url(settings.redis_url)
    channel = channel_for(task_id)

    async with subscriber.pubsub() as pubsub:
        await pubsub.subscribe(channel)

        # Publish the status
        await publish_status(task_id, status, timestamp)

        # Receive the message
        message = await pubsub.get_message(timeout=1.0)
        while message is None or message["type"] != "message":
            message = await pubsub.get_message(timeout=0.1)

        # Validate the message
        event = StatusEvent.model_validate_json(message["data"])
        assert event.status == status
        assert event.timestamp == timestamp

    await subscriber.aclose()


@pytest.mark.asyncio
async def test_publish_status_swallows_redis_exception(monkeypatch):
    """publish_status catches Exception and never raises (never-raise pattern)."""
    task_id = uuid4()
    status = TaskStatus.ANALYZING_PROBLEM
    timestamp = datetime.utcnow()

    # Patch the publisher to raise an exception
    async def mock_redis_from_url(*args, **kwargs):
        class MockClient:
            async def publish(self, *args, **kwargs):
                raise redis.asyncio.ConnectionError("Redis offline")

        return MockClient()

    monkeypatch.setattr(
        "algorunner.realtime.publisher.redis.asyncio.Redis.from_url",
        mock_redis_from_url,
    )

    # Clear the lru_cache
    get_publisher_redis.cache_clear()

    # publish_status should not raise
    await publish_status(task_id, status, timestamp)

    # Reset the cache for other tests
    get_publisher_redis.cache_clear()


@pytest.mark.asyncio
async def test_publisher_redis_cached():
    """get_publisher_redis returns a cached instance."""
    client1 = get_publisher_redis()
    client2 = get_publisher_redis()
    assert client1 is client2

    get_publisher_redis.cache_clear()
