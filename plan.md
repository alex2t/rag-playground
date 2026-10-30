# RAG Playground - Plan

## Goal

A study of RAG. It shows which RAG techniques work and which do not, measured with best-practice evaluation, and how such a system is deployed and gated in production.

The demo proves four things:

1. **A RAG system can be improved.** On each stack separately, we start from the documented out-of-the-box defaults of a widely used RAG framework (LlamaIndex), change **one variable at a time**, and re-run the same evaluation. This answers a practical question: what do you get by shipping the defaults, and what does each tuning step add?
2. **Stacks can be compared fairly.** With identical chunks and settings, we measure which stack does better and by how much.
3. **The RAG can be trusted.** It refuses questions it cannot answer instead of inventing an answer, and every claim is checked against the retrieved context.
4. **Quality is protected in deployment.** The evaluation is a release gate in CI/CD: a change that lowers quality cannot reach production.

The app runs only on a Hostinger VPS, in Docker. Every architecture and test decision, with its reasons and trade-offs, is in `decision.md`.

### What this project adds beyond a basic RAG evaluation
- Two complete stacks, hosted OpenAI and self-hosted open source, fed with identical chunks.
- The same improvement ladder on both stacks, plus a head-to-head comparison.
- **Gold source labels:** retrieval is scored on whether the right document came back, not only on keyword matches.
- **Dev / held-out split:** we tune on 192 dev questions, and the final result is confirmed on 48 held-out questions the tuning never saw.
- **Unanswerable questions** and refusal metrics.
- **Judge calibration:** the LLM judge is checked against human grades.
- **Paired statistical testing:** a change only counts as an improvement when its confidence interval is above zero.
- **Per-question diff:** shows which questions a change fixed or broke.
- **Controlled variables:** temperature fixed at 0, a pinned judge, a fixed prompt.
- **Reproducibility metadata** on every run.
- **CI/CD with an evaluation gate**, staging and production environments, and basic observability.

---

## Confirmed decisions

The reasons for each decision are in `decision.md`. Items marked *(proposed)* have a default that needs review.

| Area | Decision |
|---|---|
| Stack A | OpenAI Vector Store (OpenAI embeddings, hosted). `OPENAI_API_KEY`. |
| Stack B | Qdrant + fastembed `nomic-ai/nomic-embed-text-v1.5` (768 dims, 8192-token context, ONNX, no torch). Self-hosted. |
| Chunking | LlamaIndex's `SentenceSplitter`, unmodified, with `cl100k_base` tokens, makes the chunks for **both** stacks; chunk sets are saved to `var/chunk_sets/` and reused (T39). Stack A gets one file per chunk, so OpenAI does not split it again. |
| LLMs | Answer, judge, rerank and enrichment calls go through OpenRouter (`OPENROUTER_API_KEY`). |
| Answer models | 3 models: `openai/gpt-4.1-nano` (cheap), `openai/gpt-4.1-mini` (mid), `openai/gpt-6.1-sol` (latest). |
| Judge model | `google/gemini-3.5-flash-lite` (confirmed 2026-10-27): a different model family from the answer models, pinned to its exact version, and calibrated against human grades. |
| Baseline (S0) | LlamaIndex out-of-the-box defaults: `SentenceSplitter` with 1024-token chunks and a 200-token overlap (checked in the 0.14.25 code), K=2, no reranking, `gpt-4.1-nano` (T27 revision). |
| Improvements | Ladder: chunk size, overlap, top-K, LLM chunking/enrichment, reranking, system prompt version (S6, T36 revision 2026-10-29), and a stronger LLM (presented as a cost trade-off). Outside the ladder (dashboard and sweeps): hybrid search (T37). |
| Dashboard settings | Stack A, Stack B or both (side by side) (T40). Chunk size 64-2,048 tokens, overlap 0-50%, top-K 1-8 (T45), chunking method, reranking, answer model, system prompt version, and each stack's own search settings: Stack A OpenAI's options (ranker, hybrid weights, score threshold), Stack B hybrid on/off. Each stack runs independently; nothing is mapped between them (T40 revision 2026-10-29). Every setting is chosen by the user, with no hidden defaults (T40). Missing chunk sets are built and indexed on demand after an estimate and confirmation (T35). |
| System prompt | Written by the user on the dashboard as named, immutable versions, any number; each run stores the version and hash. The default version is used from S0 to S5 and in the CI gate; ladder step S6 picks the best of at most 4 versions on dev questions; held-out runs use the default or a version with a finished dev run (T36 revision 2026-10-29). |
| Hybrid search | Stack B: BM25 sparse vectors (fastembed `Qdrant/bm25`) + nomic dense vectors, fused with RRF. Stack A: OpenAI's `hybrid_search` weights with `ranker: none` (checked live in Step 4, T37). |
| Embedding map | 2D t-SNE images (scikit-learn) of one chunk set for both stacks, for the report; Stack A chunks re-embedded with the vector store's OpenAI embedding model (T38). |
| Data | Synthetic KB only in phase 1. `rag-mini-wikipedia` is moved to phase 2. |
| Test set | 240 generated tests: **192 dev** (tuning) + **48 held-out** (final confirmation). About 10% of each split is unanswerable. Each test has its gold source document(s). |
| Best-RAG rule | Primary metric (accuracy) plus minimum gates. No invented composite score. |
| Metrics display | The report shows all 8 core metrics. The live dashboard defaults to 4 headline metrics, with a "show all" toggle. |
| Automated evaluation | Pick the index (stack, chunk size, overlap, method), K, hybrid search, reranking on/off, model and system prompt version, then one click runs the 192 dev questions. |
| Manual testing | Ask page: free-form questions, or any test question shown with its reference answer, gold sources and scores. |
| Temperature | Not a variable. Fixed at 0 for answers, judge and reranker. Not sent to models that reject it (`gpt-6.1-sol`); those runs are flagged. |
| Sweeps | One variable at a time only, on the 192 dev questions. Cost estimate and confirmation first. |
| Budget | `BUDGET_USD=60` for all evaluation spend in production, and `BUDGET_USD=5` in staging (D15). Spend is recorded per paid call in a `spend` table (T44). The estimate counts real input tokens, assumes output tokens, and uses live prices (T43). |
| Backend / Frontend | FastAPI (Python 3.12, `uv`) / Vite + React + TS + Tailwind + Recharts. |
| Packaging | One image per release: the React build is copied into the backend image and served by FastAPI. |
| Environments | `staging` and `prod` on the same VPS, as two compose projects on separate subdomains. |
| Edge | One shared Caddy: TLS, basic auth, routes each subdomain to its environment. |
| CI/CD | GitHub Actions: test, build, push to GHCR (tagged with the git SHA), deploy to staging, smoke test and evaluation gate, manual approval, then deploy the same image to prod. Rollback = redeploy the previous tag. |
| Storage | SQLite in a Docker volume, one per environment. Runs and results are permanent: the database refuses any edit, deletion or replacement, and a run changes only once, from running to finished (D21). |
| Long jobs | Background job; the UI polls `GET /api/jobs/{id}`. |
| Observability | Structured JSON logs and an Ops page (spend against budget, error rate, p95 latency). |
| Secrets | `.env` per environment on the VPS (owner-only permissions, never committed). CI secrets in GitHub Actions secrets. |

Any new architecture or test decision must be confirmed with the user, then added here and to `decision.md`.

---

## 1. Data

### 1.1 Synthetic knowledge base
- One script generates internal documents for a **fictional** Salesforce consulting firm.
  - Folders: `company/`, `employees/`, `services/`, `clients/`, `deployment-runbooks/`.
  - 48 markdown files (T32), about 270 KB in total.
- The same script generates `tests.jsonl` with **240** tests. Each test has:
  - `question`, `reference_answer`, `category`
  - `source_docs`: the gold document paths the answer comes from (empty for unanswerable questions)
  - `keywords`: secondary signal
  - `split`: `dev` or `heldout`
- Categories: `direct_fact`, `multi_doc`, `numerical`, `temporal`, `comparative`, `exact_term`, `unanswerable`.
- **Unanswerable** questions sound plausible but their answer is not in the KB, for example the name of an employee who does not exist. Their reference answer is "not in the knowledge base".
- **Split:** stratified by category with seed 42.
  - **192 dev** questions (20 unanswerable), used for every run, sweep and ladder decision.
  - **48 held-out** questions (5 unanswerable), run only on the S0 baseline and on the final best configuration.
- **Generator:** `anthropic/claude-sonnet-5.5`, a third model family (T28).
- **Method (T29):** `world.json` first, then one markdown document per world entity, then the questions with their gold `source_docs`.
- **Categories (T30):** 25 `unanswerable`, plus 37 or 38 for each of the other six, except `temporal` 35 and `multi_doc` 30 (revision 2026-10-27).
- **Location (D20):** `backend/data/synthetic/` (`world.json`, `kb/`, `tests.jsonl`), committed after review.
- Cost is about $3, run once. You review the output by hand, then commit it.

### 1.2 Phase 2 (not in phase 1): `rag-datasets/rag-mini-wikipedia`
- Source: `https://huggingface.co/datasets/rag-datasets/rag-mini-wikipedia` (CC-BY-3.0).
- Added only after phase 1, as an external check against bias from our self-generated data.

### 1.3 Cost of one run (measured 2026-10-29)

Measured on runs 2-4 (10 dev questions each, S0: 1,024-token chunks, K=2, no reranking, `gpt-4.1-nano`; Stack A with OpenAI's default search, Stack B plain vector search). Run 1 is left out: its Stack A search was broken (`fix.md`, 2026-10-29).
- Per question: about **$0.0012** per stack (runs: $0.00120, $0.00125, $0.00111). The judge (`gemini-3.5-flash-lite`, $0.30 / $2.50 per million input / output tokens, read from the spend rows) is about 85-90% of it.
- Tokens per question: the answer model reads about 1,500 and writes about 30; the judge's two calls read about 1,250 each and write about 60 each.
- Each extra chunk (K + 1) adds about 700 input tokens to the answer and to the judge's faithfulness call: about +$0.0003 per question.

| Run | Cost per stack | Source |
|---|---|---|
| 192 dev questions, `gpt-4.1-nano`, K=2 | about $0.23 | measured per question × 192 |
| 192 dev questions, `gpt-4.1-nano`, K=8 | about $0.55 | projected (+700 tokens per chunk) |
| 192 dev questions, `gpt-4.1-mini`, K=2 | about $0.32 | projected from its list price ($0.40 / $1.60 per million) |
| 192 dev questions, `gpt-6.1-sol`, K=2 | $2.50 or more | not measured; hidden reasoning tokens add to it |
| Reranking on | about +$0.27 | projected: the reranker reads 20 candidates (about 14,000 tokens) per question |
| 48 held-out questions, `gpt-4.1-nano`, K=2 | about $0.06 | measured per question × 48 |

Time: questions run one at a time; retrieval and answer take about 2-3.5 s per question, the judge comes on top. A full run's time is not measured yet.

Fixed costs:
- Qdrant + fastembed: $0.
- OpenAI Vector Store storage: free under 1 GB.
- Stack A embedding: under $0.05 per build.
- Enrichment: about $1, once.
- Stack A searches: possibly billed by OpenAI (about $2.50 per 1,000 searches if so, about $0.48 per 192-question run); being checked. They are billed to the OpenAI account and are not counted in `BUDGET_USD`.

The app's estimate (T43) is what counts before a run: checked on batch 2 (10 questions it was not fitted to), it was 12% below the real cost on Stack A and 1% below on Stack B, within the 50% the plan allows.

### 1.4 Budget for the experiments (production, cap $60)

Projected from the measured costs above.

| Item | Cost |
|---|---|
| Ladder S0-S7 on both stacks (about 18 runs per stack, mostly `gpt-4.1-nano`, K up to 8; S7 with `gpt-6.1-sol`) | about $18 |
| One-variable sweeps on both stacks (about 13-15 runs per stack) | about $10 |
| Held-out confirmation (baseline + best, both stacks, 48 questions) | about $1 |
| Enrichment + index builds | about $1 |
| Spare for re-runs and live-demo questions | about $30 |
| **Total** | **about $60** |

The CI gate runs in staging, which has its own $5 cap: 20 questions, about $0.03 per deploy (1.3).

---

## 2. Experiment variables

| Variable | Values |
|---|---|
| Stack | `A_openai`, `B_qdrant_nomic` |
| Chunk size (tokens) | Ladder sweep: 100, 200, 400, 800, 1024, 1600. 1024 is the LlamaIndex default used by the S0 baseline. Dashboard: any value from 64 to 2,048 (T35). |
| Overlap | S0: 200 tokens (the LlamaIndex default). In the chunk-size sweep the overlap keeps S0's share, 200/1024 (about 20%). S2 picks the best of {0%, about 20%, 25%} at S1's size (T24 revision). Dashboard: 0-50% (T35); the API takes overlap in tokens and the dashboard converts a percentage with `round(size * pct / 100)`. |
| Chunking method | `fixed`, `llm_enriched` (an LLM adds a headline and summary to each meaningful chunk) |
| Top-K | Maximum 8 (T45): the KB is small (48 documents, about 730 tokens each). Ladder sweep: 2, 4, 6, 8. Dashboard: 1-8. Matters most for `multi_doc` questions and long documents, where one subject is spread across several chunks. |
| Hybrid search | off / on (BM25 + vector, fused with RRF). Dashboard and sweeps only, not a ladder step (T37). |
| System prompt | Named versions written by the user. Ladder: the default from S0 to S5, then S6 = best of at most 4 versions on dev questions. Dashboard and sweeps: any version (T36 revision 2026-10-29). |
| Reranking | off / on. When on: retrieve 20 candidates, an LLM reranker (`gpt-4.1-nano`, temperature 0) reorders them, and the top K are kept (accepted 2026-10-28, T21). |
| Answer LLM | `openai/gpt-4.1-nano`, `openai/gpt-4.1-mini`, `openai/gpt-6.1-sol` (IDs checked on OpenRouter on 2026-10-26) |

**Controlled (fixed) variables:**
- Temperature 0 for answer, judge and reranker.
- System prompt: the default version from S0 to S5 and in the CI gate; from S6 on, the version S6 chose (T36 revision 2026-10-29).
- Judge model, pinned to its exact version (OpenRouter `canonical_slug`).
- The test split.

Temperature is sent only if the model's OpenRouter `supported_parameters` includes it. `openai/gpt-6.1-sol` does not, so its runs are flagged "temperature not controlled".

### Fairness rules
- **Identical chunks:** one chunk set per `{method}__c{size}__o{overlap}`, made by LlamaIndex's `SentenceSplitter` (T39) and saved to `var/chunk_sets/`. Both stacks index that same set.
- **Stack A ingest:** each chunk is uploaded as its own file, with the attributes `source`, `doc_type` and `chunk_id`, and the static chunking strategy `max_chunk_size_tokens=4096`, `chunk_overlap_tokens=0`.
- **Stack B ingest:** nomic needs prefixes: `search_document: ...` for chunks and `search_query: ...` for queries.
- **Context length:** every chunk size fits within both embedding models' context.
- **Same everything else:** prompt, answer LLM, judge, K, reranker and test split.
- **Known asymmetry (T12):** OpenAI vector store search may apply its own ranker. Verify this in Step 4, try to switch it off, and record the settings. **Every head-to-head result in the report must state this.**

---

## 3. Story mode

### 3.1 The improvement ladder (run on each stack, on the 192 dev questions)
Each step changes **one** thing compared with the step before.

| Step | Change | Configuration |
|---|---|---|
| S0 | Baseline: framework defaults | LlamaIndex defaults: `SentenceSplitter` chunks of 1024 tokens, 200-token overlap, K=2, no reranking, `gpt-4.1-nano` (T27 revision) |
| S1 | Chunk size | Best size from the chunk-size sweep |
| S2 | Overlap | Best of {0%, about 20%, 25%} from the overlap sweep, at S1's size |
| S3 | Top-K | Best of K = {2, 4, 6, 8}, at S2's chunk set (T45) |
| S4 | Chunking method | `llm_enriched` |
| S5 | Reranking | Retrieve 20, rerank, keep the top K (S3's K) |
| S6 | System prompt | Best of at most 4 prompt versions written before the step runs, on dev questions only (T36 revision 2026-10-29) |
| S7 | Answer LLM | A stronger model. Presented as a **cost trade-off** ("accuracy +X for cost ×Y"), not as a RAG technique |

The ladder is stored as data in config.

### 3.2 Head-to-head
At every ladder step, Stack A and Stack B run with identical settings. One chart shows both stacks across S0 to S7: the climb within each stack, and the gap between them.

### 3.3 Held-out confirmation
After the ladder, S0 and the best eligible configuration are run on the **48 held-out** questions for each stack. The held-out numbers are the ones quoted as the final result. With only 48 questions their confidence intervals are wider, and the report says so.

### 3.4 Sweeps
- One variable at a time, with the other variables at the S0 baseline. For each stack: 6 sizes + 2 overlaps (0% and 25% at S1's size; the 20% run is reused from the size sweep) + 4 K + 3 models, minus combinations already run. That is about 13-15 runs, roughly $5 per stack (projected, 1.3).
- There is no full-grid mode, because it would exceed the budget.
- Guardrails:
  - The run count, cost and time are estimated first, and nothing starts until the user confirms.
  - Combinations already run are reused.
  - Nothing starts if it would exceed the remaining `BUDGET_USD`, and a running job stops cleanly at the cap.
- A 20-question **smoke test** exists only to check that a configuration works. It is excluded from Compare, Story and the findings.

---

## 4. Metrics

Each question is scored, and a run reports the mean. Retrieval metrics use **answerable** questions only. Refusal metrics use the judge's `refused` flag.

### 4.1 Retrieval metrics (primary signal: gold source documents)
`rank(d)` is the position of the first retrieved chunk whose `source` is gold document `d`.

| Metric | Formula | Origin |
|---|---|---|
| **MRR** | `1 / rank` of the first retrieved chunk from any gold document; 0 if none is in the top K. Averaged over questions. | Standard information-retrieval metric, TREC-8 QA track (Voorhees, 1999). Coverage of all gold documents is Recall@K's job (T06 revision). |
| **Recall@K** | Gold documents found in the top K / total gold documents | Standard information-retrieval metric |
| **nDCG@K** | DCG / ideal DCG, `DCG = sum(rel_i / log2(i + 1))`, relevance 1 if the chunk's source is gold | Järvelin & Kekäläinen (2002) |
| **Hit@K** | 1 if any gold document is in the top K | Standard information-retrieval metric |
| Keyword recall *(secondary)* | Keywords found in the top K / total keywords | Proxy, kept as a cross-check |

### 4.2 Answer metrics (LLM-as-judge, scale 1-5)

| Metric | Question asked to the judge |
|---|---|
| **Accuracy** | Is it factually correct against the reference answer? Any wrong fact scores 1. For an unanswerable question, a refusal scores 5 and any invented answer scores 1. |
| **Completeness** | Does it cover everything in the reference answer? |
| **Relevance** | Does it answer only the question asked? |
| **Faithfulness** | Is every claim supported by the retrieved context? |

The judge also returns `refused` (true/false) and short feedback.

### 4.3 Trust metrics
- **Correct refusal rate:** unanswerable questions that are refused / all unanswerable questions. Higher is better.
- **False refusal rate:** answerable questions that are refused / all answerable questions. Lower is better.

### 4.4 Operational metrics
- Latency per question (p50 and p95).
- Cost per question in USD.

### 4.5 What is shown where
- **Report:** all 8 core metrics (MRR, Recall@K, nDCG@K, Hit@K, Accuracy, Completeness, Relevance, Faithfulness), plus the trust and operational metrics.
- **Live dashboard:** by default, 4 headline metrics: **MRR, Recall@K, Accuracy, Faithfulness**. A "show all" toggle reveals the rest. When the app is shown live, use the 4-metric view.

### 4.6 How "best RAG" is decided
1. **Gates.** A run is eligible only if all of these hold:
   - MRR ≥ 0.75
   - Recall@K ≥ 0.80
   - faithfulness ≥ 4.0
   - correct refusal rate ≥ 0.80
   - Confirmed 2026-10-27 as a custom choice; reviewed after the first real runs (T08).
2. **Primary metric:** the highest mean accuracy among eligible runs.
3. **Tie-break:** if the accuracy difference is not significant, the cheaper run per question wins.

### 4.7 Is an improvement real?
- **Paired bootstrap** on per-question differences (accuracy, and MRR): 1,000 resamples, seed 42, 95% confidence interval.
- If the interval is above 0, the improvement is real. If it contains 0, it is not significant, and the report lists it under "what did not work".

### 4.8 Judge calibration
- After the first real runs, 30 judged answers are sampled, stratified by score. You grade them blind (without seeing the judge's scores).
- Report agreement as:
  - % of answers where the judge's accuracy is within ±1 of yours.
  - % agreement on pass/fail (accuracy ≥ 4).
- Target: ≥ 80% on pass/fail. If agreement is below target, switch the judge model and re-calibrate before running the ladder.

### 4.9 Colour bands in the UI

| Metric | Green | Amber | Red |
|---|---|---|---|
| MRR, nDCG, Recall, Hit@K, correct refusal rate | ≥ 0.90 | ≥ 0.75 | below that |
| Judge scores | ≥ 4.5 | ≥ 4.0 | below that |

---

## 5. Architecture

```
rag-playground/
  .github/workflows/ci.yml       test -> build -> push GHCR -> deploy staging -> gate -> approve -> deploy prod
  deploy/
    edge/                        shared Caddy compose project + Caddyfile (TLS, basic auth, subdomain routing)
    docker-compose.yml           app + qdrant; run as project rag-playground-staging or rag-playground-prod
    deploy.sh                    pull image tag, compose up, health check; rollback = previous tag
  .env.example                   OPENAI_API_KEY, OPENROUTER_API_KEY, BUDGET_USD, APP_ENV
  decision.md  plan.md  fix.md  CLAUDE.md
  backend/
    pyproject.toml
    Dockerfile                   multi-stage: node builds frontend -> python image with dist/ + API
    src/rag_playground/
      main.py                    FastAPI app, routers, static files
      settings.py                env vars + catalogue (models, sizes, ladder, gates, judge)
      datasets/                  synthetic loader, test schema, splits
      chunking/                  token splitter, LLM enrichment, chunk-set cache
      stacks/
        base.py                  VectorStack interface: index(chunk_set), search(query, k)
        openai_stack.py          Stack A
        qdrant_stack.py          Stack B (dense nomic + optional BM25 sparse, RRF fusion)
      llm/                       OpenRouter client, pricing, usage, temperature support
      rag/                       prompt versions, reranker, answer pipeline
      scoring/
        retrieval.py             MRR, Recall@K, nDCG, Hit@K, keyword recall
        judging.py               LLM-as-judge incl. refused flag
        trust.py                 refusal rates
        selection.py             gates, best run, paired bootstrap
        calibration.py           human vs judge agreement
      jobs.py                    background job runner
      store.py                   SQLite: chunk sets, indexes, prompt versions, runs, results, jobs, spend, calibration
      observability.py           JSON logging, request metrics
    tests/
    scripts/
      generate_synthetic.py
      eval_gate.py               CI gate: 20-question run, exit 1 if gates fail
      embedding_map.py           t-SNE 2D images of one chunk set, both stacks (T38)
  frontend/
    src/
      api/                       typed client, polling hook
      pages/                     Story, Ask, Evaluate, Compare, Build, Prompt, Sweep, Ops
      components/
```

### API (first draft)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog` | Options for the dropdowns |
| GET / POST | `/api/indexes` | List indexes / start a build job (any chunk size, overlap and method within the T35 ranges) |
| GET / POST | `/api/prompts` | List system prompt versions / save a new named version (T36) |
| POST | `/api/ask` | One question: answer, chunks, gold sources, reference answer and scores |
| POST | `/api/estimate` | Run count, cost and time |
| POST | `/api/runs` | Start an evaluation job: every setting plus `questions` = `dev`, `heldout` or `smoke` (20, round-robin, T46), all required (T40); refusals return 404, 409 or 422 with the reason (D25) |
| POST | `/api/sweeps` | Start a confirmed sweep |
| POST | `/api/story` | Run the ladder on one or both stacks |
| GET | `/api/jobs/{id}` | Status, progress, message, error |
| GET | `/api/runs`, `/api/runs/{id}` | Summaries / per-question results (with reproducibility metadata) |
| GET | `/api/runs/{id}/export` | CSV of per-question results |
| GET | `/api/compare?a={run}&b={run}` | Paired bootstrap and per-question diff |
| GET / POST | `/api/calibration` | Sample for human grading / submit grades and get agreement |
| GET | `/api/ops` | Spend against budget, error rate, latency |
| GET | `/api/health` | Health check, including the app version (git SHA) |

### Reproducibility metadata stored with every run
- Git SHA and image tag.
- Exact model IDs with OpenRouter `canonical_slug`, for the answer, judge and reranker.
- System prompt version name and hash, hash of the dataset and the split.
- Chunk-set id and stack settings, including hybrid search on/off and the OpenAI ranking options.
- `temperature_controlled` and the date.

---

## 6. Step-by-step build

Validate each step before starting the next one. Log bugs in `fix.md`. Record decisions in `decision.md`.

### Step 0 - Scaffold
- Repo layout, backend `uv init`, frontend Vite (React + TS), compose with `app` and `qdrant`, and `/api/health` returning the version.
- `/api/health` returns `{status, version, qdrant}`, with 503 when Qdrant is unreachable (D17).
- **Check:** health returns 200 in Docker locally, and Qdrant is reachable from the app. The same check on the VPS is deferred (D18).

### Step 1 - API connectivity
- OpenRouter client: chat, structured output, usage and cost, `supported_parameters`, `canonical_slug`.
- OpenAI vector store client: create, file batch, search, delete.
- fastembed with nomic.
- **Check (live tests):**
  - All 3 answer models and the judge reply.
  - The vector store round-trip works.
  - nomic returns 768-dimensional vectors.

### Step 2 - Dataset
- Generate the KB and 240 tests with gold `source_docs`, unanswerable questions and a stratified dev/held-out split. Review them by hand.
- **Check:**
  - Every `source_docs` path exists.
  - Each answerable test's keywords appear in its gold documents and in its reference answer (T34 revision).
  - Each document of a two-document test has a keyword the other lacks.
  - Unanswerable keywords appear nowhere in the KB.
  - No two tests test the same fact; no document kind fills more than 40% of a category (custom rules, T34).
  - Every test was accepted by the full-KB verification.
  - Category counts per split are printed.
  - The split is identical on every load.

### Step 3 - Chunk sets
- Any chunk size from 64 to 2,048 tokens and overlap from 0 to 50% (T35); a chunk set is built once per `{method}__c{size}__o{overlap}` and reused.
- **Check:**
  - Sizes or overlaps outside the ranges are rejected.
  - Chunk count goes down as size goes up.
  - No chunk exceeds its size by more than 2 tokens (a LlamaIndex behaviour measured over the full range, T39).
  - Consecutive chunks share at most the overlap + 2 tokens; with overlap 0 they share no text.
  - Chunks are in document order: each starts no earlier than the previous one and ends after it.
  - Every chunk is an exact piece of its document, and together the chunks cover the whole document in order (only whitespace left out).
  - A chunk set is built once and then loaded from `var/chunk_sets/`.

### Step 4 - Index both stacks from one chunk set
- **Status (2026-10-27): done** (`8a44b21`, `b47d17d`, `eca1605`). Stack B checks pass offline; Stack A live checks passed (run by the user). T12, T37 and T40 recorded; the vector store's embedding model is not documented by OpenAI (T38). Still open: the Stack A ranking values for the ladder (before Step 13).
- Record the OpenAI search ranking settings (T12).
- Hybrid search (T37): Stack B stores a BM25 sparse vector (fastembed `Qdrant/bm25`) next to the nomic dense vector and fuses both with RRF. Check whether OpenAI's vector store search has an equivalent hybrid mode, and record the answer.
- Record which OpenAI embedding model and dimensions the vector store uses, for the t-SNE map (T38).
- **Check:**
  - Both stacks report the same number of chunks.
  - With hybrid search on, an `exact_term` question whose exact string is in one chunk returns that chunk on Stack B.
  - A known question returns its gold document in the top 5 on both stacks.
  - Stack A returns chunk text identical to the stored text.

### Step 5 - Scoring
- **Status (2026-10-27): done** (`c79104b`, `fa6a526`). All checks below pass; the live judge checks were run by the user. Picking the best run (T08) moves to Step 6, when runs are stored.
- **Check (unit tests with hand-built inputs):**
  - MRR: rank 1 gives 1.0, rank 2 gives 0.5, absent gives 0. With two gold documents first found at ranks 2 and 4, MRR is 0.5 (the first one only).
  - Recall@K is 1/2 when 1 of 2 gold documents is retrieved.
  - nDCG is 1.0 with relevant chunks on top.
  - Unanswerable tests are excluded from retrieval metrics.
  - Refusal rates are correct on a hand-built set.
  - Gates reject faithfulness 3.9 and a refusal rate of 0.7.
  - Paired bootstrap: identical runs give an interval containing 0, and +1 on every question gives an interval above 0.
  - Live judge: the reference answer scores ≥ 4.5, a wrong answer gets accuracy 1, an invented fact scores low on faithfulness, and a refusal on an unanswerable question gets accuracy 5 with `refused = true`.

### Step 6 - Answer pipeline, reranker, evaluation job, estimate, metadata
- **Status (2026-10-30): done.** Built and committed: prompt versions, answer, reranker, runs and results (permanent, D21), pipeline, spend per call (T44), estimate (T43), budget guard, indexes and real search on both stacks (D24), the first real run (runs 1-4), the background job runner (D07), `POST /api/runs` (D25), WAL mode (D26), strict run requests (D27) and best-run selection (T08 details in `decision.md`). Every check below passes.
- Job runner (D07): one worker thread, one job at a time; `GET /api/jobs/{id}` returns status, progress, message and error; unfinished jobs are marked failed at startup.
- `POST /api/runs` (D25): every setting required, each stack its own search settings; a refused run stores nothing and returns its reason.
- Pipeline: retrieve (vector or hybrid), optional rerank, system prompt version, answer, judge, then store the row and the run metadata.
- System prompt versions (T36): a default version, saved edits are new immutable versions.
- **Check:**
  - Saving a prompt creates a new version; an existing version cannot be changed. A run stores its version name and hash.
  - A 10-question run stores 10 rows with full metadata, and progress reaches 1.0.
  - The reranker returns the same chunks in a new order.
  - `gpt-6.1-sol` runs are flagged `temperature_controlled = false`.
  - The estimate is within 50% of the actual cost.
  - Spend is recorded, and a run that would exceed the budget is refused.
  - First real run (user decision 2026-10-29): 10 dev questions with the S0 set-up on both stacks, run by the user (Stack B on Qdrant in Docker, D23).

### Step 7 - LLM chunking and enrichment
- **Check:**
  - Every original text is found in its source document.
  - A second build does not call the LLM again.

### Step 8 - Judge calibration
- Run one full dev evaluation, sample 30 answers, grade them blind in the UI, and compute agreement.
- **Check:** pass/fail agreement ≥ 80%. If not, change the judge and repeat this step. Record the result in `decision.md` (T07).

### Step 9 - Frontend (time-boxed)
Build in this order: **Story → Ask → Evaluate → Compare**, then Build, Sweep and Ops. Use one shared layout. Get it working before polishing.
- **Story page:**
  - Run the ladder on one or both stacks.
  - Accuracy and MRR per step, one line per stack, with confidence intervals and significance markers.
  - Held-out confirmation panel.
  - Best eligible run highlighted.
- **Settings panel (shared by Ask, Evaluate and Sweep, T35):**
  - Chunk size (64-2,048), overlap (0-50%), chunking method, top-K (1-8), reranking, answer model and system prompt version.
  - Each stack's own search settings (T40 revision 2026-10-29): Stack A shows OpenAI's options (ranker, the two hybrid weights, score threshold), Stack B its hybrid on/off switch.
  - A configuration whose chunk set is not built yet shows its estimate and builds it on confirmation.
- **Prompt page (T36):**
  - Write prompt versions: start from the default or any saved version, edit, save under a new name (any number); see the runs that used each version.
- **Ask page:**
  - Use the settings panel, then type a question or pick a test question.
  - Shows the answer, the chunks (source, rank, score) and the gold sources (highlighted where they were retrieved).
  - For test questions, also the reference answer and the judge's scores.
  - **Live demo (user requirement, 2026-10-29):** before a demo the user picks the best-performing configuration; the Ask page opens with it loaded, so guests can type their own questions and see the answer and its chunks. A free question has no reference answer or gold sources, so it shows no scores. Each question costs about $0.0002-$0.0003 at S0 (gpt-4.1-nano) and counts against `BUDGET_USD`.
- **Evaluate page:**
  - The settings panel plus the split (dev, held-out, or the 20-question smoke test). Estimate, then **Evaluate**. Held-out runs use the default prompt or a version with a finished dev run (T36 revision 2026-10-29).
  - The 4 headline KPI tiles with a "show all" toggle, trust metrics, scores by category, and a per-question table that links to Ask.
  - Export to CSV.
- **Compare page:**
  - Metric bars, the paired-bootstrap result, the per-question diff (fixed / broken), and cost against accuracy.
- **Build page:**
  - Chunking method, size (64-2,048) and overlap (0-50%) and stacks, then **Embed**, with a green or red status message.
- **Sweep page:**
  - Base configuration, the variable to sweep (including hybrid search and prompt version) and its values, then estimate, then **Confirm**.
- **Ops page:**
  - Spend against budget, error rate, p95 latency and the app version.
- Every chart can be exported as PNG.
- **Check:**
  - A smoke-test click-through, then one full dev run.
  - The Ask page reproduces the evaluation's chunks for the same question and config.

### Step 10 - Packaging, environments and edge
- One Dockerfile with multiple stages: the `node` stage builds the frontend, which is copied into `python:3.12-slim`. Uses `uv sync --frozen --no-dev`, a non-root user, and downloads nomic at build time. The git SHA is passed as a build argument.
- Copy `backend/data/synthetic/` into the image (D20; not done yet, found by Antigravity) and mount `var/` (chunk sets, T39) as a volume.
- `deploy/docker-compose.yml` runs as `rag-playground-staging` and `rag-playground-prod`, each with its own `.env`, volume and Qdrant.
- `deploy/edge`: Caddy with TLS for `staging.<domain>` and `<domain>`, basic auth, and a reverse proxy to each environment.
- **Check:**
  - Both environments are up with HTTPS and login.
  - Data survives a restart.
  - The two environments do not share data.

### Step 11 - CI/CD with an evaluation gate
- GitHub Actions on every push to `main`:
  1. Lint and unit tests.
  2. Build the image and push it to GHCR as `:<git-sha>`.
  3. Deploy to staging over SSH (`deploy.sh <sha>`), then health check.
  4. Run `scripts/eval_gate.py`: a fixed set of 20 dev questions, stratified, on the production configuration. The job fails if any gate fails.
  5. Manual approval (GitHub environment `production`).
  6. Deploy the same `:<git-sha>` to prod, then health check.
- Rollback: `deploy.sh <previous-sha>`.
- Secrets: the SSH key and API keys are stored as GitHub Actions secrets.
- **Check:**
  - A normal change goes through to prod.
  - A deliberately broken prompt fails the gate and never reaches prod.
  - A rollback restores the previous version within 2 minutes.

### Step 12 - Observability, hardening and cost guardrails
- JSON logs with request id, route, latency, tokens and cost. Ops page.
- Allow only ports 22, 80 and 443, SSH keys only.
- Spending caps on OpenRouter and on the OpenAI project.
- Nightly backup of each `rag_playground.db`.
- **Check:** port 6333 is not reachable from outside, and a forced error shows up in the logs and on the Ops page.

### Step 13 - Experiments
- Run the ladder and sweeps on both stacks (dev), then the held-out confirmation.
- **Check:** all runs pass smoke tests, and spend stays within budget.

### Step 14 - Report
- **Report outline:**
  1. **Problem:** RAG that looks fine but answers badly. How do you know, and how do you fix it safely?
  2. **Method:** controlled variables, gold labels, dev and held-out split, paired bootstrap, a calibrated judge.
  3. **Baseline:** S0 numbers on both stacks.
  4. **What worked:** the ladder chart, with each significant step explained.
  5. **What did not work:** steps whose interval crosses 0, and techniques that cost more than they gained.
  6. **Stack A vs Stack B:** head-to-head, with the ranking caveat (T12) and the build-versus-buy trade-off.
  7. **Trust:** refusal rates and faithfulness.
  8. **Cost:** cost per question against accuracy, and the S7 trade-off.
  9. **Deployment:** architecture, CI/CD gate, staging to prod, rollback, observability.
  - **Embedding map (T38), placed in the method part:** the t-SNE images of both stacks (`scripts/embedding_map.py`, 200-token chunk set), with one question, its gold chunks and its retrieved chunks marked. The report states that t-SNE distances between clusters are not meaningful.
  - **Beyond the ladder:** hybrid search and prompt-version results from sweeps, marked as exploratory (dev only).
  10. **Limitations:**
      - T05 (keyword proxy kept as secondary).
      - T12 (OpenAI ranker).
      - T14 (temperature on reasoning models).
      - T15 (one variable at a time).
      - Synthetic data bias (T11).
      - Wider intervals on the 48 held-out questions.
- The **README "Findings"** section uses the same numbers.
- **Backup:**
  - A recorded 3-minute screen video of the live demo.
  - PNG exports of all key charts.
  - CSV exports of the runs.
- **Check:**
  - `scripts/embedding_map.py` writes one PNG per stack with seed 42, and a second run gives the same images.
  - A dry run of the live demo.
  - The backup video plays offline.

---

## 7. Done criteria
- One chunk set can be indexed on both stacks from the UI, with clear success and error messages.
- Any configuration within the T35 ranges (chunk size, overlap, method, K, hybrid search, reranking, model, system prompt version) can be evaluated: 192 dev questions answered, judged and charted automatically.
- The system prompt can be edited and saved as a new version from the dashboard.
- The t-SNE images of both stacks are generated for the report.
- Any question can be asked manually, and test questions show their reference answer, gold sources and scores.
- Story mode shows the climb on **each** stack, the head-to-head comparison, and the held-out confirmation.
- The judge is calibrated, and its agreement is reported.
- CI blocks a quality regression, staging-to-prod promotion works, and rollback works.
- Both environments run behind HTTPS and basic auth, and data survives restarts.
- The report, the README findings and the backup video are ready.
