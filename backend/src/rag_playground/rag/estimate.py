"""Cost estimate of a run before it starts (decision.md T43, a custom formula).

Input tokens are counted on the real messages, built with the real templates and questions; each retrieved chunk
is a filler of the chunk set's average length. Output tokens are assumed (plan.md 1.3), except the reranker's,
whose reply is always the list of every candidate number. Prices are OpenRouter's live per-token prices.
Reasoning tokens (gpt-6.1-sol) cannot be predicted and are not counted, so such estimates are low."""

import json
from statistics import fmean

from llama_index.core.utils import get_tokenizer

from rag_playground.chunking.chunk_sets import Chunk
from rag_playground.datasets.schema import TestCase
from rag_playground.llm.models import model_info
from rag_playground.rag.answer import answer_messages
from rag_playground.rag.prompts import PromptVersion
from rag_playground.rag.rerank import rerank_messages
from rag_playground.scoring.judging import answer_messages as grade_messages
from rag_playground.scoring.judging import faithfulness_messages
from rag_playground.settings import JUDGE_MODEL, RERANK_CANDIDATES, RERANK_MODEL
from rag_playground.stacks.hits import Hit

ANSWER_TOKENS = 150  # assumed answer length (plan.md 1.3)
JUDGE_TOKENS = 200  # assumed length of each judge reply (plan.md 1.3)
MESSAGE_OVERHEAD = 4  # tokens per chat message, as in OpenAI's cookbook "How to count tokens with tiktoken"


def filler(tokens: int) -> str:
    """A text of exactly `tokens` tokens."""
    return " the" * tokens


def count(messages: list[dict]) -> int:
    """Input tokens of a chat request."""
    tokenize = get_tokenizer()
    return sum(len(tokenize(m["content"])) + MESSAGE_OVERHEAD for m in messages)


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    """Dollars for one call at the model's live prices."""
    info = model_info(model)
    return input_tokens * info.prompt_usd_per_token + output_tokens * info.completion_usd_per_token


def question_cost(test: TestCase, prompt: PromptVersion, answer_model: str, top_k: int, rerank: bool,
                  chunk_tokens: float) -> float:
    """Estimated dollars for one question: optional rerank, answer, and the judge's two calls."""
    chunk = filler(round(chunk_tokens))
    hits = [Hit(f"c{i}", "doc.md", 1.0, chunk) for i in range(top_k)]
    answer = filler(ANSWER_TOKENS)
    cost = price(answer_model, count(answer_messages(prompt, test.question, hits)), ANSWER_TOKENS)
    cost += price(JUDGE_MODEL, count(grade_messages(test, answer)), JUDGE_TOKENS)
    cost += price(JUDGE_MODEL, count(faithfulness_messages(test, [chunk] * top_k, answer)), JUDGE_TOKENS)
    if rerank:
        candidates = [Hit(f"c{i}", "doc.md", 1.0, chunk) for i in range(RERANK_CANDIDATES)]
        reply = json.dumps({"ranking": list(range(1, RERANK_CANDIDATES + 1))})
        cost += price(RERANK_MODEL, count(rerank_messages(test.question, candidates)), len(get_tokenizer()(reply)))
    return cost


def run_cost(tests: list[TestCase], prompt: PromptVersion, answer_model: str, top_k: int, rerank: bool,
             chunks: list[Chunk]) -> float:
    """Estimated dollars for a run over `tests` on this chunk set."""
    chunk_tokens = fmean(c.tokens for c in chunks)
    return sum(question_cost(t, prompt, answer_model, top_k, rerank, chunk_tokens) for t in tests)
