"""Full-KB verification of test candidates by an independent model (T34)."""

from pydantic import BaseModel

from rag_playground.datasets.candidates import Candidate
from rag_playground.datasets.schema import Category
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import AUDIT_MODEL

INSTRUCTIONS = """You verify evaluation questions for a RAG system against its whole knowledge base, given below with each document's path.
For each numbered question, judge it using only the knowledge base:
- answerable: the knowledge base states enough to answer it (computing from stated values, such as the time between two dates, counts as answerable).
- unambiguous: it has exactly one correct answer; it cannot reasonably refer to a different entity or be read in two ways.
- reference_correct: the given reference answer is correct according to the knowledge base.
- reference_complete: the reference answer contains everything the question asks for.
- docs_with_answer: every document path that states information needed for the answer and not already given in the question. Include every document that states it, even if another document states it too. Empty if not answerable.
- fewer_docs_suffice: true if fewer documents than docs_with_answer are enough to answer fully, for example because the question itself states a fact from one document, or one document alone already identifies the entity and states the answer. Always false when docs_with_answer has at most one document.
For a question whose reference answer is "Not in the knowledge base.", judge whether the knowledge base really does not answer it: answerable must be false if nothing in it answers the question.
Give a one-sentence explanation for each verdict. Return one verdict per question, with its index."""


class Verdict(BaseModel):
    index: int
    answerable: bool
    unambiguous: bool
    reference_correct: bool
    reference_complete: bool
    docs_with_answer: list[str]
    fewer_docs_suffice: bool
    explanation: str


class VerdictBatch(BaseModel):
    verdicts: list[Verdict]


def accepted(c: Candidate, v: Verdict) -> bool:
    """Keep a candidate only if the verifier confirms it exactly (T34)."""
    if c.category == Category.UNANSWERABLE:
        return not v.answerable
    return (v.answerable and v.unambiguous and v.reference_correct and v.reference_complete
            and not v.fewer_docs_suffice
            and set(v.docs_with_answer) == set(c.source_docs))


def question_block(i: int, c: Candidate) -> str:
    return f"[{i}] ({c.category}) {c.question}\nReference answer: {c.reference_answer}"


def verify_batch(candidates: list[Candidate], kb_text: str) -> tuple[list[Verdict], float]:
    """Verify up to 10 candidates against the whole KB; verdicts are returned in candidate order."""
    questions = "\n\n".join(question_block(i, c) for i, c in enumerate(candidates))
    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": f"KNOWLEDGE BASE:\n{kb_text}\n\nQUESTIONS:\n{questions}"},
    ]
    batch, result = chat_structured(AUDIT_MODEL, messages, VerdictBatch, max_tokens=64000)
    by_index = {v.index: v for v in batch.verdicts}
    if sorted(by_index) != list(range(len(candidates))):
        raise RuntimeError(f"verifier returned indexes {sorted(by_index)} for {len(candidates)} questions")
    return [by_index[i] for i in range(len(candidates))], result.cost_usd
