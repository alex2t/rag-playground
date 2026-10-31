"""Step 8 checks of /api/calibration and scripts/grade.py (T48): both are thin layers over rag/grading.py, stay blind to
the judge until the last grade, and refuse a second grade (no network, no cost)."""

import builtins
import importlib.util
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_grading import DATASET, JUDGE_SLUG, META_A, META_B, TESTS, make_run, score_of

from rag_playground import main, store
from rag_playground.rag import grading, prompts
from rag_playground.scoring import judging
from rag_playground.settings import REPO_ROOT, settings

spec = importlib.util.spec_from_file_location("grade", REPO_ROOT / "backend" / "scripts" / "grade.py")
grade_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade_script)

client = TestClient(main.app)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    connection = store.connect()
    prompts.ensure_default(connection)
    monkeypatch.setattr(grading, "load_tests", lambda: TESTS)
    monkeypatch.setattr(grading, "dataset_sha256", lambda: DATASET)
    monkeypatch.setattr(grading, "model_info", lambda model: SimpleNamespace(canonical_slug=JUDGE_SLUG))
    yield connection
    connection.close()


@pytest.fixture
def s0_runs(conn):
    return make_run(conn, META_A), make_run(conn, META_B)


@pytest.fixture
def calibration_id(s0_runs):
    response = client.post("/api/calibration", json={"run_a": s0_runs[0], "run_b": s0_runs[1]})
    assert response.status_code == 200
    return response.json()["calibration_id"]


def judge_scores(conn, calibration_id: int) -> dict[int, int]:
    rows = conn.execute("SELECT position, test_id FROM calibration_items WHERE calibration_id = ?", (calibration_id,))
    return {row["position"]: score_of(row["test_id"]) for row in rows}


def post_grade(calibration_id: int, position, grade):
    return client.post(f"/api/calibration/{calibration_id}/grades", json={"position": position, "grade": grade})


def test_the_first_state_shows_one_answer_and_the_definitions_only(calibration_id):
    state = client.get(f"/api/calibration/{calibration_id}").json()
    assert (state["graded"], state["size"], state["agreement"]) == (0, 30, None)
    assert state["rubric"] == judging.ACCURACY_RUBRIC
    assert set(state["item"]) == {"position", "question", "reference_answer", "answer"}


def test_the_user_and_the_judge_read_the_same_definitions():
    assert judging.ACCURACY_RUBRIC in judging.ANSWER_INSTRUCTIONS


def test_opening_again_gives_the_same_calibration(s0_runs, calibration_id):
    again = client.post("/api/calibration", json={"run_a": s0_runs[0], "run_b": s0_runs[1]})
    assert again.json() == {"calibration_id": calibration_id}


def test_a_run_that_is_not_s0_is_refused_with_the_reason(conn):
    run_a, run_b = make_run(conn, META_B), make_run(conn, META_B)
    response = client.post("/api/calibration", json={"run_a": run_a, "run_b": run_b})
    assert response.status_code == 422 and "stack" in response.json()["detail"]


def test_a_run_that_does_not_exist_is_a_404(conn):
    assert client.post("/api/calibration", json={"run_a": 98, "run_b": 99}).status_code == 404


def test_agreement_appears_only_with_the_last_grade(conn, calibration_id):
    scores = judge_scores(conn, calibration_id)
    for position in range(1, 30):
        assert post_grade(calibration_id, position, scores[position]).status_code == 204
    assert client.get(f"/api/calibration/{calibration_id}").json()["agreement"] is None
    post_grade(calibration_id, 30, scores[30])
    state = client.get(f"/api/calibration/{calibration_id}").json()
    assert (state["graded"], state["item"]) == (30, None)
    assert state["agreement"]["pass_fail"] == 1.0 and state["agreement"]["target_reached"] is True
    assert state["agreement"]["pass_fail_low"] == pytest.approx(0.8865, abs=0.0001)
    agreed = state["agreement"]
    assert (agreed["judge_passed"], agreed["passes_confirmed"], agreed["judge_failed"], agreed["fails_confirmed"]) == (
        12, 12, 18, 18)


def test_a_grade_below_target_is_reported_as_not_reached(calibration_id):
    for position in range(1, 31):
        post_grade(calibration_id, position, 4)
    assert client.get(f"/api/calibration/{calibration_id}").json()["agreement"]["target_reached"] is False


def test_a_second_grade_is_refused_and_the_first_stays(conn, calibration_id):
    post_grade(calibration_id, 1, 4)
    response = post_grade(calibration_id, 1, 5)
    assert response.status_code == 409 and "given once" in response.json()["detail"]
    grade = conn.execute("SELECT grade FROM calibration_items WHERE position = 1").fetchone()["grade"]
    assert grade == 4


@pytest.mark.parametrize("grade", [0, 6, 4.5, "4", True, None])
def test_only_a_whole_score_from_1_to_5_is_accepted(conn, calibration_id, grade):
    assert post_grade(calibration_id, 1, grade).status_code == 422
    assert conn.execute("SELECT count(grade) FROM calibration_items").fetchone()[0] == 0


def test_grading_outside_the_sample_is_a_404(calibration_id):
    assert post_grade(calibration_id, 31, 4).status_code == 404
    assert post_grade(calibration_id + 1, 1, 4).status_code == 404


TOO_BIG = 2**63


@pytest.mark.parametrize("too_big", [TOO_BIG, 10**100])
def test_an_id_too_big_for_the_database_is_refused_not_a_crash(conn, calibration_id, too_big):
    assert client.post("/api/calibration", json={"run_a": too_big, "run_b": 1}).status_code == 422
    assert client.post("/api/calibration", json={"run_a": 1, "run_b": too_big}).status_code == 422
    assert client.get(f"/api/calibration/{too_big}").status_code == 422
    assert client.get(f"/api/jobs/{too_big}").status_code == 422
    assert post_grade(calibration_id, too_big, 4).status_code == 422
    assert post_grade(too_big, 1, 4).status_code == 422


def test_the_largest_stored_id_is_still_a_normal_not_found(conn):
    assert client.get(f"/api/calibration/{TOO_BIG - 1}").status_code == 404


def test_an_id_below_1_is_refused(conn, calibration_id):
    assert post_grade(calibration_id, -1, 4).status_code == 422
    assert post_grade(calibration_id, 0, 4).status_code == 422


def test_an_unknown_calibration_is_a_404(conn):
    assert client.get("/api/calibration/99").status_code == 404


def type_in(monkeypatch, lines: list[str]) -> list[str]:
    """Answer input() with `lines` in order; returns the list of what is left."""
    left = list(lines)
    monkeypatch.setattr(builtins, "input", lambda prompt: left.pop(0))
    return left


def test_the_script_saves_only_confirmed_grades_and_stops_on_request(conn, s0_runs, monkeypatch, capsys):
    left = type_in(monkeypatch, ["9", "4", "n", "3", "y", "q"])
    grade_script.main(*s0_runs)
    assert left == []
    assert [row["grade"] for row in conn.execute("SELECT grade FROM calibration_items WHERE grade IS NOT NULL")] == [3]
    assert "Stopped at 1 of 30." in capsys.readouterr().out


def test_the_script_resumes_and_reports_agreement_after_the_last_grade(conn, s0_runs, monkeypatch, capsys):
    type_in(monkeypatch, ["4", "y", "q"])
    grade_script.main(*s0_runs)
    assert "agreement" not in capsys.readouterr().out.lower()
    type_in(monkeypatch, ["4", "y"] * 29)
    grade_script.main(*s0_runs)
    out = capsys.readouterr().out
    assert "Answer 2 of 30" in out and "Answer 1 of 30" not in out
    assert "Pass/fail agreement: 40% of 30 answers (95% Wilson interval 25% to 58%)" in out
    assert "Within 1 point: 60%" in out and "NOT reached" in out
    assert "Judge passed: you agreed on 12 of 12 (95% Wilson interval 76% to 100%)" in out
    assert "Judge failed: you agreed on 0 of 18 (95% Wilson interval 0% to 18%)" in out


def test_the_script_never_prints_the_judge_or_the_stack(conn, s0_runs, monkeypatch, capsys):
    """The judge's feedback and score labels stay hidden; only the rubric's own word for the scale may appear."""
    type_in(monkeypatch, ["q"])
    grade_script.main(*s0_runs)
    out = capsys.readouterr().out
    item = grading.next_item(conn, 1)
    assert item.question in out and item.reference_answer in out and item.answer in out
    assert judging.ACCURACY_RUBRIC in out
    assert "Stack" not in out and "judge" not in out.lower() and "run" not in out.replace("Run the same", "")
