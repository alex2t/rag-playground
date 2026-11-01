"""FastAPI app: API routes and the built React frontend."""

import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAIError
from qdrant_client.http.exceptions import ApiException

from rag_playground import jobs, store, story
from rag_playground.ask_requests import AskRequest, dev_questions
from rag_playground.calibration_requests import DbId, GradeRequest, OpenCalibration
from rag_playground.prompt_requests import SavePrompt
from rag_playground.rag import ask, compare, evaluation, grading, prompts
from rag_playground.rag.pipeline import BudgetExceeded
from rag_playground.run_requests import RunRequest, panel_options
from rag_playground.scoring.judging import ACCURACY_RUBRIC
from rag_playground.settings import settings
from rag_playground.stacks import qdrant_store
from rag_playground.story_requests import Stack, StoryRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Jobs do not survive a restart (D07): mark the ones a previous process left unfinished as failed."""
    conn = store.connect()
    jobs.recover_interrupted(conn)
    conn.close()
    yield


app = FastAPI(title="RAG Playground", version=settings.app_version, lifespan=lifespan)
SERVICE_ERRORS = (OpenAIError, ApiException)  # both LLM providers use the openai client; Stack B's is Qdrant's


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


@app.post("/api/runs/estimate")
def estimate_run(request: RunRequest) -> dict:
    """A run's questions, cost and time, what is left of the budget; nothing stored. 404 and 422 as POST /api/runs."""
    conn = store.connect()
    try:
        return evaluation.estimate_run(conn, request.choices(), request.tests())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/runs")
def list_runs() -> list[dict]:
    """Every stored run, newest first, with its settings and no scores."""
    conn = store.connect()
    try:
        return evaluation.listing(conn)
    finally:
        conn.close()


@app.get("/api/runs/{run_id}/report")
def run_report(run_id: DbId) -> dict:
    """A finished run's scores; a held-out run reports them overall only. 404 no such run, 422 not finished."""
    conn = store.connect()
    try:
        return evaluation.report(conn, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No run {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/compare")
def compare_runs(before: DbId, after: DbId) -> dict:
    """Two finished runs on the same questions, `after` against `before`. 404 no such run, 422 they cannot be compared."""
    conn = store.connect()
    try:
        return compare.compare(conn, before, after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No run {exc.args[0]}")
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


@app.post("/api/story", status_code=202)
def start_step(request: StoryRequest) -> dict:
    """Start the ladder's next step on one stack (T50) and return its job id. Refused with nothing stored: 404 (unknown
    prompt version), 409 (a step is already running, or over budget), 422 (prompts not chosen, ladder finished)."""
    conn = store.connect()
    try:
        return {"job_id": jobs.submit_step(conn, request.stack, request.prompt_names())}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except (jobs.StepBusy, BudgetExceeded) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.post("/api/story/{stack}/heldout", status_code=202)
def start_heldout(stack: Stack) -> dict:
    """Confirm a stack's finished ladder on the held-out questions (T18). Refused with nothing stored: 409 (a step is
    already running, or over budget), 422 (ladder not finished, or already confirmed)."""
    conn = store.connect()
    try:
        return {"job_id": jobs.submit_heldout(conn, stack)}
    except (jobs.StepBusy, BudgetExceeded) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/story/{stack}")
def story_state(stack: Stack, prompts: Annotated[list[str] | None, Query()] = None) -> dict:
    """A stack's ladder: finished steps with their scores, the next step and its estimate, and the job running now.
    `prompts` previews S6's estimate before the choice is saved; nothing is stored, and chunk sets are free to build."""
    conn = store.connect()
    try:
        return story.state(conn, stack, tuple(prompts) if prompts else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/runs/{run_id}/answers")
def run_answers(run_id: DbId) -> list[dict]:
    """What a finished or failed dev run answered, question by question, lowest accuracy first."""
    conn = store.connect()
    try:
        return story.answers(conn, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No run {run_id}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/panel")
def panel() -> dict:
    """The settings panel's ranges, models and starting values (T35)."""
    return panel_options()


@app.get("/api/ask/questions")
def ask_questions() -> list[dict]:
    """The dev test questions the Ask page may pick from, without their answers."""
    return [{"id": test.id, "category": test.category, "question": test.question} for test in dev_questions()]


@app.post("/api/ask")
def ask_question(request: AskRequest) -> dict:
    """Answer one question with the panel's settings, and judge it if it is a test question (T54). 404 (chunk set not
    indexed, unknown prompt or question), 409 (over budget, or the stored default prompt changed), 422 (invalid
    settings, before this runs), 502 (OpenAI, OpenRouter or Qdrant failed). Anything else is a bug: a plain 500."""
    conn = store.connect()
    try:
        test = request.test()
        return ask.ask(conn, request.choices(), test.question if test else request.question, test)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {exc.args[0]}")
    except (BudgetExceeded, prompts.DefaultChanged) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SERVICE_ERRORS as exc:
        raise HTTPException(status_code=502, detail=f"The question failed: {type(exc).__name__}: {exc}")
    finally:
        conn.close()


@app.get("/api/prompts")
def list_prompts() -> list[dict]:
    """Every system prompt version with the runs that used it (T36). The default is saved on first use. 409 if the
    stored default differs from the code's text."""
    conn = store.connect()
    try:
        prompts.ensure_default(conn)
        return prompts.with_runs(conn)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    finally:
        conn.close()


@app.post("/api/prompts", status_code=201)
def save_prompt(request: SavePrompt) -> dict:
    """Save a new version (T36); a saved version never changes. The default is saved first, so its name can never be
    taken by another text. 409 if the name is taken or the stored default differs from the code's text, 422 if the name
    or text is invalid."""
    conn = store.connect()
    try:
        prompts.ensure_default(conn)
        return asdict(prompts.save(conn, request.name, request.text))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"A version named '{request.name}' already exists.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
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
