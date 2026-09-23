"""WR-01: get_pool() must memoize a single AsyncConnectionPool per process —
the worker process previously held two independent, unmemoized pools
(worker/broker.py's `state.pg_pool` and worker/tasks.py's `_pool`).
"""

from algorunner.storage.postgres import get_pool


def test_get_pool_returns_same_instance_on_second_call():
    first = get_pool()
    second = get_pool()

    assert first is second
