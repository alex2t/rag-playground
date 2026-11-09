"""Tests for the error log (D37): an unhandled request error and a failed background job are logged with their trace,
on standard output and in `<var_dir>/errors.log`; nothing else goes to the file. Fakes only, no cost."""

import json

import pytest
from fastapi.testclient import TestClient
from test_api_runs import B as RUN_B, start
from test_jobs import world  # noqa: F401  (world is a fixture)
from test_spend_log import written  # noqa: F401  (written is a fixture)

from rag_playground import main
from rag_playground.settings import settings

client = TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def var(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    return tmp_path


@pytest.fixture
def broken_health(monkeypatch):
    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "qdrant_status", broken)


def error_file(var) -> list[dict]:
    return [json.loads(line) for line in (var / "errors.log").read_text(encoding="utf-8").splitlines()]


def test_an_unhandled_request_error_is_written_to_the_error_file_with_its_trace(var, broken_health):
    response = client.get("/api/health?secret=xyz")
    assert (response.status_code, response.text) == (500, "Internal Server Error")
    [line] = error_file(var)
    assert (line["level"], line["logger"], line["message"]) == ("ERROR", "rag_playground.requests", "server error")
    assert (line["method"], line["path"]) == ("GET", "/api/health")
    assert len(line["request_id"]) == 32
    assert line["exception"].startswith("Traceback")
    assert line["exception"].endswith("RuntimeError: boom")
    assert "xyz" not in (var / "errors.log").read_text(encoding="utf-8")


def test_an_unhandled_request_error_also_gets_its_request_line_with_status_500(var, broken_health, written):
    client.get("/api/health")
    error, request = [line for line in written() if line["logger"] == "rag_playground.requests"]
    assert error["message"] == "server error"
    assert (request["message"], request["status"]) == ("request", 500)
    assert request["request_id"] == error["request_id"]
    assert request["latency_ms"] >= 0
    assert "exception" not in request


def test_each_error_is_appended(var, broken_health):
    client.get("/api/health")
    client.get("/api/health")
    first, second = error_file(var)
    assert first["request_id"] != second["request_id"]


def test_a_normal_request_writes_nothing_to_the_error_file(var):
    assert client.get("/api/mode").status_code == 200
    assert not (var / "errors.log").exists()


def test_a_failed_job_is_written_to_the_error_file_with_its_trace(world):
    world["fail"] = 1
    job_id = start(RUN_B).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "failed"
    [line] = error_file(settings.var_dir)
    assert (line["level"], line["logger"], line["message"]) == ("ERROR", "rag_playground.jobs", "job failed")
    assert line["job_id"] == job_id
    assert line["exception"].endswith("RuntimeError: rate limited")
    assert "request_id" not in line
