"""Step 6 checks of the answer step (no network). `test_live_answer.py` checks a real model."""

from rag_playground.datasets import schema
from rag_playground.rag import answer
from rag_playground.rag.prompts import PromptVersion, sha256
from rag_playground.scoring import judging
from rag_playground.stacks.hits import Hit

PROMPT = PromptVersion("v1", "Answer from the context.", sha256("Answer from the context."))
HITS = [Hit("services/a.md#0", "services/a.md", 0.9, "The service costs 46,250 USD."),
        Hit("company/b.md#3", "company/b.md", 0.5, "The firm was founded in 2011.")]
CONTEXT = "[1] The service costs 46,250 USD.\n\n[2] The firm was founded in 2011."
TEST = schema.TestCase(id="numerical-004", question="What is the price?", reference_answer="It costs 46,250 USD.",
                       category="numerical", source_docs=["services/a.md"], keywords=["46,250 USD"], split="dev")


def test_messages_hold_the_prompt_version_the_numbered_chunks_in_rank_order_and_the_question():
    system, user = answer.answer_messages(PROMPT, "What is the price?", HITS)
    assert system == {"role": "system", "content": "Answer from the context."}
    assert user == {"role": "user", "content": f"CONTEXT DOCUMENTS:\n{CONTEXT}\n\nQUESTION:\nWhat is the price?"}


def test_the_faithfulness_judge_sees_the_same_context_text_as_the_answer_model():
    """Faithfulness is graded against the context, so it must be exactly the text the answer model read."""
    _, judge_user = judging.faithfulness_messages(TEST, [hit.text for hit in HITS], "An answer.")
    assert CONTEXT in judge_user["content"]


def test_no_retrieved_chunks_are_stated_explicitly_to_the_model_and_the_judge():
    """A score threshold (T40) can leave no chunks; an empty section would be ambiguous."""
    _, user = answer.answer_messages(PROMPT, "Q?", [])
    _, judge_user = judging.faithfulness_messages(TEST, [], "An answer.")
    assert user["content"] == "CONTEXT DOCUMENTS:\n(no documents were retrieved)\n\nQUESTION:\nQ?"
    assert "RETRIEVED CONTEXT:\n(no documents were retrieved)\n\n" in judge_user["content"]


def test_answer_sends_the_messages_to_the_chosen_model(monkeypatch):
    calls = []
    monkeypatch.setattr(answer, "chat", lambda model, messages: calls.append((model, messages)) or "result")
    assert answer.answer("openai/gpt-4.1-mini", PROMPT, "Q?", HITS) == "result"
    assert calls == [("openai/gpt-4.1-mini", answer.answer_messages(PROMPT, "Q?", HITS))]
