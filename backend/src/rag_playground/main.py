"""FastAPI app: API routes and the built React frontend."""

import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from rag_playground import jobs, store
from rag_playground.calibration_requests import DbId, GradeRequest, OpenCalibration
from rag_playground.rag import grading
from rag_playground.rag.pipeline import BudgetExceeded
from rag_playground.run_requests import RunRequest
from rag_playground.scoring.judging import ACCURACY_RUBRIC
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
def job_status(job_id: DbId) -> dict:
    """A background job's status, progress, message and error (D07); the UI polls it."""
    conn = store.connect()
    try:
        return asdict(jobs.get_job(conn, job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No job {job_id}")
    finally:
        conn.close()


@app.post("/api/calibration")
def open_calibration(request: OpenCalibration) -> dict:
    """Open the calibration of the two full S0 runs (T48), drawing its fixed sample the first time. 404 if a run does
    not exist, 422 if it is not the full S0 run of its stack."""
    conn = store.connect()
    try:
        return {"calibration_id": grading.open_calibration(conn, request.run_a, request.run_b)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No run {exc.args[0]}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/calibration/{calibration_id}")
def calibration_state(calibration_id: DbId) -> dict:
    """Progress, the next answer to grade (blind) and the score definitions; agreement only once all are graded."""
    conn = store.connect()
    try:
        graded, size = grading.progress(conn, calibration_id)
        item = grading.next_item(conn, calibration_id)
        result = None if item else grading.agreement(conn, calibration_id)
        return {"graded": graded, "size": size, "rubric": ACCURACY_RUBRIC, "item": item and asdict(item),
                "agreement": result and asdict(result) | {"target_reached": result.target_reached}}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No calibration {calibration_id}")
    finally:
        conn.close()


@app.post("/api/calibration/{calibration_id}/grades", status_code=204)
def grade_answer(calibration_id: DbId, request: GradeRequest) -> None:
    """Save the user's grade for one answer. 404 if there is no such answer, 409 if it is already graded: a grade is
    final (T48)."""
    conn = store.connect()
    try:
        grading.save_grade(conn, calibration_id, request.position, request.grade)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No answer {request.position} in calibration {calibration_id}")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    finally:
        conn.close()


if settings.static_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
