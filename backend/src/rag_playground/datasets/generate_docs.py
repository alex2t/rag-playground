"""Stage 2 of the dataset (T32): write each KB document from its facts, retrying until the number check passes."""

import json

from rag_playground.datasets.doc_checks import number_problems
from rag_playground.datasets.documents import DocSpec
from rag_playground.llm.openrouter import chat
from rag_playground.settings import GENERATOR_MODEL

MAX_ATTEMPTS = 3

SYSTEM = """You write one internal document for the knowledge base of a fictional Salesforce consulting firm.
The document will be retrieved by a RAG system. Questions with exact gold answers are generated from its facts, including questions whose correct answer is "not in the knowledge base". So the document must state its facts exactly and nothing else about the firm or its entities.

Rules:
- Markdown. Start with the title as a level-1 heading. Use headings, lists and tables where they help a reader.
- Include every fact given in FACTS, and state each fact exactly once: no summary tables, quick-reference sections or recaps that repeat facts stated elsewhere in the document.
- Write every number as digits, exactly as given (thousands separators are allowed). Write every date exactly as given, in YYYY-MM-DD format.
- Add nothing about the firm, its people, clients, services, offices, policies or runbooks that is not in FACTS: no responsibilities, procedures, contacts, advice, reasons, results, usage, rankings or comparisons ("longest-standing", "first", "main", "key"), and no relationships between facts that FACTS does not state.
- Do not compute values from the facts (durations between dates, totals, percentages, counts).
- Do not add filler. You may add a short generic sentence about what a Salesforce product or practice is in general, only if it says nothing about this firm or its entities.
- Put steps in numbered markdown lists; never refer to step numbers in prose.
- Return only the markdown document."""

TASK = """Document kind: {kind}
Title: {title}

FACTS:
{facts}"""

RETRY = """Your document failed the exact check of numbers and dates:
{problems}
"added" means the value is not in FACTS; "missing" means a value from FACTS is absent or written differently.
Rewrite the whole document so that it passes. Return only the markdown document."""


def write_doc(spec: DocSpec) -> tuple[str, list[str], float]:
    """Write one document; return the markdown, its remaining problems (empty if accepted) and the cost."""
    task = TASK.format(kind=spec.kind, title=spec.title, facts=json.dumps(spec.facts, indent=1, ensure_ascii=False))
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    cost = 0.0
    for _ in range(MAX_ATTEMPTS):
        result = chat(GENERATOR_MODEL, messages)
        cost += result.cost_usd
        problems = number_problems(result.text, spec.facts)
        if not problems:
            break
        messages += [{"role": "assistant", "content": result.text},
                     {"role": "user", "content": RETRY.format(problems="\n".join(problems))}]
    return result.text.strip() + "\n", problems, cost
