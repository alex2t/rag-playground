"""GET /api/panel: what the settings panel offers must be what the requests accept (T35)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rag_playground import main
from rag_playground.ask_requests import AskRequest
from rag_playground.chunking.chunk_sets import chunk_set_id
from rag_playground.settings import ANSWER_MODELS, MAX_TOP_K, S0


@pytest.fixture
def options():
    response = TestClient(main.app).get("/api/panel")
    assert response.status_code == 200
    return response.json()


def request(options, stack, **changes):
    """An Ask request built from the panel's starting values, as the page builds it."""
    start = options["start"]
    search = {"A": {"openai_ranking": start["openai_ranking"]}, "B": {"hybrid": start["hybrid"]}}[stack]
    fields = {key: start[key] for key in ("chunking_method", "chunk_size", "overlap", "top_k", "rerank", "answer_model")}
    return AskRequest(**fields | search | {"stack": stack, "prompt_name": "default", "question": "Why?"} | changes)


def test_offers_the_ranges_and_models_of_settings(options):
    assert (options["min_chunk_size"], options["max_chunk_size"], options["max_overlap_share"]) == (64, 2048, 0.5)
    assert options["max_top_k"] == MAX_TOP_K == 8
    assert options["answer_models"] == ANSWER_MODELS


@pytest.mark.parametrize("stack", ["A", "B"])
def test_starting_values_are_s0_and_a_valid_request(options, stack):
    choices = request(options, stack).choices()
    assert choices.chunk_set_id == chunk_set_id(S0["chunk_size"], S0["overlap"])
    assert (choices.top_k, choices.rerank, choices.answer_model) == (S0["top_k"], S0["rerank"], S0["answer_model"])
    assert choices.openai_ranking == S0["search"][stack]["openai_ranking"]
    assert choices.hybrid == S0["search"][stack]["hybrid"]


@pytest.mark.parametrize("stack", ["A", "B"])
def test_the_limits_offered_are_accepted(options, stack):
    largest = options["max_chunk_size"]
    assert request(options, stack, chunk_size=options["min_chunk_size"], overlap=0)
    assert request(options, stack, chunk_size=largest, overlap=int(largest * options["max_overlap_share"]))
    assert request(options, stack, top_k=options["max_top_k"])
    for model in options["answer_models"]:
        assert request(options, stack, answer_model=model)


@pytest.mark.parametrize("change", [{"chunk_size": 63, "overlap": 0}, {"chunk_size": 2049}, {"chunk_size": 100, "overlap": 51},
                                    {"top_k": 9}, {"top_k": 0}, {"answer_model": "other"}])
def test_one_step_past_the_limits_is_refused(options, change):
    with pytest.raises(ValidationError):
        request(options, "B", **change)
