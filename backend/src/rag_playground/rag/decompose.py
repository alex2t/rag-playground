"""Split the question (decision.md T60): a model splits a question into the parts it asks about, each part is
searched, and the chunks are taken in turns. One part searches the original question, as without the setting."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from rag_playground.llm.openrouter import ChatResult, chat_structured
from rag_playground.settings import DECOMPOSE_MODEL, MAX_SUB_QUESTIONS
from rag_playground.stacks.hits import Hit

INSTRUCTIONS = f"""You prepare a question for a document search.
If the question asks about one thing, return it unchanged as the only item.
If it needs facts about several separate things (for example two documents, people, projects or runbooks to
compare), return one short, self-contained search question per thing, at most {MAX_SUB_QUESTIONS}.
Never answer the question."""


class SubQuestions(BaseModel):
    """The parts of a question, each searched on its own."""

    sub_questions: list[str] = Field(min_length=1, max_length=MAX_SUB_QUESTIONS)


@dataclass(frozen=True)
class Split:
    """A searched question: the parts the model returned, the chunks kept, the searches made and the call's usage."""

    sub_questions: list[str]
    hits: list[Hit]
    searches: int
    result: ChatResult


def split_messages(question: str) -> list[dict]:
    return [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": question}]


def in_turns(lists: list[list[Hit]], k: int) -> list[Hit]:
    """The best hit of each list, then the second of each, and so on, skipping a chunk already kept, until `k`."""
    kept, seen = [], set()
    for rank in range(max(map(len, lists), default=0)):
        for hits in lists:
            if rank < len(hits) and hits[rank].chunk_id not in seen:
                kept.append(hits[rank])
                seen.add(hits[rank].chunk_id)
            if len(kept) == k:
                return kept
    return kept


def split_and_search(question: str, k: int, retrieve) -> Split:
    """Split the question, then search: the original question if there is one part, else each part for `k` chunks."""
    parts, result = chat_structured(DECOMPOSE_MODEL, split_messages(question), SubQuestions)
    subs = parts.sub_questions
    if len(subs) < 2:
        return Split(subs, retrieve(question, k), 1, result)
    return Split(subs, in_turns([retrieve(sub, k) for sub in subs], k), len(subs), result)
