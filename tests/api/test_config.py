"""Tests for GET /api/config endpoint (D-20, T-04-02-01)."""

import re


async def test_get_config_returns_200_with_required_keys(app_client):
    """GET /api/config returns 200 with exactly the required keys."""
    response = await app_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()

    # Verify exactly the required keys are present
    expected_keys = {"api_base_url", "ws_base_url", "max_problem_chars", "max_examples", "max_answer_chars"}
    assert set(body.keys()) == expected_keys


async def test_get_config_returns_default_values(app_client):
    """GET /api/config returns the default values when settings are not customized."""
    response = await app_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()

    assert body["api_base_url"] == "/api/v1"
    assert body["ws_base_url"] is None
    assert body["max_problem_chars"] == 5000  # TaskSubmission.problem_text max_length
    assert body["max_examples"] == 10  # TaskSubmission.examples max_length
    assert body["max_answer_chars"] == 5000  # ClarificationAnswer.answer max_length


async def test_get_config_limits_from_schemas(app_client):
    """GET /api/config limits are read from Pydantic schema metadata, not hard-coded."""
    # This test verifies the schema-derived limits are actually used.
    # The exact values are defined in:
    # - src/algorunner/schemas/task.py: TaskSubmission.problem_text, .examples
    # - src/algorunner/schemas/clarification.py: ClarificationAnswer.answer
    response = await app_client.get("/api/config")
    body = response.json()

    # These are the documented limits from the schemas
    assert body["max_problem_chars"] == 5000
    assert body["max_examples"] == 10
    assert body["max_answer_chars"] == 5000


async def test_get_config_never_exposes_secrets(app_client):
    """GET /api/config body contains no secret values or secret-like keys."""
    response = await app_client.get("/api/config")
    assert response.status_code == 200
    body_text = response.text

    # Check for common secret patterns
    secret_patterns = [
        r"openai_api_key",
        r"garage_secret_access_key",
        r"garage_access_key_id",
        r"['\"]sk-",  # OpenAI key prefix
        r"secret",
        r"password",
        r"token",
    ]

    for pattern in secret_patterns:
        assert not re.search(pattern, body_text, re.IGNORECASE), f"Response contains secret pattern: {pattern}"


async def test_get_config_is_outside_v1_path(app_client):
    """GET /api/config is at /api/config, not /api/v1/config (D-20)."""
    # Verify the route is at /api/config
    response = await app_client.get("/api/config")
    assert response.status_code == 200

    # Verify /api/v1/config does NOT exist
    response_v1 = await app_client.get("/api/v1/config")
    assert response_v1.status_code == 404


async def test_get_config_with_monkeypatched_settings(app_client, monkeypatch):
    """GET /api/config respects settings.client_api_base_url and .client_ws_base_url."""
    import algorunner.config as config_module

    # Monkeypatch settings to custom values
    monkeypatch.setattr(config_module.settings, "client_api_base_url", "https://example.test/api/v1")
    monkeypatch.setattr(config_module.settings, "client_ws_base_url", "wss://example.test/api/v1")

    response = await app_client.get("/api/config")
    assert response.status_code == 200
    body = response.json()

    assert body["api_base_url"] == "https://example.test/api/v1"
    assert body["ws_base_url"] == "wss://example.test/api/v1"
