"""An unreachable OpenRouter model list is a 502 that says so, on every route, never a bare 500 (fix.md 2026-11-03)."""

import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from rag_playground import main
from rag_playground.llm import models

client = TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def no_database(monkeypatch, tmp_path):
    """The routes get an empty in-memory database, never the real one, and errors.log goes to a temporary folder."""
    monkeypatch.setattr(main.store, "connect", lambda: sqlite3.connect(":memory:"))
    monkeypatch.setattr(main.settings, "var_dir", tmp_path)


CERT = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate"


@pytest.fixture
def unreachable(monkeypatch):
    """The model list fetch fails as it did on the dev PC without Norton's certificate."""
    def fail(*args, **kwargs):
        raise httpx.ConnectError(CERT)

    models.model_catalog.cache_clear()
    monkeypatch.setattr(models.httpx, "get", fail)
    yield
    models.model_catalog.cache_clear()


def test_the_model_list_fetch_raises_the_connect_error(unreachable):
    with pytest.raises(httpx.ConnectError):
        models.model_info("openai/gpt-4.1-nano")


@pytest.mark.parametrize("path", ["/api/story/A", "/api/story/B"])
def test_a_route_that_needs_the_model_list_answers_502_with_the_reason(unreachable, monkeypatch, path):
    monkeypatch.setattr(main.story, "state", lambda *args: models.model_info("google/gemini-3.5-flash-lite"))
    response = client.get(path)
    assert response.status_code == 502
    assert response.json() == {"detail": f"Cannot reach OpenRouter's model list: ConnectError: {CERT}"}


def test_other_errors_are_still_a_plain_500(monkeypatch):
    def broken(*args):
        raise RuntimeError("a bug")

    monkeypatch.setattr(main.story, "state", broken)
    response = client.get("/api/story/B")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
