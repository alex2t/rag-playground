"""GET and POST /api/prompts (T36): the Prompt page lists versions with their runs and saves new ones. No network."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from test_runs import STACK_B

from rag_playground import main, store
from rag_playground.rag import prompts, runs
from rag_playground.settings import settings

client = TestClient(main.app)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    connection = store.connect()
    yield connection
    connection.close()


def save(name="strict", text="Answer only from the context."):
    return client.post("/api/prompts", json={"name": name, "text": text})


def listed() -> dict:
    return {version["name"]: version for version in client.get("/api/prompts").json()}


def test_a_new_database_lists_the_default_version(conn):
    assert client.get("/api/prompts").json() == [
        {"name": "default", "text": prompts.DEFAULT_TEXT, "sha256": prompts.sha256(prompts.DEFAULT_TEXT), "runs": []}]


def test_saving_returns_and_stores_the_version_exactly_as_written(conn):
    text = "  Line one.\n\nLine two.  "
    response = save(text=text)
    assert response.status_code == 201
    assert response.json() == {"name": "strict", "text": text, "sha256": prompts.sha256(text)}
    assert prompts.get(conn, "strict").text == text


def test_versions_are_listed_oldest_first(conn):
    save("second")
    save("third")
    assert list(listed()) == ["default", "second", "third"]


def test_a_taken_name_is_refused_and_the_old_text_is_kept(conn):
    save(text="First text.")
    response = save(text="Changed text.")
    assert response.status_code == 409 and "'strict' already exists" in response.json()["detail"]
    assert prompts.get(conn, "strict").text == "First text."


def test_the_default_name_cannot_be_taken_on_a_new_database(conn):
    """Saved first, another text under its name would make ensure_default fail for good, stopping every ladder step."""
    response = save("default", "Another text.")
    assert response.status_code == 409
    assert prompts.ensure_default(conn).text == prompts.DEFAULT_TEXT


@pytest.mark.parametrize("name", ["", "   ", " v1", "v1 ", "v1\nv2", "\n", "v1\n", "\nv1", "v1\r", "v1\rv2",
                                  " v1", "v1 ", " "])
def test_a_blank_or_lookalike_name_is_refused(conn, name):
    assert save(name=name).status_code == 422
    assert prompts.list_all(conn) == []


@pytest.mark.parametrize("name", ["a,b", ",", ",v1", "v1,", "strict v2, short"])
def test_a_name_with_a_comma_is_refused_since_s6_could_never_choose_it(conn, name):
    assert save(name=name).status_code == 422
    assert prompts.list_all(conn) == []


@pytest.mark.parametrize("text", ["", " ", " \n\t "])
def test_a_blank_text_is_refused(conn, text):
    assert save(text=text).status_code == 422
    assert prompts.list_all(conn) == []


@pytest.mark.parametrize("name", ["v1", "a", "strict v2", "prompt-3_b.1"])
def test_ordinary_names_are_accepted(conn, name):
    assert save(name=name).status_code == 201


@pytest.mark.parametrize("body", [
    {"name": "v1"}, {"text": "Text."}, {"name": 1, "text": "Text."}, {"name": "v1", "text": None},
    {"name": "v1", "text": "Text.", "sha256": "forged"},
])
def test_a_malformed_request_is_refused(conn, body):
    assert client.post("/api/prompts", json=body).status_code == 422
    assert prompts.list_all(conn) == []


def test_each_version_lists_only_the_runs_that_used_it(conn):
    default = prompts.ensure_default(conn)
    strict = prompts.save(conn, "strict", "Answer only from the context.")
    prompts.save(conn, "unused", "Never run.")
    first = runs.create_run(conn, replace(STACK_B, prompt_name="default", prompt_sha256=default.sha256))
    second = runs.create_run(conn, replace(STACK_B, stack="A", openai_ranking={"ranker": "auto"}, split="heldout",
                                           prompt_name="strict", prompt_sha256=strict.sha256))
    third = runs.create_run(conn, replace(STACK_B, top_k=2, prompt_name="strict", prompt_sha256=strict.sha256))
    runs.finish_run(conn, third, "Budget reached")
    versions = listed()
    created = {run: runs.get_run(conn, run).created_at for run in (first, second, third)}
    assert versions["default"]["runs"] == [
        {"id": first, "stack": "B", "split": "dev", "status": "running", "created_at": created[first]}]
    assert versions["strict"]["runs"] == [
        {"id": second, "stack": "A", "split": "heldout", "status": "running", "created_at": created[second]},
        {"id": third, "stack": "B", "split": "dev", "status": "failed", "created_at": created[third]}]
    assert versions["unused"]["runs"] == []


@pytest.mark.parametrize("call", [lambda: client.get("/api/prompts"), save])
def test_a_changed_default_text_is_reported_with_its_reason(conn, monkeypatch, call):
    prompts.ensure_default(conn)
    monkeypatch.setattr(prompts, "DEFAULT_TEXT", "Edited default.")
    response = call()
    assert response.status_code == 409 and "differs from DEFAULT_TEXT" in response.json()["detail"]
    assert [version.name for version in prompts.list_all(conn)] == ["default"]
