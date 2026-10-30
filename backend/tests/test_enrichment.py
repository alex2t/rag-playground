"""Step 7 checks of LLM enrichment, with a fake LLM (no network, no cost): the original text stays exact, and a
chunk paid for once is never paid for again."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_playground.chunking import chunk_sets, enrichment
from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.settings import ENRICH_MODEL, settings

BASE_ID = "fixed__c64__o0"
DOCS = {"clients/a.md": "Client Alpha. The rollout took 6 weeks.", "services/b.md": "Service Beta costs 100 USD."}


def chunk(path: str, index: int, start: int, end: int) -> Chunk:
    return Chunk(chunk_id=f"{path}#{index}", source=path, doc_type=path.split("/")[0], index=index,
                 text=DOCS[path][start:end], tokens=5, start=start, end=end)


BASE = [chunk("clients/a.md", 0, 0, 13), chunk("clients/a.md", 1, 14, 39), chunk("services/b.md", 0, 0, 27)]


@pytest.fixture
def llm(tmp_path, monkeypatch):
    """A saved base chunk set and a fake LLM that records each call; `llm.fail_on` makes one call fail."""
    monkeypatch.setattr(settings, "var_dir", tmp_path)
    monkeypatch.setattr(enrichment, "kb_documents", lambda: DOCS)
    chunk_sets.saved_path(BASE_ID).parent.mkdir(parents=True)
    chunk_sets.saved_path(BASE_ID).write_text("".join(c.model_dump_json() + "\n" for c in BASE), encoding="utf-8")
    state = SimpleNamespace(calls=[], fail_on=None, reply=None)

    def fake(model, messages, schema):
        state.calls.append((model, messages))
        if len(state.calls) == state.fail_on:
            raise RuntimeError("provider down")
        return state.reply or schema(headline=f"Headline {len(state.calls)}", summary="A summary."), None

    monkeypatch.setattr(enrichment, "chat_structured", fake)
    return state


def test_an_enriched_set_is_named_after_its_base_set():
    assert enrichment.enriched_set_id(BASE_ID) == "llm_enriched__c64__o0"


def test_only_a_fixed_set_can_be_enriched(llm):
    with pytest.raises(ValueError):
        enrichment.load_or_enrich("llm_enriched__c64__o0")


def test_a_base_set_never_built_is_refused_without_calling_the_llm(llm):
    with pytest.raises(FileNotFoundError):
        enrichment.load_or_enrich("fixed__c128__o0")
    assert llm.calls == []


def test_the_llm_reads_the_chunk_and_its_whole_document(llm):
    """The third chunk comes from another document than the first two, so each call must send its own."""
    enrichment.load_or_enrich(BASE_ID)
    assert [model for model, _ in llm.calls] == [ENRICH_MODEL] * 3
    sent = [messages[-1]["content"] for _, messages in llm.calls]
    assert sent[1] == f"Document:\n{DOCS['clients/a.md']}\n\nChunk:\nThe rollout took 6 weeks."
    assert sent[2] == f"Document:\n{DOCS['services/b.md']}\n\nChunk:\n{DOCS['services/b.md']}"


def test_the_original_text_is_kept_exactly_and_found_in_its_document(llm):
    enriched = enrichment.load_or_enrich(BASE_ID)
    assert [c.model_dump(include=set(Chunk.model_fields)) for c in enriched] == [c.model_dump() for c in BASE]
    assert all(DOCS[c.source][c.start:c.end] == c.text for c in enriched)


def test_search_reads_headline_summary_and_original_text(llm):
    first = enrichment.load_or_enrich(BASE_ID)[0]
    assert first.indexed_text == f"Headline 1\nA summary.\n\n{first.text}"


def test_a_second_build_does_not_call_the_llm_again(llm):
    first = enrichment.load_or_enrich(BASE_ID)
    assert len(llm.calls) == 3
    assert enrichment.load_or_enrich(BASE_ID) == first
    assert len(llm.calls) == 3


def test_a_build_stopped_halfway_keeps_what_was_paid_for_and_resumes(llm):
    llm.fail_on = 3
    with pytest.raises(RuntimeError):
        enrichment.load_or_enrich(BASE_ID)
    llm.fail_on, llm.calls = None, []
    enriched = enrichment.load_or_enrich(BASE_ID)
    assert len(llm.calls) == 1
    assert [c.chunk_id for c in enriched] == [c.chunk_id for c in BASE]
    assert [c.headline for c in enriched] == ["Headline 1", "Headline 2", "Headline 1"]


def test_a_stop_while_saving_leaves_the_saved_chunks_whole_and_the_build_resumes(llm, monkeypatch):
    """The save is one atomic step: the stop falls between writing the new file and putting it in place, and the half
    finished file left behind does not get in the way."""
    real_replace, saves = Path.replace, []

    def stop_on_second_save(self, target):
        saves.append(target)
        if len(saves) == 2:
            raise OSError("power cut")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", stop_on_second_save)
    with pytest.raises(OSError):
        enrichment.load_or_enrich(BASE_ID)
    monkeypatch.setattr(Path, "replace", real_replace)
    path = chunk_sets.saved_path("llm_enriched__c64__o0")
    path.with_suffix(".tmp").write_text('{"chunk_id": "half a li', encoding="utf-8")
    assert [c.chunk_id for c in enrichment.load_saved("llm_enriched__c64__o0", BASE)] == [BASE[0].chunk_id]
    llm.calls = []
    assert len(enrichment.load_or_enrich(BASE_ID)) == 3
    assert len(llm.calls) == 2
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize("field", ["headline", "summary"])
def test_a_blank_reply_is_refused_and_not_saved(llm, field):
    llm.reply = enrichment.Enrichment(**{"headline": "h", "summary": "s", field: "  \n"})
    with pytest.raises(ValueError):
        enrichment.load_or_enrich(BASE_ID)
    assert not chunk_sets.saved_path("llm_enriched__c64__o0").exists()


def test_a_saved_chunk_that_differs_from_its_base_chunk_is_refused(llm):
    enrichment.load_or_enrich(BASE_ID)
    path = chunk_sets.saved_path("llm_enriched__c64__o0")
    path.write_text(path.read_text(encoding="utf-8").replace("6 weeks", "9 weeks"), encoding="utf-8")
    with pytest.raises(ValueError):
        enrichment.load_or_enrich(BASE_ID)


def test_a_saved_set_longer_than_its_base_set_is_refused(llm):
    enrichment.load_or_enrich(BASE_ID)
    path = chunk_sets.saved_path("llm_enriched__c64__o0")
    lines = path.read_text(encoding="utf-8")
    path.write_text(lines + lines.splitlines()[-1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        enrichment.load_or_enrich(BASE_ID)


def test_a_base_chunk_that_no_longer_matches_its_document_is_refused(llm, monkeypatch):
    """The KB changed after the chunk set was built: enriching it would describe text that is gone."""
    monkeypatch.setattr(enrichment, "kb_documents", lambda: {**DOCS, "clients/a.md": "Client Alpha. Rewritten text."})
    with pytest.raises(ValueError):
        enrichment.load_or_enrich(BASE_ID)
    assert llm.calls == []


def test_answers_read_the_original_text_of_an_enriched_set(llm):
    """The pipeline loads chunk sets by id: for an enriched set it must get the plain original chunks."""
    enrichment.load_or_enrich(BASE_ID)
    assert chunk_sets.load("llm_enriched__c64__o0") == BASE
