"""Step 6 checks of where chunk sets are indexed and how a run searches its index. Fake stacks record our calls
(no network, no cost); one test indexes and searches for real in Qdrant's in-process mode."""

import sqlite3
from dataclasses import replace

import pytest
from qdrant_client import QdrantClient

from rag_playground import store
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.rag import runs
from rag_playground.stacks import indexes, openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit

SET_ID = "fixed__c1024__o200"
CHUNKS = [Chunk(chunk_id=f"clients/acme.md#{i}", source="clients/acme.md", doc_type="clients", index=i, text=text,
                tokens=8, start=0, end=len(text))
          for i, text in enumerate(["Acme pays 46,250 USD a year.", "Acme was founded in 2011.",
                                    "The office cat is called Pixel."])]
META = runs.RunMeta(
    stack="A", split="dev", test_ids=["q0"], chunk_set_id=SET_ID, top_k=2, hybrid=True,
    openai_ranking={"ranker": "none", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0},
    answer_model="m", answer_slug="m-1", judge_model="j", judge_slug="j-1", rerank_model=None, rerank_slug=None,
    rerank_candidates=None, temperature_controlled=True, prompt_name="default", prompt_sha256="0" * 64,
    dataset_sha256="d" * 64, app_version="dev")


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def stacks(monkeypatch):
    """Fake stack calls; `calls` records them in order. Only SET_ID is a saved chunk set."""
    calls = []

    def load(set_id):
        if set_id != SET_ID:
            raise FileNotFoundError(set_id)
        return CHUNKS

    monkeypatch.setattr(indexes, "load_chunk_set", load)
    monkeypatch.setattr(openai_vector_store, "create_store", lambda name: calls.append(("create", name)) or "vs_1")
    monkeypatch.setattr(openai_vector_store, "upload_chunks", lambda sid, chunks: calls.append(("upload", sid, chunks)))
    monkeypatch.setattr(openai_vector_store, "delete_store", lambda sid: calls.append(("delete", sid)))
    monkeypatch.setattr(qdrant_store, "client", lambda: "qdrant")
    monkeypatch.setattr(qdrant_store, "index_chunks",
                        lambda q, name, chunks: calls.append(("index", q, name, chunks)) or len(chunks))
    return calls


def rows(conn):
    return [tuple(row) for row in conn.execute("SELECT stack, chunk_set_id, ref, chunk_count FROM indexes")]


@pytest.mark.parametrize("hybrid, text_weight", [(False, 0.0), (True, 1.0)])
def test_the_hybrid_switch_maps_to_fixed_openai_ranking(hybrid, text_weight):
    """T40 revision: no built-in ranker, threshold 0; the keyword list counts only with hybrid on."""
    assert openai_vector_store.hybrid_ranking(hybrid) == openai_vector_store.Ranking(
        ranker="none", embedding_weight=1.0, text_weight=text_weight, score_threshold=0.0)


def test_stack_a_uploads_every_chunk_to_a_new_store_and_records_it(conn, stacks):
    assert indexes.build(conn, "A", SET_ID) == "vs_1"
    assert stacks == [("create", f"rag-playground-dev-{SET_ID}"), ("upload", "vs_1", CHUNKS)]
    assert rows(conn) == [("A", SET_ID, "vs_1", 3)]


def test_stack_b_indexes_every_chunk_in_a_collection_named_after_the_chunk_set(conn, stacks):
    assert indexes.build(conn, "B", SET_ID) == SET_ID
    assert stacks == [("index", "qdrant", SET_ID, CHUNKS)]
    assert rows(conn) == [("B", SET_ID, SET_ID, 3)]


def test_a_failed_stack_a_upload_deletes_the_store_and_records_nothing(conn, stacks, monkeypatch):
    """A half-filled store would cost storage and could be searched by mistake."""
    def fail(sid, chunks):
        raise RuntimeError("vector store batch b: 2 of 3 completed")

    monkeypatch.setattr(openai_vector_store, "upload_chunks", fail)
    with pytest.raises(RuntimeError, match="2 of 3"):
        indexes.build(conn, "A", SET_ID)
    assert stacks[-1] == ("delete", "vs_1")
    assert rows(conn) == []


def test_a_qdrant_collection_missing_chunks_is_refused_and_not_recorded(conn, stacks, monkeypatch):
    monkeypatch.setattr(qdrant_store, "index_chunks", lambda q, name, chunks: len(chunks) - 1)
    with pytest.raises(RuntimeError, match="stored 2 of 3"):
        indexes.build(conn, "B", SET_ID)
    assert rows(conn) == []


@pytest.mark.parametrize("stack", ["A", "B"])
def test_an_index_is_built_once_per_stack_and_chunk_set(conn, stacks, stack):
    indexes.build(conn, stack, SET_ID)
    calls = len(stacks)
    with pytest.raises(ValueError, match="already indexed"):
        indexes.build(conn, stack, SET_ID)
    assert len(stacks) == calls
    assert len(rows(conn)) == 1


def test_the_same_chunk_set_is_indexed_on_both_stacks_separately(conn, stacks):
    indexes.build(conn, "A", SET_ID)
    indexes.build(conn, "B", SET_ID)
    assert (indexes.lookup(conn, "A", SET_ID), indexes.lookup(conn, "B", SET_ID)) == ("vs_1", SET_ID)


def test_a_chunk_set_never_saved_is_not_indexed(conn, stacks):
    with pytest.raises(FileNotFoundError):
        indexes.build(conn, "B", "fixed__c100__o0")
    assert (stacks, rows(conn)) == ([], [])


@pytest.mark.parametrize("row", [{"stack": "C"}, {"ref": ""}, {"chunk_count": 0}])
def test_the_table_refuses_an_unknown_stack_an_empty_ref_or_no_chunks(conn, row):
    good = {"stack": "A", "chunk_set_id": SET_ID, "ref": "vs_1", "chunk_count": 3}
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        runs.insert(conn, "indexes", good | row)


@pytest.mark.parametrize("openai_ranking", [
    META.openai_ranking, {"ranker": "auto", "embedding_weight": 0.3, "text_weight": 0.7, "score_threshold": 0.2}])
def test_a_stack_a_run_searches_its_store_with_its_stored_ranking(conn, stacks, monkeypatch, openai_ranking):
    searched = []
    monkeypatch.setattr(openai_vector_store, "search",
                        lambda sid, question, k, ranking: searched.append((sid, question, k, ranking)) or [])
    indexes.build(conn, "A", SET_ID)
    indexes.retriever(conn, replace(META, openai_ranking=openai_ranking))("What does Acme pay?", 5)
    assert searched == [("vs_1", "What does Acme pay?", 5, openai_vector_store.Ranking(**openai_ranking))]


@pytest.mark.parametrize("hybrid", [False, True])
def test_a_stack_b_run_searches_its_collection_with_its_hybrid_setting(conn, stacks, monkeypatch, hybrid):
    searched = []
    monkeypatch.setattr(qdrant_store, "search",
                        lambda q, name, question, k, hybrid: searched.append((q, name, question, k, hybrid)) or [])
    indexes.build(conn, "B", SET_ID)
    meta = replace(META, stack="B", hybrid=hybrid, openai_ranking=None)
    indexes.retriever(conn, meta)("What does Acme pay?", 4)
    assert searched == [("qdrant", SET_ID, "What does Acme pay?", 4, hybrid)]


@pytest.mark.parametrize("stack", ["A", "B"])
def test_a_run_on_a_chunk_set_not_indexed_on_its_stack_is_refused(conn, stacks, stack):
    other = "B" if stack == "A" else "A"
    indexes.build(conn, other, SET_ID)
    meta = replace(META, stack=stack, openai_ranking=META.openai_ranking if stack == "A" else None)
    with pytest.raises(KeyError, match=f"not indexed on Stack {stack}"):
        indexes.retriever(conn, meta)


def test_stack_b_finds_the_chunk_it_indexed_in_a_real_qdrant(conn, monkeypatch):
    """Real nomic embeddings (batch size 4) in Qdrant's in-process mode: build and search meet on one name."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(qdrant_store, "client", lambda: client)
    monkeypatch.setattr(indexes, "load_chunk_set", lambda set_id: CHUNKS)
    indexes.build(conn, "B", SET_ID)
    hits = indexes.retriever(conn, replace(META, stack="B", hybrid=False, openai_ranking=None))(
        "How much does Acme pay each year?", 1)
    assert [(h.chunk_id, h.text) for h in hits] == [(CHUNKS[0].chunk_id, CHUNKS[0].text)]
    assert isinstance(hits[0], Hit)
