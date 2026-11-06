"""Tests for GET /api/mode and the READ_ONLY setting (D32)."""

import pytest
from fastapi.testclient import TestClient

from rag_playground import main
from rag_playground.settings import Settings, settings

client = TestClient(main.app)


@pytest.mark.parametrize("read_only", [True, False])
def test_mode_reports_the_setting(monkeypatch, read_only):
    monkeypatch.setattr(settings, "read_only", read_only)
    response = client.get("/api/mode")
    assert response.status_code == 200
    assert response.json() == {"read_only": read_only}


def test_read_only_is_off_when_unset(monkeypatch):
    """Compose leaves READ_ONLY absent when Doppler has no value (deploy/docker-compose.yml)."""
    monkeypatch.delenv("READ_ONLY", raising=False)
    assert Settings(_env_file=None).read_only is False


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("1", True), ("false", False), ("0", False)])
def test_read_only_parsed_from_environment(monkeypatch, value, expected):
    monkeypatch.setenv("READ_ONLY", value)
    assert Settings(_env_file=None).read_only is expected


def test_read_only_refuses_an_unclear_value(monkeypatch):
    """A typo in Doppler stops the app at start instead of silently showing the paid buttons."""
    monkeypatch.setenv("READ_ONLY", "ture")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
