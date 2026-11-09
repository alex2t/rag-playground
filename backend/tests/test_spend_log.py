"""Tests for the paid-call log lines (D37): every OpenRouter call that returns is logged with its tokens and cost,
tied to the request that made it; a background job's calls carry no request id. Fakes only, no cost."""

import io
import json
import logging

import pytest
from test_api_runs import B as RUN_B, start
from test_ask import B as ASK_B, asking, post  # noqa: F401  (asking is a fixture)
from test_jobs import world  # noqa: F401  (world is a fixture)

from rag_playground.llm.openrouter import ChatResult, paid
from rag_playground.logs import JsonFormatter


@pytest.fixture
def written():
    """The app's log lines as written (formatted when emitted, as stdout gets them), parsed."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("rag_playground")
    logger.addHandler(handler)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    logger.removeHandler(handler)


def spend_lines(lines):
    return [line for line in lines if line["logger"] == "rag_playground.spend"]


def test_a_paid_call_is_logged_with_its_model_tokens_and_cost(written):
    paid(ChatResult(text="x", model="m/a", canonical_slug="m/a-1", temperature_controlled=True,
                    prompt_tokens=11, completion_tokens=7, reasoning_tokens=3, cost_usd=0.0042))
    [line] = spend_lines(written())
    assert (line["level"], line["message"]) == ("INFO", "paid call")
    assert (line["model"], line["prompt_tokens"], line["completion_tokens"], line["reasoning_tokens"],
            line["cost_usd"]) == ("m/a", 11, 7, 3, 0.0042)
    assert "request_id" not in line


def test_paid_calls_during_a_request_carry_its_request_id(asking, written):
    response = post({**ASK_B, "question": "Who?"})
    assert response.status_code == 200
    calls = spend_lines(written())
    assert len(calls) == 1
    assert calls[0]["request_id"] == response.headers["X-Request-ID"]


def test_a_background_jobs_paid_calls_carry_no_request_id(world, written):
    response = start(RUN_B)
    assert response.status_code == 202
    calls = spend_lines(written())
    assert len(calls) == 40
    assert all("request_id" not in line for line in calls)
