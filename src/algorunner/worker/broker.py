"""Single instantiation point for the taskiq broker, shared between the API
process (`.kiq()` callers) and the worker process (the listener).

`unacknowledged_lock_timeout` is set explicitly (RESEARCH.md Pitfall 2) —
the taskiq-redis default is None, meaning a crashed worker's claimed-but-
unprocessed message never gets reclaimed via XAUTOCLAIM, and Postgres status
would silently never advance past analyzing_problem. 30_000ms is several
multiples of D-06's 2-5s simulated sleep.
"""

from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from algorunner.config import settings

result_backend = RedisAsyncResultBackend(redis_url=settings.redis_url)

broker = RedisStreamBroker(
    url=settings.redis_url,
    queue_name="algorunner-tasks",
    consumer_group_name="algorunner-workers",
    unacknowledged_lock_timeout=30_000,
).with_result_backend(result_backend)
