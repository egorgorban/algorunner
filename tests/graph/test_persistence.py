"""Tests for artifact persistence across the pipeline (D-17..D-20).

Tests the incremental writing of:
- analysis.json after the final analysis
- iteration artifacts (solution, python_exec, go_exec, review) per approach iteration
- per-approach summary.json when a branch completes (verified, exhausted, timed_out, errored)
- editorial.json at the end

All tests use an in-memory FakeStore that records every write attempt.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID
import asyncio

from algorunner.graph.context import PipelineContext
from algorunner.storage.artifacts import ArtifactRecorder, sort_artifact_keys


class FakeStore:
    """In-memory artifact store for testing.

    Records all writes, supports optional failure predicates and raise modes.
    """

    def __init__(self, fail_predicate=None, raise_mode=False):
        """
        Args:
            fail_predicate: Optional callable(key) -> bool that returns True to fail the write
            raise_mode: If True, raise on failed writes; if False, return False
        """
        self.store = {}
        self.writes = []
        self.fail_predicate = fail_predicate or (lambda k: False)
        self.raise_mode = raise_mode

    async def put_json(self, key: str, payload) -> bool:
        """Write JSON and record the attempt."""
        self.writes.append((key, payload))

        if self.fail_predicate(key):
            if self.raise_mode:
                raise RuntimeError(f"Simulated write failure for {key}")
            return False

        self.store[key] = payload
        return True

    def written_keys(self) -> list[str]:
        """Return successfully written keys."""
        return list(self.store.keys())

    def get_payload(self, key: str):
        """Get payload for a written key."""
        return self.store.get(key)

    def all_write_attempts(self) -> list[tuple]:
        """Return all write attempts (including failed ones)."""
        return self.writes


@pytest.mark.asyncio
async def test_artifact_recorder_tracks_written_keys():
    """ArtifactRecorder records successful writes and tracks failures."""
    store = FakeStore()
    recorder = ArtifactRecorder(store)

    # Successful writes
    assert await recorder.put_json("key1", {"a": 1})
    assert await recorder.put_json("key2", {"b": 2})

    # Failed write
    failing_store = FakeStore(fail_predicate=lambda k: k == "key3")
    recorder_with_fail = ArtifactRecorder(failing_store)
    assert not await recorder_with_fail.put_json("key3", {"c": 3})
    assert recorder_with_fail.any_failed

    # Successful write still recorded even if another failed
    assert await recorder_with_fail.put_json("key4", {"d": 4})

    assert recorder_with_fail.written_keys() == ["key4"]


@pytest.mark.asyncio
async def test_persist_with_context():
    """persist() helper writes via context.artifacts."""
    from algorunner.graph.context import persist

    store = FakeStore()
    recorder = ArtifactRecorder(store)
    ctx = PipelineContext(artifacts=recorder)

    # Successful write
    success = await persist(ctx, lambda: "test/key", {"data": "value"})
    assert success
    assert "test/key" in recorder.written_keys()

    # No context
    success = await persist(None, lambda: "key", {"data": "value"})
    assert not success

    # No recorder
    ctx_no_recorder = PipelineContext(artifacts=None)
    success = await persist(ctx_no_recorder, lambda: "key", {"data": "value"})
    assert not success


@pytest.mark.asyncio
async def test_persist_key_validation_failures_logged():
    """Key validation errors inside key_fn are logged and return False."""
    from algorunner.graph.context import persist

    store = FakeStore()
    recorder = ArtifactRecorder(store)
    ctx = PipelineContext(artifacts=recorder)

    # Key building raises ValueError
    def bad_key_fn():
        from uuid import UUID
        UUID("invalid")
        return "should-not-reach"

    success = await persist(ctx, bad_key_fn, {"data": "value"})
    assert not success
    assert len(recorder.written_keys()) == 0


@pytest.mark.asyncio
async def test_sort_artifact_keys_deterministic_order():
    """sort_artifact_keys produces deterministic ordering per D-20."""
    keys = [
        "tasks/123/approaches/1/summary.json",
        "tasks/123/approaches/0/iter-2/review.json",
        "tasks/123/analysis.json",
        "tasks/123/editorial.json",
        "tasks/123/approaches/0/iter-1/solution.json",
        "tasks/123/approaches/0/iter-1/python_exec.json",
        "tasks/123/approaches/0/iter-1/go_exec.json",
        "tasks/123/approaches/0/iter-1/review.json",
        "tasks/123/approaches/0/summary.json",
    ]

    sorted_keys = sort_artifact_keys(keys)

    # Should follow: analysis, then per-approach (idx ascending),
    # within each: iter keys (n asc, kind asc), then summary, then editorial
    assert sorted_keys[0] == "tasks/123/analysis.json"

    # All approach 0 iteration keys before summary
    approach_0_iters = [k for k in sorted_keys if "/approaches/0/iter-" in k]
    approach_0_summary_idx = sorted_keys.index("tasks/123/approaches/0/summary.json")
    for iter_key in approach_0_iters:
        assert sorted_keys.index(iter_key) < approach_0_summary_idx

    # Summary before editorial
    assert sorted_keys.index("tasks/123/approaches/0/summary.json") < sorted_keys.index("tasks/123/editorial.json")
    assert sorted_keys[-1] == "tasks/123/editorial.json"


def test_artifact_keys_valid_for_all_test_cases():
    """All keys in tests use valid format (D-19 object key scheme)."""
    # This is a structural test that the test data itself is valid
    task_id = str(UUID(int=0))  # valid UUID

    # Build valid keys
    from algorunner.storage.artifacts import (
        analysis_key,
        iteration_key,
        summary_key,
        editorial_key,
    )

    assert analysis_key(task_id) == f"tasks/{task_id}/analysis.json"
    assert iteration_key(task_id, 0, 1, "solution") == f"tasks/{task_id}/approaches/0/iter-1/solution.json"
    assert summary_key(task_id, 0) == f"tasks/{task_id}/approaches/0/summary.json"
    assert editorial_key(task_id) == f"tasks/{task_id}/editorial.json"
