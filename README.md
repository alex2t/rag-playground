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
