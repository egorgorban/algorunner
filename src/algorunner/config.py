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
    # Unused this phase per D-11 (Garage present in docker-compose but not
    # wired to any client code until Phase 3 / DATA-02).
    garage_endpoint: str = ""


settings = Settings()
