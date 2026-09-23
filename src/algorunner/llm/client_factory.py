"""Shared OpenAI client factory and per-agent model resolution.

Mirrors storage/postgres.py's `get_pool()` "construct from settings, one
call site" shape, but uses `functools.lru_cache` (rather than a bare
module-level singleton like worker/broker.py) since the client is cheap to
construct lazily and per-test monkeypatching is easier against a
cached-function than a module-level object.
"""

from functools import lru_cache

from openai import AsyncOpenAI

from algorunner.config import settings


@lru_cache
def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


def model_for(agent_name: str) -> str:
    return getattr(settings, f"{agent_name}_model", None) or settings.default_model
