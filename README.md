# RAG Playground

A controlled study of which RAG techniques improve retrieval and answer quality, changing one variable at a time on two stacks (OpenAI Vector Store, Qdrant + nomic). FastAPI + React, deployed with Docker and a CI evaluation gate.

## How the evaluation works

**[docs/evaluation.md](docs/evaluation.md)** explains the project from scratch:
- the data (a fictional consulting firm's documents: company policies, staff directories, services, clients and deployment runbooks);
- the 240 test questions;
- the experiment;
- how each metric is computed (MRR, Recall@K, nDCG, faithfulness and the others), with a worked example;
- what counts as an improvement.

**[docs/user-manual.md](docs/user-manual.md)** explains how to use the dashboard.

## The ladder

The ladder is a fixed sequence of tests, run on each stack separately on the 192 dev questions. Each step changes one setting, keeps the best value, and the next step starts from there.

| Step | What it tests | Options |
| --- | --- | --- |
| S0 | Baseline | LlamaIndex default settings |
| S1 | Chunk size | 100, 200, 400, 800, 1024, 1600 tokens |
| S2 | Overlap | 0%, about 20%, 25% |
| S3 | Top-K | 2, 4, 6, 8 |
| S4 | LLM-enriched chunks | On or off |
| S5 | Reranking | On or off |
| S6 | System prompt | Up to 4 versions |

S1, S2, S3 and S6 use the tie rule below. S4 and S5 are kept only if their gain is real, since they add cost to every use. S7 then reports a stronger answer model as a cost trade-off.

**The system prompt:** every run from S0 to S5 uses this same `default` version, on both stacks. Each answer is built from this prompt, the question and the chunks retrieved for it. Holding the prompt fixed means a change in score comes from the setting under test, not from the wording. S6 is the only step that changes it, and later steps use the version S6 keeps.

```
You are the internal knowledge assistant of Larkspur Cloud Partners, a consulting firm that delivers cloud CRM projects for its clients.
Staff ask you questions about the company and its policies, its employees, its services, its clients and its deployment runbooks.
Each question comes with context documents retrieved from the company knowledge base.
Answer using only these context documents. Do not use outside knowledge and do not guess.
If the context does not contain the answer, say that the information is not in the knowledge base.
When the answer needs a calculation, such as a duration or a total, compute it from the facts in the context.
Answer concisely, in a few sentences at most.
```

**Why use it:**
- **Clear causes:** one change per step, so each gain has one cause.
- **Fair tests of costly techniques:** enrichment and reranking must show a real gain to stay.
- **Less self-deception:** options and rules are fixed before the results, and the 48 held-out questions, never used to choose, confirm the final result.
- **Low cost:** about 16 runs per stack, instead of 1,152 for every combination.
- **A fair comparison:** both stacks face the same steps, questions and rules.

**Limits:** the ladder never goes back, so it finds a good configuration, not a proven best one. A different order of steps could end elsewhere.

**Tie rule:** among runs that pass every minimum quality gate, the run with the highest accuracy leads. A run counts as tied with it if a paired bootstrap (a resampling test over the same questions) cannot show that the leader is really better, and the cheapest tied run wins. So a winner can score slightly below the leader: Stack A's S1 kept 800 tokens (4.208) over 1024 tokens (4.313), and the chart dips there.

The rule is kept for two reasons. It avoids paying for a gain that may be luck, which matters most at S3, where K=8 costs about 2.5 times K=2 (projected). It was also fixed before any results, and changing it after seeing them would weaken the study. Its cost is that a small real gain can be given up. See T08, T09 and T50 in [decision.md](decision.md).

## How far to trust the judge

Answers are scored by an LLM judge (`gemini-3.5-flash-lite`), so the judge was tested before any comparison relied on it. One person graded 30 of its answers blind, 15 from each stack, without seeing its scores or which stack wrote the answer. The judge had used only scores 1, 3 and 5, so the sample took an equal number of each, and the rules were fixed before any grading.

| Check | Result |
| --- | --- |
| Pass/fail agreement (target 80%) | 80%, 24 of 30 (95% interval 63% to 90%) |
| Scores within 1 point | 83%, 25 of 30 |
| Judge's passes confirmed | 8 of 10 |
| Judge's fails confirmed | 16 of 20 |

What to expect:
- The judge is good enough to compare settings, but it met the target with no margin. The check is light: one grader and 30 answers.
- The sample is balanced by score, so 80% describes that mix, not every answer.
- Read accuracy together with completeness on multi-part questions: a half answer scored 5 for accuracy on one question and 3 on a near-identical one.
- Small slips can score differently: the same one-too-high day count scored 1 on one answer and 3 on another.
- Accuracy is the only score checked by a person. Faithfulness was not.

See T20 and T48 in [decision.md](decision.md).

## Limitation: one dataset

The app runs on the one dataset in this repository and has no data import. Using other documents is a developer job: they must be Markdown, scoring needs new prepared questions and reference answers, and the judge must be calibrated again. Chunk sets and indexes are not yet tied to a dataset, so the old ones must be cleared first, or a run could search the old documents. See D28 in [decision.md](decision.md).

## Run locally

```
cd backend && uv run uvicorn rag_playground.main:app --reload
cd frontend && npm run dev
```

## Run in Docker

```
docker compose -f deploy/docker-compose.yml -p rag-playground-dev up -d --build
curl http://127.0.0.1:8000/api/health
```

## Tests

```
cd backend && uv run pytest
```
