"""At most one chunk per document (decision.md T59): the pure rule, the shared search path, the request, the stored
setting and its upgrade, and the reports and lookups that must tell it apart."""

import sqlite3
from dataclasses import replace

import pytest
from pydantic import ValidationError
from test_api_runs import B as RUN_B, client, stack_a, start  # noqa: F401  (stack_a is a fixture)
from test_ask import A, B, asking, post  # noqa: F401  (asking is a fixture)
from test_best_run import META, conn, store_run  # noqa: F401  (conn is a fixture)
from test_jobs import world  # noqa: F401  (world is a fixture)

from rag_playground import store
from rag_playground.rag import evaluation, pipeline, prompts, runs
from rag_playground.rag.ladder import baseline
from rag_playground.rag.ladder_runs import finder
from rag_playground.rag.per_document import limit_per_document
from rag_playground.run_requests import RunRequest
from rag_playground.settings import RERANK_CANDIDATES
from rag_playground.stacks import qdrant_store
from rag_playground.stacks.hits import Hit


def hits(*sources: str) -> list[Hit]:
    return [Hit(f"c{rank}", source, 1.0 / rank, f"t{rank}") for rank, source in enumerate(sources, 1)]


def ids(kept: list[Hit]) -> list[str]:
    return [hit.chunk_id for hit in kept]


def test_keeps_the_first_chunk_of_each_document_in_rank_order():
    assert ids(limit_per_document(hits("a", "a", "b", "a", "c"), 3, 1)) == ["c1", "c3", "c5"]


def test_stops_at_k_chunks():
    assert ids(limit_per_document(hits("a", "b", "c", "d"), 2, 1)) == ["c1", "c2"]


def test_keeps_fewer_than_k_when_the_candidates_hold_fewer_documents():
    assert ids(limit_per_document(hits("a", "a", "b", "b"), 4, 1)) == ["c1", "c3"]


def test_a_limit_of_two_keeps_two_chunks_of_a_document():
    assert ids(limit_per_document(hits("a", "a", "a", "b"), 3, 2)) == ["c1", "c2", "c4"]


def searching(sources: list[str]):
    asked = []

    def retrieve(question, k):
        asked.append(k)
        return hits(*sources)[:k]

    return asked, retrieve


@pytest.fixture
def answering(monkeypatch):
    monkeypatch.setattr(pipeline, "answer", lambda model, prompt, question, kept: "reply")


def test_the_limit_searches_the_candidates_and_keeps_one_chunk_per_document(answering):
    asked, retrieve = searching(["a", "a", "b", "c"] + ["d"] * 20)
    done = pipeline.search_and_answer("Q?", 2, None, "m", None, retrieve, per_doc_limit=1)
    assert asked == [RERANK_CANDIDATES]
    assert ids(done.hits) == ["c1", "c3"]


def test_without_the_limit_search_asks_for_top_k_only(answering):
    asked, retrieve = searching(["a", "a", "b"])
    done = pipeline.search_and_answer("Q?", 2, None, "m", None, retrieve)
    assert asked == [2]
    assert ids(done.hits) == ["c1", "c2"]


def test_ask_applies_the_limit_and_pays_one_search_fee(asking, stack_a, monkeypatch):
    monkeypatch.setattr(pipeline, "rerank", lambda *args: pytest.fail("no reranker with the limit"))
    reply = post({**A, "per_doc_limit": 1, "question": "Who?"}).json()
    assert stack_a == [("vs_1", RERANK_CANDIDATES, stack_a[0][2])]
    assert [c["source"] for c in reply["chunks"]] == ["d.md"]


def test_ask_on_stack_b_reads_one_chunk_of_each_document(asking, monkeypatch):
    monkeypatch.setattr(qdrant_store, "search", lambda q, name, question, k, hybrid: hits("a.md", "a.md", "b.md")[:k])
    reply = post({**B, "per_doc_limit": 1, "question": "Who?"}).json()
    assert [c["source"] for c in reply["chunks"]] == ["a.md", "b.md"]


@pytest.mark.parametrize("change, problem", [
    ({"per_doc_limit": 2}, "per_doc_limit"), ({"per_doc_limit": 0}, "per_doc_limit"),
    ({"per_doc_limit": "1"}, "per_doc_limit"), ({"per_doc_limit": True}, "per_doc_limit"),
    ({"per_doc_limit": 1, "rerank": True}, "cannot be limited with reranking on")])
def test_a_request_with_an_invalid_limit_is_refused(change, problem):
    with pytest.raises(ValidationError, match=problem):
        RunRequest.model_validate({**RUN_B, **change})


def test_the_limit_must_be_stated():
    with pytest.raises(ValidationError, match="per_doc_limit"):
        RunRequest.model_validate({k: v for k, v in RUN_B.items() if k != "per_doc_limit"})


@pytest.mark.parametrize("limit", [None, 1])
def test_a_valid_limit_reaches_the_pipeline(limit):
    assert RunRequest.model_validate({**RUN_B, "per_doc_limit": limit}).choices().per_doc_limit == limit


def test_the_api_refuses_the_limit_with_the_reranker_and_stores_nothing(world):
    response = client.post("/api/runs", json={**RUN_B, "per_doc_limit": 1, "rerank": True})
    assert response.status_code == 422 and "cannot be limited with reranking on" in response.text
    assert world["conn"].execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_a_run_stores_the_limit_and_every_question_reads_one_chunk_per_document(world, monkeypatch):
    asked = []

    def search(q, name, question, k, hybrid):
        asked.append(k)
        return hits("a.md", "a.md", "b.md")[:k]

    monkeypatch.setattr(qdrant_store, "search", search)
    job = client.get(f"/api/jobs/{start({**RUN_B, 'per_doc_limit': 1}).json()['job_id']}").json()
    assert job["status"] == "done"
    assert runs.get_run(world["conn"], job["run_id"]).meta.per_doc_limit == 1
    results = runs.get_results(world["conn"], job["run_id"])
    assert len(results) == 20 and set(asked) == {RERANK_CANDIDATES}
    assert {tuple(hit.source for hit in r.hits) for r in results} == {("a.md", "b.md")}


LIMITED = replace(META, per_doc_limit=1)


def test_a_run_stores_its_limit_and_reads_it_back(conn):
    assert runs.get_run(conn, store_run(conn, meta=LIMITED)).meta.per_doc_limit == 1
    assert runs.get_run(conn, store_run(conn)).meta.per_doc_limit is None


def test_the_database_refuses_the_limit_with_a_reranker(conn):
    with pytest.raises(sqlite3.IntegrityError, match="per_doc_limit"):
        runs.create_run(conn, replace(LIMITED, rerank_model="m", rerank_slug="s", rerank_candidates=20))


def test_the_database_refuses_a_limit_below_one(conn):
    with pytest.raises(sqlite3.IntegrityError, match="per_doc_limit"):
        runs.create_run(conn, replace(META, per_doc_limit=0))


def test_a_stored_limit_never_changes(conn):
    """Finishing the run is allowed, so only the settings trigger can refuse this update."""
    run_id = runs.create_run(conn, META)
    with pytest.raises(sqlite3.IntegrityError, match="run settings are permanent"), conn:
        conn.execute("UPDATE runs SET status = 'failed', error = 'x', per_doc_limit = 1 WHERE id = ?", (run_id,))


def test_the_report_states_the_limit():
    assert evaluation.settings_of(LIMITED)["per_doc_limit"] == 1
    assert evaluation.settings_of(META)["per_doc_limit"] is None


def test_a_limited_run_is_not_a_ladder_configuration(conn):
    store_run(conn, meta=LIMITED)
    assert finder(conn, "B")(baseline(prompts.DEFAULT_NAME)) is None


def make_old_database(path, with_per_doc_limit: bool = False):
    """A database as it was before T60 (and before T59 unless `with_per_doc_limit`): the later columns dropped, the
    settings trigger as it was then, one run. Columns go newest first, since a CHECK may read an older column."""
    conn = store.connect(path)
    prompts.ensure_default(conn)
    trigger = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'runs_settings_fixed'").fetchone()[0]
    conn.execute("DROP TRIGGER runs_settings_fixed")
    gone = ["decompose_slug", "decompose_model"] + ([] if with_per_doc_limit else ["per_doc_limit"])
    for column in gone:
        conn.execute(f"ALTER TABLE runs DROP COLUMN {column}")
    for column in ("searches", "sub_questions"):
        conn.execute(f"ALTER TABLE results DROP COLUMN {column}")
    kept = ", per_doc_limit" if with_per_doc_limit else ""
    conn.execute(trigger.replace(", per_doc_limit, decompose_model, decompose_slug ON runs", f"{kept} ON runs"))
    old_meta = {k: v for k, v in runs.asdict(META).items() if k not in gone}
    runs.insert(conn, "runs", old_meta | {"test_ids": runs.json.dumps(META.test_ids)})
    conn.commit()
    conn.close()


def test_an_old_database_gains_the_column_with_earlier_runs_as_no_limit(tmp_path):
    make_old_database(tmp_path / "old.db")
    conn = store.connect(tmp_path / "old.db")
    assert runs.get_run(conn, 1).meta.per_doc_limit is None
    with pytest.raises(sqlite3.IntegrityError, match="run settings are permanent"), conn:
        conn.execute("UPDATE runs SET status = 'failed', error = 'x', per_doc_limit = 1 WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="per_doc_limit"):
        runs.create_run(conn, replace(LIMITED, rerank_model="m", rerank_slug="s", rerank_candidates=20))


def test_a_second_connection_does_not_upgrade_again(tmp_path):
    make_old_database(tmp_path / "old.db")
    store.connect(tmp_path / "old.db").close()
    conn = store.connect(tmp_path / "old.db")
    assert [r[1] for r in conn.execute("PRAGMA table_info(runs)")].count("per_doc_limit") == 1
