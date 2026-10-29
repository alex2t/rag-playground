"""FastAPI app: API routes and the built React frontend."""

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from rag_playground import jobs, store
from rag_playground.rag.pipeline import BudgetExceeded
from rag_playground.run_requests import RunRequest
from rag_playground.settings import settings
from rag_playground.stacks import qdrant_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Jobs do not survive a restart (D07): mark the ones a previous process left unfinished as failed."""
    conn = store.connect()
    jobs.recover_interrupted(conn)
    conn.close()
    yield


app = FastAPI(title="RAG Playground", version=settings.app_version, lifespan=lifespan)


def qdrant_status() -> str:
    """Return "ok" if Qdrant answers, otherwise the error text."""
    try:
        qdrant_store.client().get_collections()
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


@app.post("/api/runs", status_code=202)
def start_run(request: RunRequest) -> dict:
    """Start an evaluation job and return its id; the UI then polls /api/jobs/{id}. A run that would be refused
    is refused here, with nothing stored: 404 (chunk set not indexed, unknown prompt), 409 (over budget), 422
    (a held-out prompt not evaluated on dev, invalid questions)."""
    conn = store.connect()
    try:
        return {"job_id": jobs.submit_evaluation(conn, request.choices(), request.tests())}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except BudgetExceeded as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: int) -> dict:
    """A background job's status, progress, message and error (D07); the UI polls it."""
    conn = store.connect()
    try:
        return asdict(jobs.get_job(conn, job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    finally:
        conn.close()


if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
