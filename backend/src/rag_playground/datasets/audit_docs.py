"""Per-document fidelity audit by an independent model (T32)."""

import json
from enum import StrEnum

from pydantic import BaseModel

from rag_playground.datasets.documents import DocSpec
from rag_playground.llm.openrouter import chat_structured
from rag_playground.settings import AUDIT_MODEL

INSTRUCTIONS = """You check one knowledge-base document against the facts it was written from.
Questions with exact gold answers, including questions whose answer must be "not in the knowledge base", are generated from these facts, so the document must state the facts exactly and nothing more about the entity.

Report every issue of these kinds:
- added: the document states something specific about this firm, its people, clients, services or runbooks that is not in FACTS, even without numbers (for example a meeting cadence, a tool, a responsibility, a reason, a result).
- altered: a fact in the document differs from FACTS in any way (value, person, service, date, scope, condition).
- omitted: a fact in FACTS is missing from the document.

Generic background that makes no claim about this specific firm or its entities (for example what a Salesforce feature does in general, or why a practice is useful in general) is allowed and must not be reported.
Quote the document text for added and altered issues. Return an empty list only if there is no issue."""


class DocIssueKind(StrEnum):
    ADDED = "added"
    ALTERED = "altered"
    OMITTED = "omitted"


class DocIssue(BaseModel):
    kind: DocIssueKind
    fact: str
    document_text: str
    explanation: str


class DocAudit(BaseModel):
    issues: list[DocIssue]


def audit_doc(spec: DocSpec, markdown: str) -> tuple[DocAudit, float]:
    """Return the fidelity issues of one document and the cost in USD."""
    content = (f"Document kind (given, not a fact to check): {spec.kind}\nTitle (given): {spec.title}\n\n"
               f"FACTS:\n{json.dumps(spec.facts, indent=1, ensure_ascii=False)}\n\nDOCUMENT:\n{markdown}")
    messages = [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": content}]
    report, result = chat_structured(AUDIT_MODEL, messages, DocAudit, max_tokens=32000)
    return report, result.cost_usd
