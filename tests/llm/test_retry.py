"""Unit tests for llm/retry.py — call_structured()'s tenacity-wrapped retry
behavior.

No network calls: a fake client with a mocked
`.chat.completions.parse` async method. `asyncio.sleep` is monkeypatched to
a no-op (matching graph/build.py's established test convention) so retry
backoff doesn't slow down the suite.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APITimeoutError, RateLimitError

from algorunner.config import settings
from algorunner.llm.retry import call_structured


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)


def _timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APITimeoutError(request=request)


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def _make_client(side_effect: list) -> MagicMock:
    client = MagicMock()
    client.chat.completions.parse = AsyncMock(side_effect=side_effect)
    return client


async def test_call_structured_retries_timeout_then_succeeds():
    success = object()
    client = _make_client(
        [_timeout_error(), _timeout_error(), _timeout_error(), _timeout_error(), success]
    )

    result = await call_structured(client, model="gpt-5-mini")

    assert result is success
    assert client.chat.completions.parse.call_count == 5


async def test_call_structured_reraises_original_exception_after_exhausting_retries():
    client = _make_client([_timeout_error()] * settings.retry_max_attempts)

    with pytest.raises(APITimeoutError):
        await call_structured(client, model="gpt-5-mini")

    assert client.chat.completions.parse.call_count == settings.retry_max_attempts


async def test_call_structured_retries_rate_limit_then_succeeds():
    success = object()
    client = _make_client([_rate_limit_error(), success])

    result = await call_structured(client, model="gpt-5-mini")

    assert result is success
    assert client.chat.completions.parse.call_count == 2


async def test_call_structured_does_not_retry_non_retryable_exception():
    client = _make_client([ValueError("boom")])

    with pytest.raises(ValueError):
        await call_structured(client, model="gpt-5-mini")

    assert client.chat.completions.parse.call_count == 1
