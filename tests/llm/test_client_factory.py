"""Unit tests for llm/client_factory.py — get_client() lru_cache identity and
model_for() per-agent model resolution.

No network calls, no real Postgres/Redis: pure monkeypatching against
algorunner.config.settings.
"""

from algorunner import config as config_module
from algorunner.llm.client_factory import get_client, model_for


def test_get_client_returns_same_instance_on_second_call():
    first = get_client()
    second = get_client()
    assert first is second


def test_model_for_returns_override_when_set(monkeypatch):
    monkeypatch.setattr(config_module.settings, "problem_analyzer_model", "gpt-5")
    assert model_for("problem_analyzer") == "gpt-5"


def test_model_for_falls_back_to_default_when_override_unset(monkeypatch):
    monkeypatch.setattr(config_module.settings, "problem_analyzer_model", None)
    assert model_for("problem_analyzer") == config_module.settings.default_model


def test_model_for_falls_back_to_default_for_unknown_agent(monkeypatch):
    assert model_for("totally_unknown_agent") == config_module.settings.default_model
