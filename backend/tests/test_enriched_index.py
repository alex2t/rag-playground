"""Step 7 checks of T47 on both stacks: search reads the headline and summary, while answers only ever get the
original text. Stack B runs in Qdrant's in-process mode with fake vectors; Stack A's calls are faked. No network."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from qdrant_client import QdrantClient

from rag_playground import store
from rag_playground.chunking import chunk_sets, enrichment
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.chunking.enrichment import EnrichedChunk
from rag_playground.settings import EMBED_DIM, settings
from rag_playground.stacks import indexes, nomic, openai_vector_store, qdrant_store
from rag_playground.stacks.hits import Hit
from test_indexes import META

BASE_ID, SET_ID = "fixed__c64__o0", "llm_enriched__c64__o0"
DOC = "The rollout took 6 weeks. It ended in May."
BASE = [Chunk(chunk_id=f"clients/a.md#{i}", source="clients/a.md", doc_type="clients", index=i, text=DOC[start:end],
              tokens=5, start=start, end=end) for i, (start, end) in enumerate([(0, 25), (26, 42)])]
ENRICHED = [EnrichedChunk(**c.model_dump(), headline=f"Alpha project {c.index}", summary="Alpha's rollout.")
            for c in BASE]
RANKING = {"ranker": "auto", "embedding_weight": 1.0, "text_weight": 1.0, "score_threshold": 0.0}


def save(set_id: str, chunks: list[Chunk]) -> None:
    path = chunk_sets.saved_path(set_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")


@pytest.fixture
def saved(tmp_path, monkeypatch):
    """A base set and its full enriched set on disk."""
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    save(BASE_ID, BASE)
    save(SET_ID, ENRICHED)


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def stack_a(monkeypatch):
    """A fake store that returns the uploaded (enriched) text, as the real one does."""
    calls = []
    monkeypatch.setattr(openai_vector_store, "create_store", lambda name: "vs_1")
    monkeypatch.setattr(openai_vector_store, "upload_chunks", lambda sid, chunks: calls.append(chunks))
    monkeypatch.setattr(openai_vector_store, "search", lambda sid, question, k, ranking: [
        Hit(c.chunk_id, c.source, 1.0, c.indexed_text) for c in ENRICHED[:k]])
    return calls


def test_a_plain_chunk_is_indexed_as_its_own_text():
    assert BASE[0].indexed_text == BASE[0].text


def test_stack_a_uploads_the_text_search_should_read(monkeypatch):
    sent = []
    files = SimpleNamespace(create=lambda file, purpose: sent.append(file[1]) or SimpleNamespace(id="f"))
    monkeypatch.setattr(openai_vector_store, "client", lambda: SimpleNamespace(files=files))
    openai_vector_store.upload_file(ENRICHED[0])
    assert sent == [ENRICHED[0].indexed_text.encode()]


def test_stack_b_embeds_the_enriched_text_but_returns_the_original(monkeypatch):
    embedded, keywords = [], []
    monkeypatch.setattr(nomic, "embed_documents", lambda texts: embedded.extend(texts) or [[1.0] * EMBED_DIM] * len(texts))
    monkeypatch.setattr(nomic, "embed_query", lambda text: [1.0] * EMBED_DIM)
    sparse = SimpleNamespace(indices=np.array([1]), values=np.array([1.0]))
    monkeypatch.setattr(qdrant_store, "bm25", lambda: SimpleNamespace(
        embed=lambda texts: keywords.extend(texts) or [sparse] * len(texts)))
    q = QdrantClient(":memory:")
    qdrant_store.index_chunks(q, SET_ID, ENRICHED)
    assert embedded == keywords == [c.indexed_text for c in ENRICHED]
    hits = qdrant_store.search(q, SET_ID, "rollout", 2)
    assert {h.text for h in hits} == {c.text for c in BASE}


def test_stack_a_hits_of_an_enriched_set_carry_the_original_text(conn, saved, stack_a):
    conn.execute("INSERT INTO indexes (stack, chunk_set_id, ref, chunk_count) VALUES ('A', ?, 'vs_1', 2)", (SET_ID,))
    meta = replace(META, chunk_set_id=SET_ID, openai_ranking=RANKING)
    hits = indexes.retriever(conn, meta)("rollout", 2)
    assert [(h.chunk_id, h.source, h.score) for h in hits] == [(c.chunk_id, c.source, 1.0) for c in BASE]
    assert [h.text for h in hits] == [c.text for c in BASE]


def test_stack_a_hits_of_a_plain_set_are_left_alone_and_need_no_saved_file(conn, monkeypatch):
    hit = Hit("c", "s", 1.0, "text")
    monkeypatch.setattr(openai_vector_store, "search", lambda sid, question, k, ranking: [hit])
    conn.execute("INSERT INTO indexes (stack, chunk_set_id, ref, chunk_count) VALUES ('A', ?, 'vs_1', 1)",
                 (META.chunk_set_id,))
    assert indexes.retriever(conn, replace(META, openai_ranking=RANKING))("q", 1) == [hit]


def test_building_an_enriched_index_uses_the_enriched_chunks(conn, saved, stack_a):
    indexes.build(conn, "A", SET_ID)
    assert stack_a == [ENRICHED]
    assert indexes.lookup(conn, "A", SET_ID) == "vs_1"


@pytest.mark.parametrize("stack", ["A", "B"])
def test_a_partly_enriched_set_cannot_be_indexed_so_it_cannot_be_run(conn, saved, stack_a, stack, monkeypatch):
    """A stopped build leaves some chunks enriched: an index of them would silently miss part of the KB."""
    monkeypatch.setattr(qdrant_store, "index_chunks", lambda *args: pytest.fail("indexed a partial set"))
    save(SET_ID, ENRICHED[:1])
    with pytest.raises(ValueError, match="1 of 2"):
        indexes.build(conn, stack, SET_ID)
    assert stack_a == [] and indexes.lookup(conn, stack, SET_ID) is None


def test_a_set_never_enriched_cannot_be_indexed(conn, saved, stack_a):
    chunk_sets.saved_path(SET_ID).unlink()
    with pytest.raises(ValueError, match="0 of 2"):
        indexes.build(conn, "A", SET_ID)


def test_load_complete_gives_back_the_enriched_chunks(saved):
    assert enrichment.load_complete(SET_ID) == ENRICHED
