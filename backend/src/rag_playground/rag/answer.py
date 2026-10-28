"""The answer step: a prompt version, the retrieved chunks and the question go to the answer model."""

from rag_playground.llm.openrouter import ChatResult, chat
from rag_playground.rag.prompts import PromptVersion
from rag_playground.scoring.judging import numbered
from rag_playground.stacks.hits import Hit


def answer_messages(prompt: PromptVersion, question: str, hits: list[Hit]) -> list[dict]:
    """The system prompt, then the chunks numbered exactly as the judge sees them, then the question."""
    context = numbered([hit.text for hit in hits])
    return [
        {"role": "system", "content": prompt.text},
        {"role": "user", "content": f"CONTEXT DOCUMENTS:\n{context}\n\nQUESTION:\n{question}"},
    ]


def answer(model: str, prompt: PromptVersion, question: str, hits: list[Hit]) -> ChatResult:
    """Answer one question; the result carries the text, cost and model metadata."""
    return chat(model, answer_messages(prompt, question, hits))
