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
