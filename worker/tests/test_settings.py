"""Tests for worker settings composition and the metrics helpers."""

from __future__ import annotations

from pydantic import SecretStr

from floresu_worker.metrics import WORKER_REGISTRY, record_job_completed, set_queue_depth
from floresu_worker.settings import SERVICE, EnvSettings, build_worker_settings


def test_build_worker_settings_maps_env_fields() -> None:
    env = EnvSettings(
        environment="production",
        log_level="warning",
        redis_url="redis://broker:6379/1",
        backend_internal_url="http://backend:8001",
        internal_api_token=SecretStr("secret"),
        openai_api_key=SecretStr("sk-x"),
        openai_base_url="https://api.openai.test",
        worker_metrics_port=9200,
    )
    settings = build_worker_settings(env)

    assert settings.service == SERVICE
    assert settings.is_dev is False
    assert settings.redis_url == "redis://broker:6379/1"
    assert settings.backend_internal_url == "http://backend:8001"
    assert settings.internal_api_token.get_secret_value() == "secret"
    assert settings.openai_api_key.get_secret_value() == "sk-x"
    assert settings.worker_metrics_port == 9200


def test_defaults_are_dev_friendly() -> None:
    settings = build_worker_settings(EnvSettings())
    assert settings.is_dev is True
    assert settings.openai_api_key.get_secret_value() == ""
    assert settings.worker_metrics_port == 9100


def test_record_job_completed_increments_by_status() -> None:
    def value() -> float:
        return (
            WORKER_REGISTRY.get_sample_value("embed_jobs_completed_total", {"status": "applied"})
            or 0.0
        )

    before = value()
    record_job_completed("applied")
    assert value() == before + 1.0


def test_set_queue_depth_records_the_gauge() -> None:
    set_queue_depth(42)
    assert WORKER_REGISTRY.get_sample_value("embed_queue_depth") == 42.0
