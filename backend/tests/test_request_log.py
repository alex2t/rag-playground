"""Tests for the JSON request log (D37): one line per request on standard output."""

import json
import logging
import subprocess
import sys

from fastapi.testclient import TestClient

from rag_playground import main
from rag_playground.logs import JsonFormatter

client = TestClient(main.app)

APP_REQUEST = """
from fastapi.testclient import TestClient
from rag_playground.main import app
TestClient(app).get("/api/mode?secret=xyz")
"""


def request_lines(caplog) -> list[dict]:
    return [r.fields for r in caplog.records if r.name == "rag_playground.requests"]


def test_a_request_prints_one_json_line_on_stdout():
    """The real app in a fresh process, as in the container: stdout holds the request as a JSON line."""
    out = subprocess.run([sys.executable, "-c", APP_REQUEST], capture_output=True, text=True, check=True).stdout
    lines = [json.loads(line) for line in out.splitlines()]
    assert len(lines) == 1
    line = lines[0]
    assert line["level"] == "INFO"
    assert line["logger"] == "rag_playground.requests"
    assert line["message"] == "request"
    assert line["method"] == "GET"
    assert line["path"] == "/api/mode"
    assert line["status"] == 200
    assert len(line["request_id"]) == 32
    assert line["latency_ms"] >= 0
    assert line["time"].endswith("+00:00")
    assert "xyz" not in out


def test_the_line_holds_the_status_the_client_got(caplog):
    with caplog.at_level(logging.INFO):
        response = client.get("/api/no-such-route")
    assert response.status_code == 404
    [fields] = request_lines(caplog)
    assert fields["status"] == 404
    assert fields["path"] == "/api/no-such-route"


def test_the_response_carries_the_logged_request_id(caplog):
    with caplog.at_level(logging.INFO):
        response = client.post("/api/sign-in")
    [fields] = request_lines(caplog)
    assert fields["method"] == "POST"
    assert response.headers["X-Request-ID"] == fields["request_id"]


def test_a_client_cannot_choose_the_request_id(caplog):
    with caplog.at_level(logging.INFO):
        response = client.get("/api/mode", headers={"X-Request-ID": "client-chosen"})
    [fields] = request_lines(caplog)
    assert fields["request_id"] != "client-chosen"
    assert response.headers["X-Request-ID"] == fields["request_id"]


def test_each_request_gets_a_new_id(caplog):
    with caplog.at_level(logging.INFO):
        client.get("/api/mode")
        client.get("/api/mode")
    first, second = request_lines(caplog)
    assert first["request_id"] != second["request_id"]


def test_formatter_writes_fields_and_utc_time():
    record = logging.LogRecord("rag_playground.x", logging.WARNING, __file__, 1, "hello %s", ("you",), None)
    record.created = 0.0
    record.fields = {"status": 500}
    assert json.loads(JsonFormatter().format(record)) == {
        "time": "1970-01-01T00:00:00.000+00:00",
        "level": "WARNING",
        "logger": "rag_playground.x",
        "message": "hello you",
        "status": 500,
    }
