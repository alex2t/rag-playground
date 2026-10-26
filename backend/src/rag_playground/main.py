"""FastAPI app: API routes and the built React frontend."""

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from qdrant_client import QdrantClient

from rag_playground.settings import settings

app = FastAPI(title="RAG Playground", version=settings.app_version)
qdrant = QdrantClient(url=settings.qdrant_url, timeout=2)


def qdrant_status() -> str:
    """Return "ok" if Qdrant answers, otherwise the error text."""
    try:
        qdrant.get_collections()
    except Exception as exc:
        return f"error: {type(exc).__name__}"
    return "ok"


@app.get("/api/health")
def health(response: Response) -> dict:
    """Report the app version and whether Qdrant is reachable (D17)."""
    status = qdrant_status()
    if status != "ok":
        response.status_code = 503
    return {"status": "ok" if status == "ok" else "degraded", "version": settings.app_version, "qdrant": status}


if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
