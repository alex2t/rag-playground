"""Stage 3 of the dataset (T34): generate test candidates from KB documents."""

from rag_playground.datasets.candidates import NOT_IN_KB, Candidate, CandidateBatch
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import GENERATOR_MODEL

SYSTEM = """You write evaluation questions for a RAG system over the internal knowledge base of a fictional Salesforce consulting firm.
Each question gets a gold reference answer and the gold documents that contain the answer.

Rules for every question:
- Ask it as an employee of the firm would, in natural language. Never mention document names, file paths or "the document".
- It must have exactly one correct answer, stated in the given documents (or, for unanswerable questions, stated nowhere in the knowledge base). Name the entity precisely so the question cannot refer to anything else.
- The question names entities only; it never states a fact from the documents (no values, dates, counts or other attributes), so the answer must come from retrieval.
- reference_answer: concise and complete, using the values exactly as the documents state them.
- source_docs: exactly the given document paths that are needed to answer.
- keywords: 1-3 answer values, each copied verbatim from the gold documents and also written verbatim in reference_answer: a name, term, amount, count, date or duration (for example "Adelaide", "142 products", "2019-03-04", "seven years"). Never a label or field name (such as "Owner" or "Fixed fee"), never a lone single digit, never the entity the question names.
- Avoid questions whose answer is also stated in other documents of the knowledge base (for example a service name, which the company overview also lists, or a service launch year, which the company history also states).

Categories:
- direct_fact: one stated fact (who, what, which, where).
- numerical: the answer is a number stated in the document (amount, count, percentage, duration).
- temporal: about time: which of two stated events came first, the exact time elapsed between two dates the document states, or when something happened. Prefer order and elapsed-time questions; a policy frequency is not temporal.
- exact_term: the answer is an exact name, error message, setting, field or certification as written; tests exact wording.
- multi_doc: the answer is worked out by combining a value that only the first document states with a value that only the second document states, by comparing them or computing with them (for example, whether a client project's figure stays within the limit its service states; the years between a client relationship starting and its account lead joining the firm; how long a runbook's owner had been at the firm when the runbook was last reviewed; the certification bonus an employee's certifications earn under the handbook). The answer gives both values and the result. Never two unrelated facts joined with "and".
- comparative: compares the two entities on a stated attribute (higher, earlier, longer); the answer names the entity and both values."""

SINGLE_TASK = """For each document below, write two questions for each of these categories that the document supports: direct_fact, numerical, temporal, exact_term. The two questions of a category ask about different attributes, and each question about a different fact than the document's other questions. Skip a question if the document cannot support a good one. Each question uses only its own document.

{docs}"""

PAIR_TASK = """For each pair of documents below, write two {category} questions on different facts, each needing both documents of the pair. source_docs must list both paths.

{pairs}"""

AVOID = """Each question must still follow its category rules, and combine values that none of these existing questions uses:
{existing}"""

TOPUP_TASK = """For each document below, write up to 2 {category} questions that the document supports, using only its own document. Skip a document that cannot support a good {category} question.
Do not repeat or rephrase any of these existing questions:
{existing}

{docs}"""

UNANSWERABLE_TASK = """Here is the whole knowledge base:

{kb}

Write {n} unanswerable questions: plausible questions an employee might ask whose answer is stated nowhere in this knowledge base.
- Half ask about entities that do not exist (an employee, client, service, office or runbook with an invented name).
- Half ask about existing entities for information the knowledge base never states (for example a client's number of employees or a policy that does not exist).
For each: category unanswerable, reference_answer exactly "{not_in_kb}", source_docs empty, and keywords: 1-3 distinctive terms from the question that appear nowhere in the knowledge base (the invented name, or the missing attribute such as "parking")."""


def section(path: str, text: str) -> str:
    return f"=== {path} ===\n{text}"


def ask(task: str) -> tuple[list[Candidate], float]:
    """One structured generation call."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    batch, result = chat_structured(GENERATOR_MODEL, messages, CandidateBatch, max_tokens=64000)
    return batch.candidates, result.cost_usd


def single_doc_candidates(paths: list[str], kb: dict[str, str]) -> tuple[list[Candidate], float]:
    return ask(SINGLE_TASK.format(docs="\n\n".join(section(p, kb[p]) for p in paths)))


def topup_candidates(paths: list[str], category: str, existing: list[str], kb: dict[str, str]) -> tuple[list[Candidate], float]:
    """Extra single-document candidates for one category, avoiding existing questions."""
    docs = "\n\n".join(section(p, kb[p]) for p in paths)
    return ask(TOPUP_TASK.format(category=category, existing="\n".join(f"- {q}" for q in existing), docs=docs))


def pair_candidates(pairs: list[tuple[str, str]], category: str, kb: dict[str, str],
                    existing: list[str] | None = None) -> tuple[list[Candidate], float]:
    """Two questions per pair; with `existing`, each must test a fact those questions do not use."""
    blocks = [f"--- Pair {i} ---\n{section(a, kb[a])}\n\n{section(b, kb[b])}" for i, (a, b) in enumerate(pairs, 1)]
    task = PAIR_TASK.format(category=category, pairs="\n\n".join(blocks))
    if existing:
        task += "\n\n" + AVOID.format(existing="\n".join(f"- {q}" for q in existing))
    return ask(task)


def unanswerable_candidates(n: int, kb: dict[str, str]) -> tuple[list[Candidate], float]:
    kb_text = "\n\n".join(section(p, t) for p, t in kb.items())
    return ask(UNANSWERABLE_TASK.format(kb=kb_text, n=n, not_in_kb=NOT_IN_KB))
