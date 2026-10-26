"""Tests for GET /api/health (D17)."""

from fastapi.testclient import TestClient

from rag_playground import main

client = TestClient(main.app)


def test_health_ok_when_qdrant_answers(monkeypatch):
    monkeypatch.setattr(main.qdrant, "get_collections", lambda: [])
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "dev", "qdrant": "ok"}


def test_health_503_when_qdrant_unreachable(monkeypatch):
    """No Qdrant listens on port 1, so the real client fails to connect."""
    monkeypatch.setattr(main, "qdrant", main.QdrantClient(url="http://127.0.0.1:1", timeout=1))
    response = client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["version"] == "dev"
    assert body["qdrant"].startswith("error: ")
