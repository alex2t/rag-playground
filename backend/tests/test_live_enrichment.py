"""Live check of T47 with the real enrichment model on real KB chunks (under $0.001). Run by the user."""

import pytest

from rag_playground.chunking import chunk_sets, enrichment


@pytest.mark.live
def test_the_real_model_writes_a_headline_and_summary_naming_the_subject():
    """The first chunk of a client document, which opens with the client's name."""
    documents = chunk_sets.kb_documents()
    path = next(p for p in documents if p.startswith("clients/"))
    chunk = chunk_sets.build_chunk_set({path: documents[path]}, 200, 0)[0]
    enriched = enrichment.enrich(chunk, documents[path])
    print(f"\n{enriched.headline}\n{enriched.summary}")
    assert enriched.text == chunk.text
    assert len(enriched.headline.split()) <= 15
    assert len(enriched.summary) < 600
    assert "this chunk" not in enriched.summary.lower()
