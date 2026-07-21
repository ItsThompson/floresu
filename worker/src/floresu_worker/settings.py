"""Embedding-worker settings, sourced from the environment once.

The worker is a thin arq worker: it drains the embed queue on Redis, reads an
item's text and writes its vector back over the backend internal API, and calls
the embedding provider in between. Its config is the union of those three hops:
the Redis URL (the arq broker, shared with the backend), the backend internal
base URL plus the shared internal-API token (the trusted hop), and the OpenAI
credentials (the provider). The model + dimension are pinned in the provider, not
configured here (changing them is a backend migration).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Compose/CD inject real env vars, which win over env_file. The host inner loop
# may launch the worker from worker/, so anchor the shared root .env from here.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

SERVICE = "floresu-worker"


class EnvSettings(BaseSettings):
    """Deployment config for the worker, sourced from the environment.

    Field names mirror the shared ``.env`` keys. Unknown keys are ignored so the
    single sectioned root ``.env`` can carry vars for other consumers.
    """

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    # The arq broker, shared with the backend deployment.
    redis_url: str = "redis://localhost:6379/0"
    # Backend internal app base (app-net, e.g. http://backend:8001). The worker
    # reads item text and writes vectors back here with the trusted headers.
    backend_internal_url: str = "http://localhost:8001"
    # Shared secret the internal app requires; empty fails the hop closed.
    internal_api_token: SecretStr = SecretStr("")
    # OpenAI credentials for the embedding provider. Empty in dev lets the worker
    # boot; a real embed then fails and the job retries.
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com"
    # Port the worker exposes its Prometheus metrics on for scraping. A
    # non-positive value disables the exposition server.
    worker_metrics_port: int = 9100


class WorkerSettings(BaseModel):
    """Full, immutable settings for the worker process."""

    service: str
    environment: str
    log_level: str
    redis_url: str
    backend_internal_url: str
    internal_api_token: SecretStr
    openai_api_key: SecretStr
    openai_base_url: str
    worker_metrics_port: int

    @property
    def is_dev(self) -> bool:
        return self.environment.lower() == "development"


def build_worker_settings(env: EnvSettings | None = None) -> WorkerSettings:
    """Compose the worker settings from deployment config."""
    env = env or EnvSettings()
    return WorkerSettings(
        service=SERVICE,
        environment=env.environment,
        log_level=env.log_level,
        redis_url=env.redis_url,
        backend_internal_url=env.backend_internal_url,
        internal_api_token=env.internal_api_token,
        openai_api_key=env.openai_api_key,
        openai_base_url=env.openai_base_url,
        worker_metrics_port=env.worker_metrics_port,
    )
