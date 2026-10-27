"""Step 5 checks of our side of the judge (no network). `test_live_judge.py` checks the judge itself."""

import pytest
from pydantic import ValidationError

from rag_playground.datasets import schema
from rag_playground.scoring import judging
from rag_playground.settings import JUDGE_MODEL

TEST = schema.TestCase(id="numerical-004", question="What is the price of the service?",
                       reference_answer="It costs 46,250 USD.", category="numerical",
                       source_docs=["services/a.md"], keywords=["46,250 USD"], split="dev")
GRADES = {"feedback": "ok", "refused": False, "accuracy": 5, "completeness": 4, "relevance": 3}


def test_answer_call_holds_question_reference_and_answer_but_no_context():
    system, user = judging.answer_messages(TEST, "It costs 46,250 USD.")
    assert system == {"role": "system", "content": judging.ANSWER_INSTRUCTIONS}
    assert user["content"] == ("QUESTION:\nWhat is the price of the service?\n\nREFERENCE ANSWER:\nIt costs 46,250 USD."
                               "\n\nANSWER TO GRADE:\nIt costs 46,250 USD.")


def test_faithfulness_call_never_sees_the_reference_answer():
    """The root-cause fix: the judge cannot let the reference override the context if it never sees it."""
    system, user = judging.faithfulness_messages(TEST, ["first chunk", "second chunk"], "An answer.")
    assert system == {"role": "system", "content": judging.FAITHFULNESS_INSTRUCTIONS}
    assert user["content"] == ("QUESTION:\nWhat is the price of the service?"
                               "\n\nRETRIEVED CONTEXT:\n[1] first chunk\n\n[2] second chunk"
                               "\n\nANSWER TO GRADE:\nAn answer.")
    assert TEST.reference_answer not in system["content"] + user["content"]


@pytest.mark.parametrize("bad", [0, 6])
def test_scores_outside_1_to_5_are_rejected(bad):
    with pytest.raises(ValidationError):
        judging.AnswerGrades(**{**GRADES, "accuracy": bad})
    with pytest.raises(ValidationError):
        judging.FaithfulnessGrade(feedback="ok", faithfulness=bad)


def test_schemas_ask_for_feedback_before_the_scores():
    assert list(judging.AnswerGrades.model_json_schema()["properties"])[0] == "feedback"
    assert list(judging.FaithfulnessGrade.model_json_schema()["properties"])[0] == "feedback"
    assert judging.FaithfulnessGrade.model_json_schema()["properties"]["faithfulness"]["enum"] == [1, 2, 3, 4, 5]


def test_judge_makes_both_calls_and_merges_their_grades(monkeypatch):
    calls = []
    replies = {judging.AnswerGrades: (judging.AnswerGrades(**GRADES), "answer result"),
               judging.FaithfulnessGrade: (judging.FaithfulnessGrade(feedback="unsupported", faithfulness=2),
                                           "faithfulness result")}
    monkeypatch.setattr(judging, "chat_structured",
                        lambda model, messages, schema: calls.append((model, messages, schema)) or replies[schema])
    judgement, results = judging.judge(TEST, ["chunk"], "answer")
    assert calls == [(JUDGE_MODEL, judging.answer_messages(TEST, "answer"), judging.AnswerGrades),
                     (JUDGE_MODEL, judging.faithfulness_messages(TEST, ["chunk"], "answer"), judging.FaithfulnessGrade)]
    assert judgement == judging.Judgement(refused=False, accuracy=5, completeness=4, relevance=3, faithfulness=2,
                                          feedback="ok", faithfulness_feedback="unsupported")
    assert results == ["answer result", "faithfulness result"]
