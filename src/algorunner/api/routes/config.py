"""GET /api/config endpoint for frontend runtime configuration (D-20, T-04-02-01).

Serves the frontend with API and WebSocket base URLs, and input/output limits.
All limits are derived from Pydantic schema metadata (MaxLen), so form constraints
sync with server validation automatically.

Never exposes secrets (openai_api_key, garage_secret_access_key, etc.) or any
key containing "secret", "password", or "token".
"""

import annotated_types
from pydantic import BaseModel, Field

from algorunner.config import settings
from algorunner.schemas.clarification import ClarificationAnswer
from algorunner.schemas.task import TaskSubmission
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["config"])


def _get_max_len(model_class: type, field_name: str) -> int:
    """Extract the MaxLen metadata from a Pydantic model field.

    Args:
        model_class: The Pydantic model class
        field_name: The field name to inspect

    Returns:
        The max_length value from the MaxLen metadata

    Raises:
        ValueError if the field has no MaxLen metadata
    """
    field_info = model_class.model_fields[field_name]
    for metadata in field_info.metadata or []:
        if isinstance(metadata, annotated_types.MaxLen):
            return metadata.max_length
    raise ValueError(f"{model_class.__name__}.{field_name} has no MaxLen metadata")


class ClientConfig(BaseModel):
    """Frontend runtime configuration (D-20, safe subset of settings).

    Contains only client-facing values: API/WS URLs and input limits.
    All limits are read from schema metadata at request time.
    """

    api_base_url: str = Field(description="API base URL")
    ws_base_url: str | None = Field(description="WebSocket base URL, or null to derive from browser location")
    max_problem_chars: int = Field(description="Max length of problem_text")
    max_examples: int = Field(description="Max length of examples array")
    max_answer_chars: int = Field(description="Max length of clarification answer")


@router.get("/config", response_model=ClientConfig)
async def get_config() -> ClientConfig:
    """Return frontend configuration with limits derived from schemas.

    GET /api/config (note: outside /api/v1, per D-20)

    Returns:
        ClientConfig with api_base_url, ws_base_url, and three limits read from
        TaskSubmission and ClarificationAnswer field metadata.
    """
    return ClientConfig(
        api_base_url=settings.client_api_base_url,
        ws_base_url=settings.client_ws_base_url,
        max_problem_chars=_get_max_len(TaskSubmission, "problem_text"),
        max_examples=_get_max_len(TaskSubmission, "examples"),
        max_answer_chars=_get_max_len(ClarificationAnswer, "answer"),
    )
