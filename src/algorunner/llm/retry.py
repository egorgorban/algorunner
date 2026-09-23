"""Tenacity-wrapped retry helper for OpenAI structured-output calls.

Scoped narrowly per D-00f: only APITimeoutError/RateLimitError retry here.
A `message.parsed is None` outcome (malformed/refused structured output) is
NOT a transient network condition and must not be retried by this same
mechanism — each agent node inspects `message.parsed` itself after calling
this wrapper.
"""

from openai import APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from algorunner.config import settings


@retry(
    retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
    wait=wait_exponential(
        multiplier=1, min=settings.retry_wait_min_s, max=settings.retry_wait_max_s
    ),
    stop=stop_after_attempt(settings.retry_max_attempts),
    reraise=True,
)
async def call_structured(client, **kwargs):
    return await client.chat.completions.parse(**kwargs)
