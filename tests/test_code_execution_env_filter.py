"""Tests for code execution environment filtering policy."""

from __future__ import annotations

from integrations.code_execution import CodeExecutionIntegration


def test_clean_env_filters_sensitive_prefixes(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "x")
    monkeypatch.setenv("TOKEN_VALUE", "y")
    monkeypatch.setenv("SECRET_THING", "z")
    monkeypatch.setenv("PATH", "/usr/bin")

    integration = CodeExecutionIntegration()
    env = integration._clean_env()

    assert "API_KEY" not in env
    assert "TOKEN_VALUE" not in env
    assert "SECRET_THING" not in env
    assert "PATH" in env
