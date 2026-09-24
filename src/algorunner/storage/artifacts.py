"""Artifact storage to Garage (S3-compatible).

Security notes:
- D-19: Keys are built only from a validated UUID task_id (str(UUID(x)) == x)
  and non-negative integers with a closed kind Literal. No user text reaches
  a key, so there is no path/key injection.
- D-18: Write failures log one warning (key and exception type only, no
  credentials or traceback) and return False instead of raising.
- D-21: No retention/lifecycle policy configured; artifacts are kept forever
  in v1.
- Immutability comes from the key scheme (Garage ignores IfNoneMatch), not
  from object metadata.

Pattern mirrors storage/postgres.py's lru_cache factory convention.
"""

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any, Literal, Protocol
from uuid import UUID

import botocore.config
import botocore.session
from pydantic import BaseModel

from algorunner.config import settings

logger = logging.getLogger(__name__)

ArtifactKind = Literal["solution", "python_exec", "go_exec", "review"]


class ArtifactStore(Protocol):
    """Protocol for artifact persistence."""

    async def put_json(
        self, key: str, payload: BaseModel | dict | list
    ) -> bool:
        """Write a JSON object to the store.

        Returns True on success, False on failure (logged as warning).
        Never raises.
        """
        ...


class NoopArtifactStore:
    """No-op store that always returns False."""

    async def put_json(
        self, key: str, payload: BaseModel | dict | list
    ) -> bool:
        return False


class S3ArtifactStore:
    """S3-compatible artifact store (Garage) using boto3."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        write_timeout_s: float,
    ):
        self.endpoint = endpoint
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.write_timeout_s = write_timeout_s
        self._client = None

    def _get_client(self):
        """Lazily construct the boto3 S3 client."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                region_name=self.region,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                config=botocore.config.Config(
                    s3={"addressing_style": "path"},
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=2,
                    read_timeout=5,
                ),
            )
        return self._client

    async def put_json(
        self, key: str, payload: BaseModel | dict | list
    ) -> bool:
        """Write JSON to S3, bounded by write_timeout_s.

        Returns True on success, False on any failure (logged).
        Never raises.
        """
        try:
            if isinstance(payload, BaseModel):
                body = payload.model_dump_json()
            else:
                body = json.dumps(payload, ensure_ascii=False)

            body_bytes = body.encode("utf-8")

            def _put():
                client = self._get_client()
                client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body_bytes,
                    ContentType="application/json",
                )

            await asyncio.wait_for(
                asyncio.to_thread(_put), timeout=self.write_timeout_s
            )
            return True

        except Exception as exc:
            logger.warning(
                "artifact write failed: %s (%s)", key, type(exc).__name__
            )
            return False


@lru_cache
def get_artifact_store() -> ArtifactStore:
    """Get the configured artifact store.

    Returns NoopArtifactStore when settings.garage_endpoint is empty,
    otherwise S3ArtifactStore. Memoized so each call returns the same
    instance within a process.
    """
    if not settings.garage_endpoint:
        return NoopArtifactStore()

    return S3ArtifactStore(
        endpoint=settings.garage_endpoint,
        bucket=settings.garage_bucket,
        access_key_id=settings.garage_access_key_id,
        secret_access_key=settings.garage_secret_access_key,
        region=settings.garage_region,
        write_timeout_s=settings.artifact_write_timeout_s,
    )


def analysis_key(task_id: str) -> str:
    """Build the key for the analysis artifact.

    Args:
        task_id: UUID string (validated)

    Returns:
        Key path

    Raises:
        ValueError: if task_id is not a valid UUID string
    """
    if str(UUID(task_id)) != task_id:
        raise ValueError(f"Invalid task_id: {task_id}")
    return f"tasks/{task_id}/analysis.json"


def iteration_key(task_id: str, idx: int, n: int, kind: ArtifactKind) -> str:
    """Build the key for an iteration artifact.

    Args:
        task_id: UUID string (validated)
        idx: approach index (>= 0)
        n: iteration number (>= 1)
        kind: artifact kind (solution, python_exec, go_exec, review)

    Returns:
        Key path

    Raises:
        ValueError: if any parameter is invalid
    """
    if str(UUID(task_id)) != task_id:
        raise ValueError(f"Invalid task_id: {task_id}")
    if idx < 0:
        raise ValueError(f"Invalid idx: {idx}")
    if n < 1:
        raise ValueError(f"Invalid n: {n}")
    if kind not in ("solution", "python_exec", "go_exec", "review"):
        raise ValueError(f"Invalid kind: {kind}")

    return f"tasks/{task_id}/approaches/{idx}/iter-{n}/{kind}.json"


def summary_key(task_id: str, idx: int) -> str:
    """Build the key for an approach summary artifact.

    Args:
        task_id: UUID string (validated)
        idx: approach index (>= 0)

    Returns:
        Key path

    Raises:
        ValueError: if any parameter is invalid
    """
    if str(UUID(task_id)) != task_id:
        raise ValueError(f"Invalid task_id: {task_id}")
    if idx < 0:
        raise ValueError(f"Invalid idx: {idx}")

    return f"tasks/{task_id}/approaches/{idx}/summary.json"


def editorial_key(task_id: str) -> str:
    """Build the key for the editorial artifact.

    Args:
        task_id: UUID string (validated)

    Returns:
        Key path

    Raises:
        ValueError: if task_id is not a valid UUID string
    """
    if str(UUID(task_id)) != task_id:
        raise ValueError(f"Invalid task_id: {task_id}")
    return f"tasks/{task_id}/editorial.json"


def sort_artifact_keys(keys: list[str]) -> list[str]:
    """Sort artifact keys in deterministic order.

    Order: analysis key first, then per approach (ascending idx) its
    iteration keys ordered by (n, kind) followed by its summary key,
    then editorial key last. Unknown keys sort last in input order.

    Args:
        keys: list of artifact keys

    Returns:
        Sorted list of keys
    """

    def parse_key(key: str) -> tuple:
        """Parse a key into a sort tuple."""
        if key.endswith("/analysis.json"):
            return (0,)  # analysis first
        elif "/approaches/" in key and "/iter-" in key:
            # iteration key: tasks/{id}/approaches/{idx}/iter-{n}/{kind}.json
            parts = key.split("/")
            if len(parts) >= 6:
                idx = int(parts[3])  # approaches/{idx}
                iter_part = parts[4]  # iter-{n}
                n = int(iter_part.split("-")[1])
                kind = parts[5].replace(".json", "")

                # kind rank for sorting: solution, python_exec, go_exec, review
                kind_rank = {
                    "solution": 0,
                    "python_exec": 1,
                    "go_exec": 2,
                    "review": 3,
                }.get(kind, 4)

                return (1, idx, 0, n, kind_rank)
            return (4, key)  # unknown, sort last in input order
        elif "/approaches/" in key and key.endswith("/summary.json"):
            # summary key: tasks/{id}/approaches/{idx}/summary.json
            parts = key.split("/")
            if len(parts) >= 4:
                idx = int(parts[3])  # approaches/{idx}
                return (1, idx, 1)
            return (4, key)  # unknown
        elif key.endswith("/editorial.json"):
            return (2,)  # editorial last
        else:
            return (4, key)  # unknown, sort last in input order

    return sorted(keys, key=parse_key)


class ArtifactRecorder:
    """Records artifacts written per invocation.

    Tracks which keys were successfully written and whether any writes failed.
    """

    def __init__(self, store: ArtifactStore):
        self.store = store
        self._written_keys: list[str] = []
        self._any_failed = False

    async def put_json(
        self, key: str, payload: BaseModel | dict | list
    ) -> bool:
        """Write JSON via the store and record success/failure.

        Args:
            key: artifact key
            payload: object to serialize

        Returns:
            True if write succeeded (appended to written_keys),
            False if write failed or store raised (recorded as failed).
        """
        try:
            success = await self.store.put_json(key, payload)
            if success:
                self._written_keys.append(key)
            else:
                self._any_failed = True
            return success
        except Exception:
            self._any_failed = True
            return False

    def written_keys(self) -> list[str]:
        """Return successfully written keys, sorted deterministically.

        Returns:
            Sorted list of keys from put_json calls that returned True
        """
        return sort_artifact_keys(self._written_keys)

    @property
    def any_failed(self) -> bool:
        """Whether any put_json call failed or raised.

        Returns:
            True if any write failed, False if all succeeded or no writes
            attempted
        """
        return self._any_failed
