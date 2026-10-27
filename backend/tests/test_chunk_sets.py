"""Step 3 checks on chunk sets built from the real KB (T01, T35, T39)."""

from functools import cache

import pytest
from llama_index.core.utils import get_tokenizer

from rag_playground.chunking.chunk_sets import (
    Chunk, build_chunk_set, check_params, chunk_set_id, kb_documents, load_or_build,
)

DOCS = kb_documents()
TOKENS = get_tokenizer()
SWEEP = [100, 200, 400, 800, 1024, 1600]


@cache
def built(size: int, overlap: int) -> tuple[Chunk, ...]:
    return tuple(build_chunk_set(DOCS, size, overlap))


def by_doc(chunks: tuple[Chunk, ...]) -> dict[str, list[Chunk]]:
    docs = {}
    for c in chunks:
        docs.setdefault(c.source, []).append(c)
    return docs


@pytest.mark.parametrize("size, overlap", [(63, 0), (2049, 0), (1024, -1), (1024, 513), (64, 33)])
def test_sizes_and_overlaps_outside_the_ranges_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        check_params(size, overlap)


@pytest.mark.parametrize("size, overlap", [(64, 0), (64, 32), (2048, 1024), (1024, 200)])
def test_range_limits_are_accepted(size, overlap):
    check_params(size, overlap)


def test_chunk_set_id_names_method_size_and_overlap():
    assert chunk_set_id(1024, 200) == "fixed__c1024__o200"


@pytest.mark.parametrize("share", [0, 200 / 1024])
def test_chunk_count_goes_down_as_size_goes_up(share):
    counts = [len(built(s, round(s * share))) for s in SWEEP]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] > counts[SWEEP.index(1024)]


# T39: the splitter limits the sum of its pieces' token counts; joined text can count up to 2 tokens more
# (measured over the full T35 range on our KB). (64, 6) and (66, 33) are the worst settings found.
TOLERANCE = 2


@pytest.mark.parametrize("size, overlap", [(64, 0), (100, 20), (400, 78), (1024, 200), (2048, 0), (64, 6), (66, 33)])
def test_no_chunk_exceeds_its_size_by_more_than_the_tolerance(size, overlap):
    chunks = built(size, overlap)
    assert all(c.tokens == len(TOKENS(c.text)) for c in chunks)
    assert max(c.tokens for c in chunks) <= size + TOLERANCE


@pytest.mark.parametrize("size, overlap", [(100, 20), (400, 78), (1024, 200), (192, 38), (64, 32), (66, 13)])
def test_consecutive_chunks_share_at_most_the_overlap(size, overlap):
    shared = [len(TOKENS(DOCS[a.source][b.start:a.end]))
              for chunks in by_doc(built(size, overlap)).values()
              for a, b in zip(chunks, chunks[1:]) if b.start < a.end]
    assert shared and max(shared) <= overlap + TOLERANCE


@pytest.mark.parametrize("size", [200, 84])
def test_without_overlap_consecutive_chunks_share_no_text(size):
    for chunks in by_doc(built(size, 0)).values():
        assert all(b.start >= a.end for a, b in zip(chunks, chunks[1:]))


@pytest.mark.parametrize("size, overlap", [(64, 0), (200, 39), (1024, 200), (84, 0), (132, 26), (192, 38), (66, 13)])
def test_chunks_are_exact_pieces_that_cover_each_document_in_order(size, overlap):
    """(84, 0), (132, 26), (192, 38): a runbook's last chunk is a lone "|" that also occurs in the chunk before.
    (66, 13): a one-sentence chunk fits entirely in the next chunk's overlap, so both start at the same place."""
    docs = by_doc(built(size, overlap))
    assert set(docs) == set(DOCS)
    for path, chunks in docs.items():
        text = DOCS[path]
        assert all(c.text == text[c.start:c.end] for c in chunks)
        assert [c.index for c in chunks] == list(range(len(chunks)))
        assert all(a.start <= b.start and a.end < b.end for a, b in zip(chunks, chunks[1:]))
        gaps = [(0, chunks[0].start), (chunks[-1].end, len(text))]
        gaps += [(a.end, b.start) for a, b in zip(chunks, chunks[1:])]
        assert all(not text[s:e].strip() for s, e in gaps if s < e)


def test_chunk_ids_folders_and_sources_are_set():
    c = built(1024, 200)[0]
    assert c.chunk_id == f"{c.source}#0" and c.doc_type == c.source.split("/")[0]


def test_out_of_range_settings_raise_even_when_a_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("rag_playground.chunking.chunk_sets.settings.var_dir", tmp_path)
    stale = tmp_path / "chunk_sets" / "fixed__c4096__o0.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_or_build(4096, 0)


def test_a_chunk_set_is_built_once_and_then_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr("rag_playground.chunking.chunk_sets.settings.var_dir", tmp_path)
    first = load_or_build(400, 78)
    path = tmp_path / "chunk_sets" / "fixed__c400__o78.jsonl"
    assert path.exists() and first == list(built(400, 78))
    path.write_text(path.read_text(encoding="utf-8").replace("#0", "#zero", 1), encoding="utf-8")
    assert load_or_build(400, 78)[0].chunk_id.endswith("#zero")
