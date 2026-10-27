# RAG Playground

A controlled study of which RAG techniques improve retrieval and answer quality, changing one variable at a time on two stacks (OpenAI Vector Store, Qdrant + nomic). FastAPI + React, deployed with Docker and a CI evaluation gate.

## How the evaluation works

**[docs/evaluation.md](docs/evaluation.md)** explains the project from scratch:
- the data (a fictional Salesforce consulting firm's documents: company policies, staff directories, services, clients and deployment runbooks);
- the 240 test questions;
- the experiment;
- how each metric is computed (MRR, Recall@K, nDCG, faithfulness and the others), with a worked example;
- what counts as an improvement.

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
