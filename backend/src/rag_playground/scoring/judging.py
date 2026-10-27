"""LLM-as-judge: four 1-5 scores and a refusal flag per answer (plan.md 4.2, T07, T19).

Faithfulness is graded in a separate call that never sees the reference answer: in one combined call the
judge let a matching reference answer override the context (fix.md, 2026-10-27). The rubric anchors are a
custom choice (decision.md T41), not a standard."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from rag_playground.datasets.schema import TestCase
from rag_playground.llm.openrouter import ChatResult, chat_structured
from rag_playground.settings import JUDGE_MODEL

Score = Literal[1, 2, 3, 4, 5]

ANSWER_INSTRUCTIONS = """You grade one answer from a question-answering system against a reference answer.
You receive the question, the reference answer and the system's answer.
First write a short feedback explaining your grades, then grade each criterion from 1 to 5.

refused: true if the answer declines to answer or says the information is not available; otherwise false.

accuracy (answer vs reference answer): is what the answer states correct?
- 5: every stated fact agrees with the reference answer.
- 3: the main fact is correct but a secondary detail is wrong.
- 1: the main fact is wrong or missing, or any stated fact contradicts the reference answer.
- If the reference answer is "Not in the knowledge base.": a refusal scores 5; any answer that gives a substantive answer scores 1.
- If the reference answer contains an answer and the system refused: 1.

completeness (answer vs reference answer): does the answer give every part of what the question asks for, as the reference answer gives it?
- 5: every part. 3: about half of the parts. 1: none of them.
- Supporting details in the reference answer that the question does not ask for, such as the dates used to compute a duration, are not required.
- If the reference answer is "Not in the knowledge base.": a refusal scores 5; any answer that gives a substantive answer scores 1.

relevance (answer vs question): does the answer address the question, and only the question?
- 5: it answers exactly what was asked. 3: it answers but adds unrelated material. 1: it does not address the question.
- A refusal of a question is relevant (5)."""

FAITHFULNESS_INSTRUCTIONS = """You check whether an answer from a question-answering system is supported by the documents it retrieved.
You receive the question, the retrieved context and the system's answer. You do not know the correct answer.
First write a short feedback naming any claim the context does not support, then grade faithfulness from 1 to 5.

faithfulness: is every claim in the answer supported by the retrieved context?
- 5: every claim is stated in, or computed from, the context.
- 3: the main claim is supported but some other claims are not.
- 1: the main claim is not supported by the context.
- Judge only against the context, never against your own knowledge: a claim that may be true but is not in the context is unsupported.
- An answer that makes no factual claims, such as a refusal, scores 5."""


class AnswerGrades(BaseModel):
    """Grades against the reference answer; feedback comes first so the scores follow the reasoning."""

    feedback: str
    refused: bool
    accuracy: Score
    completeness: Score
    relevance: Score


class FaithfulnessGrade(BaseModel):
    """Grade against the retrieved context only."""

    feedback: str
    faithfulness: Score


@dataclass(frozen=True)
class Judgement:
    """The full verdict on one answer."""

    refused: bool
    accuracy: int
    completeness: int
    relevance: int
    faithfulness: int
    feedback: str
    faithfulness_feedback: str


def numbered(context: list[str]) -> str:
    return "\n\n".join(f"[{i}] {text}" for i, text in enumerate(context, 1))


def answer_messages(test: TestCase, answer: str) -> list[dict]:
    """Input of the reference-based call: question, reference answer and the answer (no context)."""
    return [
        {"role": "system", "content": ANSWER_INSTRUCTIONS},
        {"role": "user", "content": f"QUESTION:\n{test.question}\n\nREFERENCE ANSWER:\n{test.reference_answer}\n\n"
                                    f"ANSWER TO GRADE:\n{answer}"},
    ]


def faithfulness_messages(test: TestCase, context: list[str], answer: str) -> list[dict]:
    """Input of the faithfulness call: question, numbered retrieved chunks and the answer (no reference)."""
    return [
        {"role": "system", "content": FAITHFULNESS_INSTRUCTIONS},
        {"role": "user", "content": f"QUESTION:\n{test.question}\n\nRETRIEVED CONTEXT:\n{numbered(context)}\n\n"
                                    f"ANSWER TO GRADE:\n{answer}"},
    ]


def judge(test: TestCase, context: list[str], answer: str) -> tuple[Judgement, list[ChatResult]]:
    """Grade one answer with two judge calls; both results are returned for cost and reproducibility."""
    grades, answer_result = chat_structured(JUDGE_MODEL, answer_messages(test, answer), AnswerGrades)
    faith, faith_result = chat_structured(JUDGE_MODEL, faithfulness_messages(test, context, answer),
                                          FaithfulnessGrade)
    judgement = Judgement(refused=grades.refused, accuracy=grades.accuracy, completeness=grades.completeness,
                          relevance=grades.relevance, faithfulness=faith.faithfulness, feedback=grades.feedback,
                          faithfulness_feedback=faith.feedback)
    return judgement, [answer_result, faith_result]
