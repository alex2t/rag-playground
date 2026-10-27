"""Stack A checks of our side of the OpenAI calls (no network). The live tests prove OpenAI's side."""

from types import SimpleNamespace

import pytest
from openai.types import VectorStoreSearchResponse

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.stacks import openai_vector_store as store
from rag_playground.stacks.hits import Hit


def chunk(i: int) -> Chunk:
    return Chunk(chunk_id=f"clients/acme-co.md#{i}", source="clients/acme-co.md", doc_type="clients",
                 index=i, text=f"text {i}", tokens=2, start=0, end=6)


class FakeClient:
    """Records the calls our code makes; each file batch completes `completed(n)` of its n files."""

    def __init__(self, completed=lambda n: n):
        self.batches, self.searches = [], []
        poll = lambda store_id, files: self.batches.append(files) or SimpleNamespace(
            id="b", file_counts=SimpleNamespace(completed=completed(len(files))))
        self.vector_stores = SimpleNamespace(file_batches=SimpleNamespace(create_and_poll=poll),
                                             search=lambda store_id, **kw: self.searches.append(kw) or
                                             SimpleNamespace(data=[]))


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(store, "client", lambda: client)
    monkeypatch.setattr(store, "upload_file", lambda c: f"file-{c.index}")
    return client


def test_file_name_is_stable_distinct_and_free_of_document_words():
    assert store.file_name(chunk(0)) == store.file_name(chunk(0))
    assert store.file_name(chunk(0)) != store.file_name(chunk(1))
    assert "acme" not in store.file_name(chunk(0)) and "clients" not in store.file_name(chunk(0))


def test_ranking_has_no_defaults():
    with pytest.raises(TypeError):
        store.Ranking(ranker="none")


def test_ranking_body_sends_every_option():
    ranking = store.Ranking(ranker="none", embedding_weight=1.0, text_weight=0.5, score_threshold=0.0)
    assert store.ranking_body(ranking) == {"ranker": "none", "score_threshold": 0.0,
                                           "hybrid_search": {"embedding_weight": 1.0, "text_weight": 0.5}}


def test_search_sends_k_no_rewrite_and_the_ranking(fake):
    ranking = store.Ranking(ranker="auto", embedding_weight=1.0, text_weight=1.0, score_threshold=0.0)
    store.search("vs", "a question", 7, ranking)
    assert fake.searches == [{"query": "a question", "max_num_results": 7, "rewrite_query": False,
                              "extra_body": {"ranking_options": store.ranking_body(ranking)}}]


def test_to_hit_reads_ids_from_attributes_and_joins_content():
    result = VectorStoreSearchResponse.model_validate({
        "file_id": "file-1", "filename": "chunk_x.md", "score": 0.5,
        "attributes": {"chunk_id": "clients/acme-co.md#3", "source": "clients/acme-co.md", "doc_type": "clients"},
        "content": [{"type": "text", "text": "first "}, {"type": "text", "text": "second"}]})
    assert store.to_hit(result) == Hit("clients/acme-co.md#3", "clients/acme-co.md", 0.5, "first second")


def test_upload_chunks_batches_files_with_their_attributes(fake, monkeypatch):
    monkeypatch.setattr(store, "BATCH_SIZE", 2)
    assert store.upload_chunks("vs", [chunk(i) for i in range(5)]) == 5
    assert [len(b) for b in fake.batches] == [2, 2, 1]
    assert fake.batches[2] == [{"file_id": "file-4", "attributes": store.chunk_attributes(chunk(4)),
                                "chunking_strategy": store.NO_RESPLIT}]


def test_upload_chunks_raises_when_a_batch_is_incomplete(fake, monkeypatch):
    monkeypatch.setattr(store, "client", lambda: FakeClient(completed=lambda n: n - 1))
    with pytest.raises(RuntimeError):
        store.upload_chunks("vs", [chunk(0), chunk(1)])
