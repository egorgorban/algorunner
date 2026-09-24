"""Tests for artifact storage (Garage/S3)."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from algorunner.storage.artifacts import (
    ArtifactRecorder,
    NoopArtifactStore,
    S3ArtifactStore,
    analysis_key,
    editorial_key,
    get_artifact_store,
    iteration_key,
    sort_artifact_keys,
    summary_key,
)


# Test Models for serialization
class SampleModel(BaseModel):
    text: str
    number: int


# ============================================================================
# Key Builder Tests
# ============================================================================


class TestAnalysisKey:
    """Tests for analysis_key builder."""

    def test_valid_uuid(self):
        """Valid UUID produces correct key."""
        task_id = str(uuid4())
        key = analysis_key(task_id)
        assert key == f"tasks/{task_id}/analysis.json"

    def test_invalid_uuid_raises(self):
        """Invalid UUID raises ValueError."""
        with pytest.raises(ValueError):
            analysis_key("not-a-uuid")

    def test_uuid_variant_raises(self):
        """Non-canonical UUID string (different case/format) raises ValueError."""
        with pytest.raises(ValueError):
            analysis_key("../etc/passwd")


class TestIterationKey:
    """Tests for iteration_key builder."""

    def test_valid_params(self):
        """Valid params produce correct key."""
        task_id = str(uuid4())
        key = iteration_key(task_id, 0, 1, "solution")
        assert key == f"tasks/{task_id}/approaches/0/iter-1/solution.json"

    def test_all_kinds(self):
        """All kinds are supported."""
        task_id = str(uuid4())
        kinds = ["solution", "python_exec", "go_exec", "review"]
        for kind in kinds:
            key = iteration_key(task_id, 0, 1, kind)
            assert kind in key

    def test_distinct_coordinates_yield_distinct_keys(self):
        """Different coordinates never produce the same key."""
        task_id = str(uuid4())
        k1 = iteration_key(task_id, 0, 1, "solution")
        k2 = iteration_key(task_id, 0, 2, "solution")
        k3 = iteration_key(task_id, 1, 1, "solution")
        assert len({k1, k2, k3}) == 3

    def test_invalid_task_id_raises(self):
        """Invalid task_id raises ValueError."""
        with pytest.raises(ValueError):
            iteration_key("not-a-uuid", 0, 1, "solution")

    def test_negative_idx_raises(self):
        """Negative idx raises ValueError."""
        task_id = str(uuid4())
        with pytest.raises(ValueError):
            iteration_key(task_id, -1, 1, "solution")

    def test_n_less_than_1_raises(self):
        """n < 1 raises ValueError."""
        task_id = str(uuid4())
        with pytest.raises(ValueError):
            iteration_key(task_id, 0, 0, "solution")

    def test_invalid_kind_raises(self):
        """Invalid kind raises ValueError."""
        task_id = str(uuid4())
        with pytest.raises(ValueError):
            iteration_key(task_id, 0, 1, "invalid_kind")


class TestSummaryKey:
    """Tests for summary_key builder."""

    def test_valid_params(self):
        """Valid params produce correct key."""
        task_id = str(uuid4())
        key = summary_key(task_id, 0)
        assert key == f"tasks/{task_id}/approaches/0/summary.json"

    def test_invalid_task_id_raises(self):
        """Invalid task_id raises ValueError."""
        with pytest.raises(ValueError):
            summary_key("not-a-uuid", 0)

    def test_negative_idx_raises(self):
        """Negative idx raises ValueError."""
        task_id = str(uuid4())
        with pytest.raises(ValueError):
            summary_key(task_id, -1)


class TestEditorialKey:
    """Tests for editorial_key builder."""

    def test_valid_uuid(self):
        """Valid UUID produces correct key."""
        task_id = str(uuid4())
        key = editorial_key(task_id)
        assert key == f"tasks/{task_id}/editorial.json"

    def test_invalid_uuid_raises(self):
        """Invalid UUID raises ValueError."""
        with pytest.raises(ValueError):
            editorial_key("not-a-uuid")


# ============================================================================
# Key Sorting Tests
# ============================================================================


class TestSortArtifactKeys:
    """Tests for sort_artifact_keys deterministic ordering."""

    def test_analysis_first(self):
        """Analysis key comes first."""
        task_id = str(uuid4())
        keys = [
            editorial_key(task_id),
            analysis_key(task_id),
            iteration_key(task_id, 0, 1, "solution"),
        ]
        sorted_keys = sort_artifact_keys(keys)
        assert sorted_keys[0] == analysis_key(task_id)

    def test_editorial_last(self):
        """Editorial key comes last."""
        task_id = str(uuid4())
        keys = [
            editorial_key(task_id),
            analysis_key(task_id),
            iteration_key(task_id, 0, 1, "solution"),
        ]
        sorted_keys = sort_artifact_keys(keys)
        assert sorted_keys[-1] == editorial_key(task_id)

    def test_iteration_order(self):
        """Iterations ordered by (idx, n, kind)."""
        task_id = str(uuid4())
        keys = [
            iteration_key(task_id, 0, 2, "solution"),
            iteration_key(task_id, 0, 1, "review"),
            iteration_key(task_id, 0, 1, "solution"),
            iteration_key(task_id, 0, 1, "python_exec"),
            iteration_key(task_id, 0, 1, "go_exec"),
        ]
        sorted_keys = sort_artifact_keys(keys)

        # All should be from approach 0
        assert all("approaches/0" in k for k in sorted_keys)

        # Iteration 1 should come before iteration 2
        iter1_keys = [k for k in sorted_keys if "iter-1" in k]
        iter2_keys = [k for k in sorted_keys if "iter-2" in k]
        assert (
            sorted_keys.index(iter1_keys[0])
            < sorted_keys.index(iter2_keys[0])
        )

        # Within iter-1, kind order should be: solution, python_exec, go_exec, review
        iter1_order = [
            k.split("/")[-1].replace(".json", "") for k in iter1_keys
        ]
        assert iter1_order == [
            "solution",
            "python_exec",
            "go_exec",
            "review",
        ]

    def test_approach_order_ascending(self):
        """Approaches ordered by ascending idx."""
        task_id = str(uuid4())
        keys = [
            iteration_key(task_id, 1, 1, "solution"),
            iteration_key(task_id, 0, 1, "solution"),
            summary_key(task_id, 1),
            summary_key(task_id, 0),
        ]
        sorted_keys = sort_artifact_keys(keys)

        # Approach 0 keys should come before approach 1 keys
        app0_indices = [
            i
            for i, k in enumerate(sorted_keys)
            if "/approaches/0/" in k
        ]
        app1_indices = [
            i
            for i, k in enumerate(sorted_keys)
            if "/approaches/1/" in k
        ]
        assert max(app0_indices) < min(app1_indices)

    def test_summary_after_iterations(self):
        """Summary comes after its approach's iterations."""
        task_id = str(uuid4())
        keys = [
            summary_key(task_id, 0),
            iteration_key(task_id, 0, 1, "solution"),
        ]
        sorted_keys = sort_artifact_keys(keys)
        assert sorted_keys.index(iteration_key(task_id, 0, 1, "solution")) < sorted_keys.index(
            summary_key(task_id, 0)
        )


# ============================================================================
# Store Tests
# ============================================================================


class TestNoopArtifactStore:
    """Tests for NoopArtifactStore."""

    @pytest.mark.asyncio
    async def test_put_json_returns_false(self):
        """put_json always returns False."""
        store = NoopArtifactStore()
        result = await store.put_json("key", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_never_raises(self):
        """put_json never raises even with unusual payloads."""
        store = NoopArtifactStore()
        result = await store.put_json("key", None)
        assert result is False


class TestS3ArtifactStore:
    """Tests for S3ArtifactStore."""

    @pytest.mark.asyncio
    async def test_put_json_basemodel_serializes_correctly(self):
        """BaseModel is serialized with model_dump_json."""
        store = S3ArtifactStore(
            endpoint="http://localhost:3900",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
            region="garage",
            write_timeout_s=10,
        )

        model = SampleModel(text="hello", number=42)

        # Mock the client's put_object
        with patch.object(store, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.put_object = MagicMock()

            await store.put_json("key", model)

            # Verify put_object was called with correct body
            call_args = mock_client.put_object.call_args
            assert call_args is not None
            body_bytes = call_args[1]["Body"]
            parsed = json.loads(body_bytes.decode("utf-8"))
            assert parsed == {"text": "hello", "number": 42}

    @pytest.mark.asyncio
    async def test_put_json_dict_serializes_correctly(self):
        """Dict is serialized with json.dumps and ensure_ascii=False."""
        store = S3ArtifactStore(
            endpoint="http://localhost:3900",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
            region="garage",
            write_timeout_s=10,
        )

        payload = {"text": "Привет"}

        with patch.object(store, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.put_object = MagicMock()

            await store.put_json("key", payload)

            # Verify UTF-8 encoding
            call_args = mock_client.put_object.call_args
            body_bytes = call_args[1]["Body"]
            parsed = json.loads(body_bytes.decode("utf-8"))
            assert parsed["text"] == "Привет"

    @pytest.mark.asyncio
    async def test_put_json_timeout_returns_false(self, caplog):
        """Timeout returns False and logs warning."""
        store = S3ArtifactStore(
            endpoint="http://localhost:3900",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
            region="garage",
            write_timeout_s=0.01,  # Very short timeout
        )

        def blocking_put(*args, **kwargs):
            # This will be called in a thread, so we can use time.sleep
            import time
            time.sleep(1)  # Longer than timeout

        with patch.object(store, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.put_object = blocking_put

            with caplog.at_level(logging.WARNING):
                result = await store.put_json("test-key", {})

            assert result is False
            assert "test-key" in caplog.text
            assert "TimeoutError" in caplog.text

    @pytest.mark.asyncio
    async def test_put_json_exception_logs_and_returns_false(self, caplog):
        """Exception logs warning and returns False."""
        store = S3ArtifactStore(
            endpoint="http://localhost:3900",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
            region="garage",
            write_timeout_s=10,
        )

        with patch.object(store, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.put_object.side_effect = RuntimeError("S3 error")

            with caplog.at_level(logging.WARNING):
                result = await store.put_json("test-key", {})

            assert result is False
            # Verify log contains key and exception type but not secret
            assert "test-key" in caplog.text
            assert "RuntimeError" in caplog.text
            # Secret should never be in logs
            assert "secret_access_key" not in caplog.text

    @pytest.mark.asyncio
    async def test_put_json_no_exc_info_in_log(self, caplog):
        """Warning does not include exc_info (traceback)."""
        store = S3ArtifactStore(
            endpoint="http://localhost:3900",
            bucket="test",
            access_key_id="test",
            secret_access_key="test",
            region="garage",
            write_timeout_s=10,
        )

        with patch.object(store, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.put_object.side_effect = RuntimeError("S3 error")

            with caplog.at_level(logging.WARNING):
                await store.put_json("test-key", {})

            # Check that the log record has no exception info
            for record in caplog.records:
                if "artifact write failed" in record.message:
                    assert record.exc_info is None


# ============================================================================
# get_artifact_store Tests
# ============================================================================


class TestGetArtifactStore:
    """Tests for get_artifact_store factory."""

    @pytest.mark.asyncio
    async def test_returns_noop_when_endpoint_empty(self):
        """Returns NoopArtifactStore when garage_endpoint is empty."""
        get_artifact_store.cache_clear()
        with patch(
            "algorunner.storage.artifacts.settings"
        ) as mock_settings:
            mock_settings.garage_endpoint = ""
            store = get_artifact_store()
            assert isinstance(store, NoopArtifactStore)
        get_artifact_store.cache_clear()

    @pytest.mark.asyncio
    async def test_returns_s3_when_endpoint_set(self):
        """Returns S3ArtifactStore when garage_endpoint is set."""
        get_artifact_store.cache_clear()
        with patch(
            "algorunner.storage.artifacts.settings"
        ) as mock_settings:
            mock_settings.garage_endpoint = "http://garage:3900"
            mock_settings.garage_bucket = "test-bucket"
            mock_settings.garage_access_key_id = "key"
            mock_settings.garage_secret_access_key = "secret"
            mock_settings.garage_region = "garage"
            mock_settings.artifact_write_timeout_s = 10.0

            store = get_artifact_store()
            assert isinstance(store, S3ArtifactStore)
        get_artifact_store.cache_clear()

    @pytest.mark.asyncio
    async def test_memoized(self):
        """Same instance returned on multiple calls."""
        get_artifact_store.cache_clear()
        with patch(
            "algorunner.storage.artifacts.settings"
        ) as mock_settings:
            mock_settings.garage_endpoint = "http://garage:3900"
            mock_settings.garage_bucket = "test-bucket"
            mock_settings.garage_access_key_id = "key"
            mock_settings.garage_secret_access_key = "secret"
            mock_settings.garage_region = "garage"
            mock_settings.artifact_write_timeout_s = 10.0

            store1 = get_artifact_store()
            store2 = get_artifact_store()
            assert store1 is store2
        get_artifact_store.cache_clear()


# ============================================================================
# ArtifactRecorder Tests
# ============================================================================


class TestArtifactRecorder:
    """Tests for ArtifactRecorder."""

    @pytest.mark.asyncio
    async def test_records_successful_writes(self):
        """Successful writes are recorded in written_keys."""
        mock_store = AsyncMock()
        mock_store.put_json = AsyncMock(return_value=True)

        recorder = ArtifactRecorder(mock_store)
        await recorder.put_json("key1", {})
        await recorder.put_json("key2", {})

        assert set(recorder.written_keys()) == {"key1", "key2"}
        assert not recorder.any_failed

    @pytest.mark.asyncio
    async def test_excludes_failed_writes(self):
        """Failed writes are excluded from written_keys."""
        mock_store = AsyncMock()

        async def put_side_effect(key, payload):
            return key != "key2"

        mock_store.put_json = AsyncMock(side_effect=put_side_effect)

        recorder = ArtifactRecorder(mock_store)
        await recorder.put_json("key1", {})
        await recorder.put_json("key2", {})
        await recorder.put_json("key3", {})

        assert set(recorder.written_keys()) == {"key1", "key3"}
        assert recorder.any_failed

    @pytest.mark.asyncio
    async def test_handles_exceptions(self):
        """Exceptions are caught and recorded as failures."""
        mock_store = AsyncMock()
        mock_store.put_json = AsyncMock(side_effect=RuntimeError("S3 error"))

        recorder = ArtifactRecorder(mock_store)
        result = await recorder.put_json("key", {})

        assert result is False
        assert recorder.written_keys() == []
        assert recorder.any_failed

    @pytest.mark.asyncio
    async def test_noop_store_records_as_failed(self):
        """NoopArtifactStore results are recorded as failed."""
        store = NoopArtifactStore()
        recorder = ArtifactRecorder(store)

        await recorder.put_json("key1", {})

        assert recorder.written_keys() == []
        assert recorder.any_failed

    @pytest.mark.asyncio
    async def test_written_keys_sorted(self):
        """written_keys returns sorted output."""
        mock_store = AsyncMock()
        mock_store.put_json = AsyncMock(return_value=True)

        task_id = str(uuid4())
        recorder = ArtifactRecorder(mock_store)

        # Add keys in random order
        await recorder.put_json(editorial_key(task_id), {})
        await recorder.put_json(iteration_key(task_id, 0, 1, "solution"), {})
        await recorder.put_json(analysis_key(task_id), {})

        written = recorder.written_keys()
        assert written[0] == analysis_key(task_id)
        assert written[-1] == editorial_key(task_id)


# ============================================================================
# Live Garage Round-Trip Test
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.live
class TestLiveGarageRoundTrip:
    """Live tests against Garage (requires docker compose services running)."""

    async def test_utf8_roundtrip(self):
        """UTF-8 JSON round-trip through live Garage."""
        from algorunner.config import Settings

        # Use Settings to get Garage endpoint
        # For live tests, settings.garage_endpoint should be set
        # (e.g., http://localhost:3900)
        settings_obj = Settings()

        if not settings_obj.garage_endpoint:
            pytest.skip("GARAGE_ENDPOINT not configured")

        # Use compose dev defaults if not overridden
        access_key = settings_obj.garage_access_key_id or "GK0123456789abcdef01234567"
        secret_key = settings_obj.garage_secret_access_key or (
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        bucket = settings_obj.garage_bucket or "algorunner-artifacts"

        store = S3ArtifactStore(
            endpoint=settings_obj.garage_endpoint,
            bucket=bucket,
            access_key_id=access_key,
            secret_access_key=secret_key,
            region="garage",
            write_timeout_s=10.0,
        )

        payload = {"текст": "Привет, мир"}
        key = "test-utf8-roundtrip.json"

        # Write
        result = await store.put_json(key, payload)
        assert result is True

        # Read back
        import boto3

        s3_client = boto3.client(
            "s3",
            endpoint_url=settings_obj.garage_endpoint,
            region_name="garage",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        parsed = json.loads(body)

        assert parsed == payload

    async def test_idempotent_after_container_recreate(self):
        """Provisioning survives container force-recreation."""
        from algorunner.config import Settings

        settings_obj = Settings()
        if not settings_obj.garage_endpoint:
            pytest.skip("GARAGE_ENDPOINT not configured")

        # This test is meant to be run manually after:
        # docker compose up -d --force-recreate --wait garage
        # It verifies that the bucket/key still exist after recreation
        import boto3

        access_key = settings_obj.garage_access_key_id or "GK0123456789abcdef01234567"
        secret_key = settings_obj.garage_secret_access_key or (
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        bucket = settings_obj.garage_bucket or "algorunner-artifacts"

        s3_client = boto3.client(
            "s3",
            endpoint_url=settings_obj.garage_endpoint,
            region_name="garage",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        # Try to list buckets to ensure provisioning worked
        response = s3_client.list_buckets()
        bucket_names = [b["Name"] for b in response.get("Buckets", [])]
        assert bucket in bucket_names
