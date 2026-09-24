"""Application configuration, loaded from environment variables.

The same code runs unmodified on the host (against docker-compose-exposed
ports) and inside the api/worker containers (which override these env vars
with the postgres/redis service DNS names).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://algorunner:algorunner@localhost:5432/algorunner"
    redis_url: str = "redis://localhost:6379"
    # Artifact storage endpoint (S3-compatible). Empty string disables persistence
    # and yields artifacts_incomplete=true in the result. Compose sets
    # http://garage:3900 for the worker.
    garage_endpoint: str = ""
    garage_access_key_id: str = ""
    garage_secret_access_key: str = ""
    garage_bucket: str = "algorunner-artifacts"
    garage_region: str = "garage"
    artifact_write_timeout_s: float = 10.0

    # Required secret, no default (Pitfall 12) — Settings() must fail loudly
    # at construction time when unset, not defer the failure to the first
    # LLM call.
    openai_api_key: str

    # Per-agent model overrides — None means "use default_model" (model_for()
    # in llm/client_factory.py owns the fallback lookup).
    default_model: str = "gpt-5-mini"
    problem_analyzer_model: str | None = None
    solution_strategist_model: str | None = None
    solver_model: str | None = None
    code_generator_model: str | None = None
    test_generator_model: str | None = None
    reviewer_model: str | None = None

    max_iterations: int = 5
    clarification_round_cap: int = 2
    test_generator_min_tests: int = 10
    global_timeout_s: int = 600

    retry_max_attempts: int = 5
    retry_wait_min_s: float = 2.0
    retry_wait_max_s: float = 30.0


settings = Settings()
