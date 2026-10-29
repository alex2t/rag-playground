# Decision Log

Every architecture and test decision goes here: what was chosen, why, what else was considered, and the known trade-offs. Entries marked **Not best practice** are deliberate shortcuts for a single-user demo. Each one says what a production system would use instead.

Status: `accepted` | `proposed` (default, needs review) | `open` | `superseded`.

---

## Architecture

### D01 - Two stacks: hosted OpenAI and self-hosted open source - `accepted`
- **Decision:** Stack A is the OpenAI Vector Store. Stack B is Qdrant with an open-source embedding model.
- **Why:** this compares a managed service (no operations, pay per use, vendor lock-in) with a self-hosted one (we run it, no per-call cost, data stays on the VPS). That build-versus-buy trade-off is central to deployment strategy.
- **Trade-off:** we cannot choose or see the embedding model behind Stack A.

### D02 - Stack B: Qdrant + fastembed `nomic-embed-text-v1.5` - `accepted` (supersedes all-MiniLM-L6-v2)
- **Decision:** nomic-embed-text-v1.5: 768 dimensions, 8192-token context, ONNX runtime with no torch.
- **Why:** MiniLM reads only 256 word-pieces and silently ignores the rest, which would have penalised Stack B unfairly. nomic covers every chunk size we test.
- **Why Qdrant:** production-grade, one container, hybrid search available later.
- **Why fastembed:** a small runtime with no torch, so the image stays small.
- **Trade-off:** nomic needs the `search_document:` and `search_query:` prefixes. Forgetting them silently lowers quality.
- **Batch size 4 (2026-10-27, after the dev PC froze twice):** chunks are embedded 4 at a time (`BATCH_SIZE` in `stacks/nomic.py`). fastembed's default batch of 256 put a whole chunk set in one batch and needed about 15 GB of RAM for 51 chunks of about 1,000 tokens; the dev PC has 8 GB. With 4: about 2 GB peak, 77 s for 51 chunks, and identical vectors (batching does not change results). The 8 GB VPS benefits too. Details: `fix.md`.

### D03 - LLM calls through OpenRouter - `accepted`
- **Why:** one key and one OpenAI-compatible API for every model; comparing models only means changing an ID.
- **Trade-off:** an extra provider in the path, with its own outages and mark-up. The OpenAI Vector Store still needs a direct OpenAI key.

### D04 - FastAPI backend + Vite/React/TypeScript frontend - `accepted`
- **Why:** a production-shaped split between API and UI, with a typed API that is easy to discuss.
- **Trade-off:** more code than Gradio or Streamlit. Mitigated by time-boxing the frontend (D16).

### D05 - Frontend served by FastAPI inside one release image - `accepted` 2026-10-26 (supersedes "Caddy serves the frontend")
- **Decision:** a multi-stage Dockerfile builds the React app in a `node` stage and copies `dist/` into the backend image. FastAPI serves the static files and the API. One shared edge Caddy handles TLS and auth for all environments (D09).
- **Why:**
  - Staging and prod (D13) need one shared edge server for ports 80/443. If Caddy also served the frontend, each environment would need its own static-file server behind the edge: two web servers in a row, which we rejected for Nginx.
  - One image per release, tagged with the git SHA, contains both UI and API. UI and API are deployed and rolled back together and cannot drift apart.
- **Trade-off:** Python serves the static files, which is slower than a dedicated web server. That does not matter for one user.
- **Alternative rejected:** a per-environment Caddy behind the edge Caddy (double hop).

### D06 - SQLite for runs and results - `accepted`
- **Why:** a single file in a volume, one per environment, with nothing extra to run.
- **Not best practice for multi-user use:** a single writer and tied to one host. Production would use PostgreSQL.

### D07 - Background jobs in the API process, UI polling - `accepted`
- **Decision:** long jobs run in a thread inside the FastAPI process, and React polls `GET /api/jobs/{id}` every 1-2 s.
- **Why:** the simplest thing that works, with no broker.
- **Not best practice:**
  - Polling wastes requests and adds lag. SSE or WebSockets push progress instead.
  - In-process jobs are lost on restart and force a single API worker.
  - Production would use a job queue (Celery, RQ or arq with Redis) plus SSE.

### D08 - Caddy basic auth - `accepted`
- **Why:** stops strangers from spending the API credits, with no application code.
- **Not best practice:** one shared password and no user identity. Production would use SSO/OIDC (Salesforce Identity, Auth0, Keycloak).

### D09 - One shared edge Caddy for TLS and routing - `accepted`
- **Decision:** a separate compose project (`deploy/edge`) runs Caddy on ports 80/443. It handles TLS for `staging.<domain>` and `<domain>`, basic auth, and reverse proxying to each environment's app.
- **Why:** certificates are issued and renewed automatically, and one entry point serves every environment.

### D10 - Secrets in `.env` files on the VPS, CI secrets in GitHub - `accepted`
- **Not best practice:** plain text on disk. Production would use a secrets manager (Vault, Doppler, cloud provider).
- **Mitigation:**
  - One `.env` per environment, readable only by its owner, never committed and never baked into images.
  - Spending caps on both API keys.
  - CI credentials (the SSH deploy key, and the API keys for the gate) are kept in GitHub Actions secrets.

### D11 - Temperature support read from OpenRouter - `accepted`
- **Decision:** read each model's `supported_parameters` from OpenRouter. Temperature 0 is sent only if supported; otherwise the run is flagged `temperature_controlled = false`.
- **Why:** reasoning models (on 2026-10-26: `openai/gpt-6.1-sol`) reject or ignore temperature.

### D12 - CI/CD with GitHub Actions, GHCR and an evaluation gate - `accepted`
- **Decision:** on every push to `main`, the pipeline runs these steps, and the job stops at the first one that fails:
  1. Unit tests.
  2. Build the image and push it to GHCR as `:<git-sha>`.
  3. Deploy to staging over SSH.
  4. Health check.
  5. A 20-question evaluation gate on staging.
  6. Manual approval.
  7. Deploy the same image to prod.
- **Rollback:** redeploy the previous SHA tag.
- **Why (best practice):**
  - Immutable, versioned artifacts.
  - The same image is promoted from staging to prod, never rebuilt.
  - Automated quality gates, with a human approval before production.
  - The evaluation gate turns RAG quality into a release criterion: a change that lowers quality cannot reach production.
- **Trade-off:** each deploy costs about $0.05 in API calls, and the gate set is small (20 questions), so it catches large regressions, not small ones.
- **Not best practice:** deploying over SSH with compose. Production would use an orchestrator (Kubernetes, ECS) or a GitOps tool. It is acceptable for one VPS.

### D13 - Staging and prod environments on the same VPS - `accepted`
- **Decision:** two compose projects, `rag-playground-staging` and `rag-playground-prod`, each with its own `.env`, data volume and Qdrant.
- **Why:** it mirrors the Salesforce sandbox → production flow. CI tests in staging before prod is touched.
- **Not best practice:** both environments share one host, so a host failure takes down both. Production would put them on separate infrastructure.
- **Cost:** about double the RAM (two apps with nomic loaded, two Qdrant instances). Fits a VPS with 8 GB.

### D14 - Observability: JSON logs and an Ops page - `accepted`
- **Decision:** structured JSON logs (request id, route, latency, tokens, cost, error). The Ops page shows spend against budget, error rate, p95 latency and the app version.
- **Why:** "how do you monitor it?" is a standard deployment question, and this answers it in the app itself.
- **Not best practice:** no central log store, alerting or tracing. Production would use an observability stack (OpenTelemetry with Grafana/Loki, Datadog, or an LLM-tracing tool).

### D15 - Global evaluation budget per environment - `accepted` 2026-10-28
- **Decision:** `BUDGET_USD` caps all evaluation spend recorded in SQLite: $60 for prod and $5 for staging (CI gates). It replaces `SWEEP_BUDGET_USD`, because spend from the ladder, sweeps and held-out runs all counts against the $60.
- **Why:** one cap covers every way of spending money, not only sweeps.
- **Funding status (2026-10-27):** the user's OpenRouter key has a $30 limit and the account a $3.12 balance (about $26.90 was spent on the Step 2 dataset). That covers the Step 5 live judge tests (about $0.01) and the first runs in Step 6 (about $0.50 each). The Step 13 experiments need about $60 more credit: raise it with the user before Step 13. Claude never uses the OpenRouter key; the user runs anything that calls it.

### D16 - Frontend built in priority order - `accepted`
- **Decision:** Story → Ask → Evaluate → Compare first, then Build, Sweep, Ops. One shared layout; make it work before polishing.
- **Why:** React is the largest time cost. The pages that carry the presentation come first.

### D17 - `/api/health` reports version and Qdrant reachability - `accepted` 2026-10-26
- **Decision:** `GET /api/health` returns `{status, version, qdrant}`. `version` is the git SHA baked into the image (`APP_VERSION` build arg, `dev` locally). It returns 200 when Qdrant answers and 503 when it does not.
- **Why:** one endpoint proves the app is up, which release is running, and that its dependency is reachable. CI and `deploy.sh` can use it directly.
- **Alternative rejected:** a version-only health check plus a manual curl to Qdrant, which nothing would re-check after deploys.
- **Trade-off:** if Qdrant is down, the app reports unhealthy even for pages that do not need Qdrant. Production often splits this into liveness (process up) and readiness (dependencies up) probes.

### D18 - Step 0 validated locally, VPS check deferred - `accepted` 2026-10-26
- **Decision:** Step 0 is validated with `docker compose` on the dev machine. The same compose file is run on the VPS by hand before the deploy step.
- **Why:** the deploy path (edge Caddy, `deploy.sh`, CI) is built later. The image and compose file are the same either way.

### D19 - Official `openai` SDK for OpenRouter and the OpenAI Vector Store - `accepted` 2026-10-26
- **Decision:** one `openai` SDK client points at OpenRouter (`base_url=https://openrouter.ai/api/v1`) for chat and structured output. A second client uses the OpenAI API directly for the vector store. Model metadata (`supported_parameters`, `canonical_slug`, pricing) is read from OpenRouter's `/api/v1/models` with `httpx`.
- **Why:** OpenRouter is OpenAI-compatible, so one typed, maintained SDK covers both providers. Cost comes from OpenRouter's `usage.cost`, which is returned by default (checked on 2026-10-26).
- **Alternative rejected:** raw `httpx` calls for every endpoint: more code to write and test.
- **Trade-off:** OpenRouter-specific response fields (`usage.cost`) are not in the SDK's types and are read as extra fields.

---

## Test design

### T01 - One chunk set feeds both stacks - `accepted`
- **Decision:** each chunk set is made once (by LlamaIndex's `SentenceSplitter`, T39). Stack A gets one file per chunk, with `max_chunk_size_tokens=4096` and overlap 0, so OpenAI does not split it again. Each file carries the chunk's id, source document and folder as attributes, so Stack A's results map back to the same chunks as Stack B's.
- **Neutral file names (2026-10-27, Step 4 review):** Stack A's files are named `chunk_<hash of the chunk id>.md`, not after the document. Stack B indexes the chunk text only; a file name such as `clients__acme.md__1.md` could give OpenAI's keyword search an extra match that Stack B does not have.
- **Why:** with identical chunks, the only difference left is the embedding model and the vector DB.
- **Trade-off:** this is not OpenAI's default chunking, so absolute Stack A scores may differ from a default setup.

### T02 - Change one variable per ladder step - `accepted`
- **Why:** if two things change at once, we cannot tell which one caused the improvement.

### T03 - Same ladder on both stacks, plus head-to-head - `accepted`
- **Why:** shows improvement within each stack and compares the stacks fairly. No stack is set up to fail.

### T04 - Chunk sizes measured in tokens - `accepted`
- **Why:** OpenAI's limits and LLM context are both measured in tokens.

### T05 - Keyword match as relevance - `superseded` by T17
- Kept only as a secondary metric (keyword recall), to cross-check the gold-document metrics.

### T06 - Retrieval metrics: MRR, Recall@K, nDCG@K, Hit@K - `accepted`
- **Why:** standard IR metrics. MRR: TREC-8 QA track (Voorhees, 1999). nDCG: Järvelin & Kekäläinen (2002). They are computed on gold source documents (T17).
- **Revision 2026-10-27 (user decision):** MRR is the standard definition: 1 / rank of the first retrieved chunk from any gold document, 0 if none is in the top K. The earlier plan averaged 1 / rank over every gold document while citing TREC, which presented a custom variant as the standard. Coverage of two-document questions is measured by Recall@K, so nothing is lost.
- **nDCG@K as implemented (2026-10-27, Step 5):** binary relevance per chunk (relevant if its source is gold); the ideal ranking holds min(K, relevant chunks in the chunk set) relevant chunks, with K the run setting, not the number of chunks returned (Stack A can return fewer with a score threshold, T40). So nDCG measures how concentrated the top K is on gold-document chunks: at small chunk sizes a one-document question reaches 1.0 only if every slot holds a chunk of that document, and a two-document question reaches 1.0 with every slot from one gold document while Recall@K is 0.5. First-relevant rank and coverage are measured by MRR and Recall@K, which are the retrieval gates (T08); nDCG is not a gate.

### T07 - LLM-as-judge: different family, pinned, calibrated - `accepted` (judge model confirmed by the user 2026-10-27)
- **Decision:** the judge is `google/gemini-3.5-flash-lite`, at temperature 0, with a structured output schema, pinned to its OpenRouter `canonical_slug`.
- **Why a different family:** all three answer models are OpenAI models. A judge from another family reduces self-preference bias.
- **Why this model:** cheap enough (about $0.37 per 200-question run) to stay within budget. Stronger judges, such as `gemini-3.5-flash` at about $1.70 per run, would use most of the $60.
- **Two requests per answer (2026-10-27):** one for accuracy, completeness and relevance, one for faithfulness without the reference answer. Why and how: T41.
- **Validation:** calibrated against human grades (T20). If agreement is below target, change the judge.
- **Known risks:** bias towards longer answers, and variance between runs. Calibration measures both.

### T08 - Best RAG = highest accuracy after passing gates - `accepted` (gate values confirmed by the user 2026-10-27, to be reviewed after the first real runs)
- **Decision:**
  - Gates: MRR ≥ 0.75, Recall@K ≥ 0.80, faithfulness ≥ 4.0, correct refusal rate ≥ 0.80.
  - A gate passes when the score is equal to or above its value (`GATES` in `settings.py`, checked by `scoring/selection.failed_gates`).
  - The highest mean accuracy among eligible runs wins. Ties go to the cheaper run: "tie" means the paired bootstrap (T09) does not find the accuracy difference real.
  - Picking the best run is built in Step 6, when runs are stored; Step 5 built the gates only.
- **Why:** an earlier weighted composite had invented weights. One primary metric plus explicit gates is transparent.
- **Gate values:** these match the amber band of the UI colours. They are a custom choice, not a standard. Review them after the first real runs (Step 6), using scores from runs done anyway (no extra cost).

### T09 - Paired bootstrap to call an improvement real - `accepted`
- **Decision:** 1,000 resamples of per-question differences, seed 42, 95% confidence interval. The change counts only if the interval is above 0.
- **Interval method (user decision 2026-10-27):** percentile bootstrap (Efron & Tibshirani, 1993): the 2.5th and 97.5th percentiles of the 1,000 resampled mean differences. Alternative not chosen: BCa (bias-corrected and accelerated), slightly more accurate for skewed data but harder to explain. Best practice: yes, a standard method.
- **Why:** a paired test on the same questions separates real effects from noise.
- **In plain words:** to decide whether a change (for example, bigger chunks) really improved a score or was luck, we re-draw the questions at random 1,000 times and check whether the gain holds in nearly all draws.
- **Implementation (2026-10-27):** `scoring/selection.py`, Python standard library only (`random`, `statistics.quantiles`); numpy is not a declared dependency and adding one needs the user's OK. Cross-checked against `numpy.percentile`: identical to 6 decimals. It refuses two runs over different question sets, because the pairing would be meaningless.

### T10 - Fixed test split, seed 42 - `accepted`
- **Why:** every run must answer the same questions, or the comparisons are meaningless.

### T11 - Synthetic dataset generated by an LLM - `accepted`
- **Why:** no data was available. A fictional Salesforce consulting firm fits the presentation topic and has no licensing issue.
- **Risk:** a model from the same family as the generator may find the data easier, which inflates scores. With Wikipedia moved to phase 2 (T25), this risk is partly reduced by the judge from another family (T07) and its calibration (T20). It must be listed as a limitation.

### T12 - OpenAI vector store ranking vs plain Qdrant similarity - `accepted` 2026-10-27 (settings are user choices, T40; the "semantic only" anomaly is explained) (MUST appear in the report)
- **In plain words:** by default, OpenAI's search is not plain vector search: it mixes vector and keyword search, then re-orders results with its own undocumented model (the "ranker"). Qdrant does none of that. To compare the stacks fairly, the user chooses OpenAI's ranking settings explicitly for every run, and results with OpenAI's ranker on are labelled.
- **Issue:** OpenAI vector store search may apply its own ranker (`ranking_options`). Qdrant returns plain similarity. If OpenAI re-ranks, Stack A could win partly because of the ranker.
- **Findings (live, 2026-10-27, `vector_stores.search`, `rewrite_query=False`):**
  - The API accepts `ranker: "none"`, `"auto"`, `score_threshold` and `hybrid_search: {embedding_weight, text_weight}`. The SDK types omit `"none"` and `hybrid_search`, so they are sent through `extra_body`.
  - OpenAI's default is hybrid search plus a built-in ranker. With `ranker: "none"`, the scores are exactly RRF scores with k=60 (2/61 = 0.0328 when a chunk is first in both lists; 1/61 with one list), so the default fuses a semantic list and a keyword list with equal weights. With `auto`, scores change to values like 0.79-0.99: an undocumented re-ranking step on top.
  - With `auto`, the hybrid weights have no measurable effect (same ranks and scores for semantic-only and default).
  - `score_threshold: 0` returned exactly K results in every setting.
  - Probe on S0 (51 chunks), 12 dev questions (2 per answerable category), top 5, neutral file names. Hit@5 / MRR: `auto` 12/12, 1.00; `none` hybrid 1:1 12/12, 0.70; `none` semantic only (1:0) 7/12, 0.42; `none` keyword only (0:1) 12/12, 0.90; `auto` + semantic only 12/12, 1.00. Stack B on the same questions (offline): nomic dense 12/12, 0.96; hybrid 12/12, 0.96.
  - An earlier probe with file names derived from the document path gave `none` semantic only 6/12, 0.29 and `none` hybrid 11/12, 0.65. With 12 questions this cannot be told apart from noise; files are now named neutrally anyway (finding 8 of the Step 4 review).
- **Anomaly checked (2026-10-27, user-approved, about $0.005):** OpenAI "semantic only" (`ranker: none`, weights 1:0) scored far below nomic dense search (7/12 vs 12/12). The same 51 chunks and 12 questions embedded directly with `text-embedding-3-small` (1,536 dims) and `text-embedding-3-large` (3,072 dims) and ranked by plain cosine: both 12/12, MRR 1.00. So the vector store's "semantic only" mode is not plain cosine similarity over these models; what it computes is undocumented. Consequence: that mode is not presented as "OpenAI's embedding quality". A like-for-like dense comparison needs plain cosine over OpenAI embeddings outside the vector store; whether to add that is a scope question for the user.
- **Decision (user, T40):** the ranker, the two hybrid weights and the score threshold are Stack A settings chosen by the user on the dashboard; the code has no defaults and every run stores them.
- **Reporting rule:** every head-to-head result must state the ranking settings. Results with `ranker: auto` are labelled: Stack B has no equivalent, so Stack A's advantage may come from the ranker.
- **Still to decide before the ladder runs (Step 13):** the Stack A ranking values used in the ladder.

### T13 - Automated evaluation on the dev split - `accepted`
- **Decision:** the user picks index, K, reranking and model. One click answers and judges the 192 dev questions.

### T14 - Temperature fixed at 0, not a variable - `accepted` (supersedes the temperature sweep)
- **Decision:** temperature 0 for answer, judge and reranker. There is no temperature control.
- **Why (best practice):**
  - It is not a RAG technique.
  - Its effect is predictable.
  - Controlled evaluation keeps everything fixed except the variable under test.
- **Limitation:** `openai/gpt-6.1-sol` runs at its provider default. Its results are labelled "temperature not controlled".

### T15 - Sweep guardrails - `accepted`
- **Decision:**
  - One variable at a time only. The full-grid mode is removed, because it would exceed the budget.
  - Estimate and confirmation before starting.
  - Combinations already run are skipped.
  - Hard stop at `BUDGET_USD`.
- **Trade-off:** misses interactions between variables (for example, the best K may depend on chunk size). This must be stated as a limitation.

### T16 - All reported results use the same fixed splits - `accepted`
- **Decision:**
  - The ladder, sweeps and head-to-head all use the 192 dev questions.
  - The final result is confirmed on the 48 held-out questions (T18).
  - The 20-question smoke test is for checks only and never appears in results.
- **Why:** comparable, paired, statistically meaningful results.

### T17 - Gold source documents as the relevance signal - `accepted` (supersedes T05)
- **Decision:** the generator records which document(s) each answer comes from (`source_docs`). A retrieved chunk is relevant if its source is a gold document.
- **Why (best practice):** gold relevance labels are the standard for retrieval evaluation. Keywords are a weak proxy: a chunk can contain "2015" without answering the question. Here the labels are free, because we generate the data.
- **Limitation:** relevance is per document, not per passage. A chunk from the right document might still be the wrong part of it. Faithfulness and accuracy catch that downstream.

### T18 - Dev / held-out split (200 / 50) - `accepted`
- **Decision:** 250 tests, stratified by category with seed 42. 200 dev questions are used for every tuning decision. The 50 held-out questions are run only on S0 and on the final best configuration, per stack.
- **Why (best practice):** picking the best configuration on the same questions you report on overfits to those questions and inflates the result. A held-out set gives an honest final number.
- **Trade-off:** 50 questions give wider confidence intervals, and the report says so. Cost: about $2.
- **Revision 2026-10-27 (T34):** the held-out set is a fifth of the tests, rounded: 48 of 240 (192 dev).

### T19 - Unanswerable questions and refusal metrics - `accepted`
- **Decision:** about 10% of each split asks for information that is not in the KB. The judge flags `refused`. Two metrics:
  - **Correct refusal rate** (higher is better), which is also a gate.
  - **False refusal rate** (lower is better).
- **Why:** hallucination is the main enterprise risk with RAG. A RAG that refuses safely is as important as one that answers well. This matches Salesforce's trust message.
- **Trade-off:** prompts that make the model refuse more often can hurt the false refusal rate. Both metrics are reported, so the trade-off is visible.

### T20 - Judge calibration against human grades - `accepted`
- **Decision:** after the first real run, 30 answers are sampled, stratified by score, and graded blind by a human. Agreement is reported as: within ±1 on accuracy, and % agreement on pass/fail (accuracy ≥ 4). Target: ≥ 80% pass/fail agreement before the ladder runs.
- **Why (best practice):** an LLM judge is a measuring instrument and must be validated. "Who checks the judge?" is the first question an evaluation expert asks.
- **Limitation:** one human grader and 30 items is a light check, not a full inter-annotator study.

### T21 - Reranking as a ladder step - `accepted` (reranker model `gpt-4.1-nano` accepted 2026-10-28)
- **Decision:** S5 retrieves 20 candidates, an LLM reranker (`gpt-4.1-nano`, temperature 0, structured output) reorders them, and the top K are kept. The reranker is applied the same way to both stacks.
- **Why:** reranking is one of the most widely recommended RAG improvements.
- **Why an LLM rather than a cross-encoder:** the common open-source cross-encoders read at most 512 tokens, so they would truncate our larger chunks. This is the same unfairness that removed MiniLM. An LLM reranker reads whole chunks.
- **Trade-off:** extra cost (about $0.10 per run) and latency. Both are reported.
- **Implementation (2026-10-28, `rag/rerank.py`):** listwise ranking as in RankGPT (Sun et al., 2023): the model returns every passage number, most useful first, as structured output; it sees chunk texts only, no source paths. `RERANK_CANDIDATES = 20` in `settings.py`. An invalid ranking (duplicates, unknown numbers, missing passages) is completed as RankGPT's `receive_permutation` does: valid first mentions kept, missing passages appended in retrieved order. Each completed ranking is flagged `repaired`, so the repair rate can be reported and a model that often fails is visible.

### T22 - Answer models reduced to 3 - `accepted`
- **Decision:** `gpt-4.1-nano` (cheap), `gpt-4.1-mini` (mid), `gpt-6.1-sol` (latest).
- **Why:** comparing models is not a RAG technique (the same reasoning as T14). Three price points are enough to show the cost trade-off, and they save budget and time.

### T23 - Metrics display: 8 in the presentation, 4 headline metrics live - `accepted`
- **Decision:**
  - The presentation shows all 8 core metrics (MRR, Recall@K, nDCG@K, Hit@K, Accuracy, Completeness, Relevance, Faithfulness), plus trust and operational metrics.
  - The live dashboard defaults to 4 headline metrics (MRR, Recall@K, Accuracy, Faithfulness), with a "show all" toggle.
- **Why:**
  - The prepared presentation has time to explain every metric.
  - In a live session, 4 metrics map to two plain questions: did we find it, and did we say it correctly?
  - If the audience asks to see the app live, suggest the 4-metric view.

### T24 - Overlap values reduced to 0% and 25% - `accepted`
- **Why:** 10% and 50% rarely change the conclusion. Dropping them saves runs.
- **Revision 2026-10-27 (user decision, after T27's overlap became 200 tokens):** ladder step S2 picks the best overlap from {0%, about 20% (S0's 200/1024 share), 25%}, at S1's chunk size, the same way S1 picks the best chunk size. A fixed 25% would only be a small change from S0's 20%. Cost: about one extra run per stack, since the 20% run already exists from the size sweep. Any other overlap (0-50%) is available on the dashboard (T35).

### T25 - Wikipedia dataset moved to phase 2 - `accepted`
- **Why:** its keyword signal is weak (it has no gold passage labels in our schema), and it is unrelated to the Salesforce story. Removing it halves the runs.
- **Consequence:** synthetic-data bias (T11) has no external check in the presentation. Listed as a limitation.

### T26 - Report rules - `accepted`
- **Decision:** the README findings and the deck must include:
  - A "what did not work" section: steps whose interval crosses 0, and techniques whose cost exceeds their gain.
  - All limitations: T11, T12, T14, T15, T17, and the held-out interval width.
  - The OpenAI ranking settings next to every head-to-head result (T12).
  - Reproducibility metadata (git SHA, model slugs, dataset hash) for every quoted number.
- **Why:** reporting only the wins looks like cherry-picking. Honest null results and stated limits build credibility.

### T27 - Baseline S0 = LlamaIndex out-of-the-box defaults - `accepted` 2026-10-26 (supersedes the "bad" baseline of 100 tokens, 0 overlap, K=2)
- **Decision:** S0 uses fixed chunks of 1024 tokens, a 20-token overlap, top-K 2, no reranking and `gpt-4.1-nano`.
- **Source:** LlamaIndex documentation, checked on 2026-10-26: "The default chunk size is 1024, while the default chunk overlap is 20", and `similarity_top_k` defaults to 2 (https://developers.llamaindex.ai/python/framework/optimizing/basic_strategies/basic_strategies/). The answer model (`gpt-4.1-nano`, the cheapest in the catalogue) and "no reranking" are our own choices, not LlamaIndex defaults.
- **Why:** a baseline chosen to be weak inflates every gain and would not survive scrutiny. Documented framework defaults are a neutral, external reference that many teams actually ship, so the ladder measures what tuning adds over "out of the box".
- **Alternatives rejected:**
  - OpenAI vector store "auto" chunking (800 tokens, 400 overlap): its 50% overlap is off our grid, and its default result count could not be verified.
  - Custom mid-grid values (400 tokens, 0 overlap, K=5): no external source.
- **Trade-off (T27):** 1024 tokens and a 20-token overlap are not on the original grid, so 1024 is added to the size sweep (one extra run per stack) and the 20-token overlap is used by S0 only. Defaults can change between LlamaIndex versions; the report states the version and date checked.
- **Revision 2026-10-27 (user decision): S0 overlap is 200 tokens, not 20.** Checked in the code of `llama-index-core` 0.14.25: building an index without settings uses `Settings.node_parser`, which is `SentenceSplitter()` with `chunk_size=1024` and `chunk_overlap=200` (its own default, `SENTENCE_CHUNK_OVERLAP`). The constant `DEFAULT_CHUNK_OVERLAP = 20`, which the documentation quotes, is not used by that splitter. The docs-based value was wrong for "out of the box". **Chunk-size sweep (custom choice):** the overlap keeps S0's share of the chunk size, 200 / 1,024 (about 20%, rounded to whole tokens), because a fixed 200 tokens is impossible at 100 and 200 tokens. The ladder's S2 step (25%) is then a small change from S0's 20%; it is measured honestly and reported as is.

### T28 - Dataset generator: `anthropic/claude-sonnet-5.5` - `accepted` 2026-10-26
- **Decision:** the knowledge base and the 250 tests are generated once by `anthropic/claude-sonnet-5.5` through OpenRouter, reviewed by hand and committed.
- **Why:** a third model family, different from the answer models (OpenAI) and the judge (Google). This reduces the T11 risk that the answer models find text written by their own family easier, and that the judge favours its own family's style.
- **Cost:** about $3, one-off, above the plan's first estimate of "under $2". Taken from the spare budget.
- **Alternatives rejected:** `claude-haiku-5.5` (about $0.20, weaker at keeping many documents consistent), `deepseek-v4-pro` (about $0.80, untested here for long structured output).
- **Trade-off:** the model does not accept temperature, so generation is not repeatable. This does not matter, because the output is committed and hashed (D20).

### T29 - Dataset generated from a structured world model - `accepted` 2026-10-26
- **Decision:** three stages. (1) Generate `world.json`: the fictional firm, employees, services, clients, projects and runbooks, with dates and numbers. (2) Write each markdown document from the world model. (3) Generate questions from the documents; the generator records the gold `source_docs`.
- **Why:** documents written independently contradict each other, which corrupts gold answers for `multi_doc`, `comparative` and `temporal` questions. One source of truth keeps facts consistent. The world model also lets the checks prove that an unanswerable question's entity does not exist.
- **Alternative rejected:** generating each document from a short brief.
- **Trade-off:** more code than one prompt per document, and the world model has to fit in one context window.

### T30 - Even category distribution - `accepted` 2026-10-26 (custom choice)
- **Decision:** 25 `unanswerable` tests (10%, T19) and 225 tests split evenly across the other six categories (37 or 38 each). The split is stratified per category with seed 42; the held-out counts per category are allocated by largest remainder so that they sum to exactly 50.
- **Source:** custom choice, not a standard. It keeps every category large enough for per-category results.
- **Alternative rejected:** weighting towards `direct_fact` to resemble real traffic; small categories would give noisy numbers.
- **Revision 2026-10-27 (user decision, T34):** `temporal` 35 and `multi_doc` 30, others unchanged: 240 tests. These are the largest quotas the verified pool fills after the year/date check and the stricter same-fact rule, with the 40% cap kept. Keeping 36 `multi_doc` would have needed the cap computed from the old quota (15 of 36, 41.7%); rejected because it relaxes the rule. **Trade-off:** `multi_doc` confidence intervals are about 10% wider than at 36.

### D20 - Dataset committed under `backend/data/synthetic/` - `accepted` 2026-10-26
- **Decision:** `backend/data/synthetic/world.json`, `kb/<folder>/*.md` and `tests.jsonl` are committed after review and copied into the image.
- **Why:** every run's dataset hash points to a fixed file anyone can read. Regenerating would give different data each time.

### T31 - Automated consistency audit of the world model - `accepted` 2026-10-26
- **Decision:** after `world.json` is generated, `openai/gpt-6.1-sol` (a strong reasoning model from a family other than the generator) reads the whole world and returns a structured list of issues. An issue is either a **contradiction** (two statements that cannot both be true) or an **ambiguity** (a question about it would have two defensible answers). Documents are generated only when the list is empty. A human review follows.
- **Generator constraints (T29, tightened):** free-text facts describe only their own entity; no superlatives, ordinals ("first", "only", "most") or firm-wide totals in free text; metrics must respect the limits of the service used; projects are sorted by date in code; runbooks state hands-on time separately from monitoring windows.
- **Why (best practice):** synthetic evaluation data must be verified before use. A contradiction in the KB makes a gold answer wrong, and every score built on it. The first world passed the structural checks but had 6 confirmed cross-entity contradictions, found by an external review (`fix.md`).
- **Validation of the audit itself:** it is first run on that flawed world, and its findings are compared with the confirmed list, so its recall is measured, not assumed.
- **Trade-off:** an LLM audit is not exhaustive, so the human review stays. The auditor is from the answer models' family; it only flags issues and writes no data, so it does not shape the KB.


### T32 - Knowledge-base documents: facts only, one fact per document; checked for fidelity - `accepted` 2026-10-26
- **Decision:** 48 markdown documents are written by `claude-sonnet-5.5` from the world model: `company/` (overview, history, employee handbook with all policies), `employees/` (one staff directory per office), `services/` (10), `clients/` (18), `deployment-runbooks/` (14). File names are slugs; ids never appear in documents.
- **One fact, one document:** each fact is stated in exactly one document. Relations are stated on one side only (a service names its lead, a client names its account lead and project teams, a runbook names its owner, a profile names the manager); other documents mention an entity by name only. So a question's gold `source_docs` are exactly the documents that hold its answer.
- **Facts only:** every given fact must appear, and nothing else about the firm or its entities: no responsibilities, procedures, contacts, advice, rankings or invented relationships, no computed values. Dates in ISO format so they can be checked exactly. A short generic sentence about a Salesforce product in general is allowed. Document length comes from the facts; there are no length targets.
- **Why facts only:** a first sample with length targets and "generic prose" allowed produced 65 invented claims in 5 documents ("one of the longest-standing clients", "route client questions through..."). Invented claims make gold answers wrong and can silently answer questions meant to be unanswerable.
- **Why grouped staff directories:** individual employee profiles are about 150 words; real firms keep short profiles in a directory. Grouping keeps the facts unchanged and gives a more realistic spread of lengths.
- **Checks before use:**
  1. Code (deterministic): every number and date in a document exists in its facts, and every number and date in its facts appears in the document. The writer retries with the exact problems, up to 3 attempts.
  2. Fidelity audit by `openai/gpt-6.1-sol`, one call per document, given the document kind and title: lists any fact added, altered or omitted (about $0.004 per document).

### T33 - Enriched world model for realistic document lengths - `accepted` 2026-10-26
- **Decision:** the world model gains facts per entity: clients have 3-5 projects, each with a summary, objectives and several metrics, plus client-side stakeholders; runbooks have a purpose, an action and a verification check per step, and known issues with resolutions; services have scope included, scope excluded and client prerequisites; employees have a short bio; the company has 6 policies with 5-8 rules. Clients are generated in two calls of 9.
- **Why:** facts-only documents from the first world were about 150-900 tokens. At chunk sizes of 800 tokens and more (including the S0 baseline at 1,024), almost every document would be one chunk, so the chunk-size sweep would mostly compare whole-document retrieval with itself. More facts give realistic lengths without invented prose.
- **Trade-off:** a larger world costs more to generate and audit (about $1.50) and needs another review round. All T29 and T31 checks apply to the new free-text fields.

### T34 - Test generation and full-KB verification - `accepted` 2026-10-26
- **Generation (`claude-sonnet-5.5`):** single-document categories (`direct_fact`, `numerical`, `temporal`, `exact_term`) from each document's text; `multi_doc` and `comparative` from pairs of related documents built from world relations (client + account lead's directory, service + lead's directory, runbook + owner's directory, client + a project's service; two clients in the same industry, two services, two runbooks); `unanswerable` from the whole KB, of two kinds: entities that do not exist, and information about existing entities that the KB never states. Each candidate has a question, reference answer, gold `source_docs` and 2-4 keywords copied verbatim from the gold documents (for unanswerable: distinctive terms that must not appear in the KB). About 30% more candidates than needed.
- **Verification (`openai/gpt-6.1-sol`):** the whole KB plus 10 candidates per call. For each candidate: answerable, unambiguous, reference answer correct and complete, and which documents contain the answer. A candidate is kept only if all pass and the documents found equal its `source_docs`; an unanswerable candidate only if it is judged not answerable.
- **Code checks (unit tests on the committed data):** every `source_docs` path exists; answerable keywords appear in their gold documents; unanswerable keywords appear nowhere in the KB; counts per category match T30; ids and questions are unique; the split is identical on every load.
- **Selection:** verified candidates are shuffled with seed 42 and taken up to each category's quota; then the stratified split (T18, T30) is applied.
- **Why (best practice):** gold labels decide every score. Keyword checks cannot detect a wrong answer or an answer that also appears in another document; an independent model reading the whole KB can. Cost about $4-5.
- **Limitation:** the verifier is an LLM and the generator wrote the documents (T11); the human review of the tests and the judge calibration (T20) remain.
- **Revision 2026-10-26 (after the review in `fix.md`):**
  - **Questions:** questions name entities only and never state a fact. `multi_doc` answers compare or compute with one value that only the first document states and one that only the second states. Two questions per category per document (two per pair), each on a different fact. `temporal` prefers order and elapsed time.
  - **Pairs:** clients are paired same-industry first, then in a ring over shuffled clients (seed 42), so each client appears 2-4 times (5 at most) in 30 pairs. Each client is paired with the services of 2 random projects.
  - **Keywords:** 1-3 answer values, each also in the reference answer. Each document of a two-document test has a keyword the other lacks (code check).
  - **Verifier:** new `fewer_docs_suffice` check, which must be false.
  - **Selection (custom choices, not a standard):** no document kind (folder or folder pair) above 40% of a category, so one entity type cannot dominate. Two tests that share a source document count as the same fact when every answer value (keyword) of one is also an answer value of the other (one test is fully covered by the other); only the first picked (in category order) is kept, so dev and held-out do not test the same fact.
  - **Same-fact rule, first version rejected (user decision 2026-10-26):** the first version ("share a source document and any one answer keyword") allowed only 223 tests: `temporal` 28 and `comparative` 23, because the world's dates are shared by `multi_doc`, `temporal` and `comparative` tests. It also treated different questions as duplicates, for example the same employee's start date combined with two different projects. A 45% cap for `multi_doc` was approved, then withdrawn after the full selection showed it reached only 225. The whole-answer rule gives all 250 tests with the 40% cap everywhere, and still removes every duplicate listed in the review. **Trade-off:** one value (such as a start date) can appear in several tests, each time combined with a different fact.
  - **Why:** without these, a test could be answered from one document, test the same fact as another test, or be scored with keyword recall that does not reflect the answer. All are stricter checks; none was relaxed.
- **Revision 2026-10-27 (after Antigravity's re-review in `fix.md`, user chose option B):**
  - **Year/date check (code):** a "how many / how long" question whose keywords mix a bare year (`2015`) and a full date (`2014-10-13`) is rejected: "client since 2015" to "joined 2014-10-13" is 0 or 1 year depending on the counting convention. Ordering questions ("which came first") and questions that state the convention ("by calendar years") are unambiguous and kept. 13 verified candidates rejected. Assembly re-runs every code check on verified candidates.
  - **Same-fact rule, extended (custom rule):** two tests also test the same fact when every source document of one is a source document of the other and they share an answer value. This catches the same project duration or the same handbook rule reached from the same documents; tests that pair a shared value with a different document stay distinct.
  - **Category order:** categories pick scarcest first (verified pool size / quota), so a fact shared across categories goes to the category with the fewest spare candidates.
  - **Final-check fixes (Antigravity's notes, user decision 2026-10-27):** (1) a shared answer value is matched as a whole value even when one keyword adds words ("85.0%" in "85.0% pass rate", but not "5.0%" in "85.0%"); (2) a code check rejects an answer in months and days when the end's day of the month is before the start's (2020-01-13 to 2024-05-06 is 23 or 24 extra days depending on what is counted first); (3) the year/date check looks for "how many / how long" anywhere in the question and exempts questions that state "calendar years". 19 tests were replaced; all quotas still fill.
  - **Limitations:** 16 dev/held-out pairs share one of two values (for example, two duration comparisons that both include Service Cloud's 11 weeks); each asks a different question. 12 of 30 `multi_doc` questions follow the "how long had X been at the firm when..." template. 2 duration questions (`multi_doc-002`, `003`) list only one of the project's two dates in keywords, so their keyword recall is less complete. Keywords hold only values a document states, never computed answers, because they measure retrieval only. The verifier wrongly rejected 2 valid candidates.

### T35 - Dashboard settings: any value within a range - `accepted` 2026-10-27
- **Decision:** the dashboard sets chunk size (64-2,048 tokens), overlap (0-50% of the chunk size), top-K (1-20), chunking method, hybrid search on/off (T37), reranking on/off, answer model and system prompt version (T36). A chunk set that does not exist yet is built and indexed on both stacks on demand, after a cost and time estimate and a confirmation. Sweeps take any list of values for one variable.
- **Why:** lets the presenter and the audience try any configuration live, not only the precomputed grid.
- **Ranges (custom choice):** 2,048 tokens stays far below both embedding models' context (OpenAI's 4,096-token chunk limit for vector store files, nomic's 8,192). Below 64 tokens a chunk rarely holds a full fact. 50% overlap is OpenAI's own default (800/400), the upper end of common practice.
- **Revision 2026-10-29 (T45):** top-K is 1-8, not 1-20.
- **Trade-off:** more chunk sets to store and index (each a few cents of OpenAI embedding cost and about a minute). Results outside the ladder are exploratory: only dev questions, and the paired bootstrap still decides what is an improvement.

### T36 - System prompt editable as named versions - `accepted` 2026-10-27
- **Decision:** the answer model's system prompt is editable on the dashboard. Each saved edit is a named, immutable version; every run stores the version and its hash. The default version is used by S0, the ladder, the held-out confirmation and the CI gate.
- **Why:** the prompt strongly affects accuracy, faithfulness and refusals (T19), so it is a real RAG setting. Versioning keeps every result reproducible.
- **Rule:** a prompt change is one variable, compared on dev questions only with the paired bootstrap. Never tuned on held-out questions.
- **Trade-off:** prompt tuning can overfit the dev questions; the held-out confirmation is what guards against it.
- **Default text approved by the user 2026-10-28** (`DEFAULT_TEXT` in `rag/prompts.py`, custom wording, not a standard): role (internal assistant of the fictional firm), audience and topics, answer only from the retrieved context, say when the answer is not in the knowledge base, compute durations and totals from the context, answer concisely. A first draft without role and task was rejected by the user. The text gives the task type only, never an answer, and is identical for every run on both stacks.

### T37 - Hybrid search (keyword + vector) as a setting - `accepted` 2026-10-27
- **Decision:** a hybrid search on/off setting, available on the dashboard and in sweeps, not a ladder step. Stack B: Qdrant with a sparse BM25 model from fastembed (`Qdrant/bm25`, no torch) next to the nomic dense vectors, fused with reciprocal rank fusion (RRF) in Qdrant's query API. Stack A: OpenAI's own hybrid mode (`ranking_options.hybrid_search` weights, with `ranker: none`), found in Step 4 (see below).
- **Why:** keyword matching finds exact strings (commands, error messages, names) that dense vectors often rank low; about 15% of the tests (`exact_term`) ask for these. Widely used in production RAG, cheap (no LLM calls).
- **Alternatives rejected (user decision):** query rewriting (our questions are already precise; one more LLM call per question), score threshold (the two stacks' scores are on different scales), neighbour-chunk expansion.
- **Trade-off:** the two hybrid modes are similar, not identical: OpenAI's keyword scoring is undocumented, Stack B uses BM25.
- **Step 4 result (2026-10-27):** Stack A has an equivalent: `ranking_options.hybrid_search` with `embedding_weight` and `text_weight`, fused by RRF (k=60, see T12). It is only effective with `ranker: "none"`. So hybrid search can be part of the comparison.
- **Stack B detail (custom choice):** `HYBRID_PREFETCH = 50` candidates from each list (dense and BM25) before RRF, at least 2.5 times the maximum top-K of 20 (since T45 the maximum is 8, so the margin is larger). Qdrant's RRF uses its default constant.

### T38 - t-SNE embedding map for the presentation - `accepted` 2026-10-27
- **Decision:** a script draws a 2D t-SNE map (scikit-learn, seed 42) of one chunk set's embeddings for each stack: chunks coloured by KB folder, test questions overlaid, and optionally one question with its gold chunks and its retrieved chunks marked. Stack B uses nomic embeddings (local, free). Stack A's embeddings cannot be read back from the OpenAI vector store, so the chunks are embedded again with an OpenAI embedding model (about $0.01). Which one is still to decide when the map is built: OpenAI does not document the vector store's model (Step 4 result below). Default chunk set: 200 tokens, so the map has enough points to read.
- **Why:** shows the audience how the documents and questions sit in embedding space, and why a question can land near the wrong document.
- **Limitations (stated on the slide):** t-SNE keeps local neighbourhoods but not global distances, so the distances between clusters and the cluster sizes mean nothing; the two stacks' maps are separate fits, so only their structure can be compared, not their axes. It is an illustration, not evidence: results come from the metrics.
- **Step 4 result (2026-10-27):** OpenAI does not document which embedding model or dimensions the vector store uses (file search guide and retrieval guide checked). The direct-embedding check under T12 did not identify it: both `text-embedding-3-small` and `-large` rank far better than the vector store's semantic-only mode. The Stack A map is labelled with the model actually used and "vector store model not documented".

### T39 - Chunk sets made by LlamaIndex's SentenceSplitter - `accepted` 2026-10-27
- **Decision:** every chunk set is made by `llama_index.core.node_parser.SentenceSplitter` (`llama-index-core` 0.14.25), unmodified, on each KB document's text with no metadata. Tokens are counted with the same tokenizer (`cl100k_base`, bundled with LlamaIndex, so no download is needed). A set is identified as `fixed__c{size}__o{overlap tokens}`, saved once to `var/chunk_sets/<id>.jsonl` (gitignored; a Docker volume in deployment) and reused by both stacks. Each chunk stores its id (`<path>#<n>`), source, folder, position, text, token count and character span.
- **Why:** the S0 baseline claims "LlamaIndex out of the box"; using the library's own default splitter makes that claim exact and verifiable. It cuts at paragraph and sentence boundaries where it can.
- **Alternatives rejected (user decision):** our own sentence-aware splitter (S0 would only reuse LlamaIndex's numbers); plain token windows (cut mid-sentence and mid-row, not what LlamaIndex does).
- **Size and overlap tolerance: up to 2 tokens over (user decision 2026-10-27, revised from 1 token).**
  - **What happens:** `SentenceSplitter` first cuts the text into small pieces (paragraphs, then sentences, then words), counts the tokens of each piece separately, and fills a chunk until the *sum* of those counts would pass the limit (`cur_chunk_len + cur_split.token_size > chunk_size` in `_merge`). The same sum-based rule fills the overlap. When the pieces are joined back into one string, the tokenizer can count the joined text slightly differently, because a boundary such as `"word" + "\n" + "-"` tokenizes differently as a whole than piece by piece. The more pieces a chunk joins, the larger the possible gap, so it shows only at small sizes.
  - **How it was measured:** all 836 settings in the T35 range on our 48 documents (sizes 64-256 in steps of 2 and 256-2,048 in steps of 16, each with overlaps of 0, 10%, 20% and 50%). Chunk size: 754 settings never go over, 80 go 1 token over, 2 go 2 tokens over (size 64 / overlap 6, size 66 / overlap 33), none more. Overlap: 732 never, 92 by 1, 12 by 2 (all at size 134 or below, three of them found by Antigravity), none more.
  - **Decision:** the checks allow a chunk to be at most its size + 2 tokens, and two consecutive chunks to share at most the overlap + 2 tokens. The tests include the worst settings found. This is a measured bound on our KB, not a guarantee from LlamaIndex: a different corpus could in principle go further, so the sweep is re-run if the KB changes.
  - **Why accept it:** 2 tokens is less than one word, it occurs only at sizes of 134 tokens or less, and it is far below the embedding models' limits (4,096 and 8,192 tokens), so it cannot change retrieval or answer quality measurably. Keeping the chunks exactly as LlamaIndex produces them is what makes the S0 baseline a real "LlamaIndex out of the box".
  - **Alternative rejected:** re-cutting any chunk that goes over would make the limits exact, but the chunks would no longer be LlamaIndex's output, which weakens the S0 claim.
  - Overlap is made of whole pieces up to the overlap budget, so an actual overlap can also be smaller than the setting, or zero when the next piece does not fit.
- **Chunk positions (bug found by Antigravity, fixed):** the splitter returns text only, so each chunk's character span is found by searching the document. Two facts of the splitter's output make a naive search wrong: (1) a short chunk such as a lone `|` also occurs inside the previous chunk; (2) a whole short chunk can fit in the next chunk's overlap, so both start at the same place. The search therefore starts where the next chunk must lie: no earlier than the previous start, ending after the previous end, and at or after the previous end when overlap is 0. Checked over the same 836 settings: every chunk is an exact piece of its document, chunks are in order, and together they cover every document.
- **Consequence:** at 1,600 and 2,048 tokens every document is one chunk (the longest document is 1,550 tokens), so those sizes compare whole-document retrieval.
- **Trade-off:** a large dependency (`llama-index-core`, no torch) for one function. uv is set to copy files instead of hard-linking them (`[tool.uv] link-mode = "copy"`), because nltk, which the splitter uses, refuses to open multiply-linked data files.

### T40 - The user picks the stack(s) and every setting; no defaults - `accepted` 2026-10-27 (user decision)
- **In plain words:** on the dashboard the user chooses Stack A, Stack B or both, and sets every option. The code never fills in a value silently.
- **Decision:** a dashboard run uses Stack A, Stack B, or both. With both, the same settings run on each stack and the results are shown side by side. Every setting is chosen by the user, including Stack A's ranking options (ranker `none`/`auto`, hybrid weights, score threshold, T12); the code has no hidden defaults, and every run stores all settings.
- **Why:** flexibility for the user, and nothing is decided silently by a library or a vendor default (OpenAI's default turns on hybrid search and a built-in ranker, T12).
- **Consequences:** Stack A-only settings (the OpenAI ranker) are shown only when Stack A is selected; side-by-side results with `ranker: auto` are labelled, since Stack B has no equivalent. The ladder (S0-S6) is a fixed set of configurations, so it states its Stack A ranking values explicitly (still to decide, T12).
- **Best practice:** yes. Explicit configuration recorded per run is standard for reproducible evaluation.
- **Revision 2026-10-28 (user decision): one identical menu for both stacks.** Different menus would make a side-by-side comparison not like for like. The menu is the same for A and B: chunk size, overlap, top-K, hybrid on/off, reranking on/off, answer model, prompt version; the user still sets every one. Stack A's hybrid switch is translated into fixed OpenAI settings (custom choice, not a standard): off = ranker `none`, `embedding_weight` 1, `text_weight` 0, `score_threshold` 0 (meaning search only, like Stack B off); on = ranker `none`, both weights 1, `score_threshold` 0 (both lists fused equally by RRF, like Stack B on). The run's `hybrid` flag is what the user set on both stacks, and `openai_ranking` stores the translated values.
  - **Consequence:** this also fixes the Stack A ranking values used by the ladder (the open T12 item).
  - **Limitation (report it):** Stack A's meaning-only mode scored 7/12 vs 12/12 for Stack B in the Step 4 probe, and what OpenAI computes in that mode is undocumented (T12).
  - **Still open:** whether OpenAI's own extras (ranker `auto`, other weights, threshold) stay in a separate "Stack A only" section kept out of A-vs-B comparisons, or are removed. Claude's recommendation: keep them separate, as "OpenAI out of the box" is a result of its own.

### T41 - Judge rubric (what each score from 1 to 5 means) - `accepted` 2026-10-27 (user approved the recommended scale)
- **In plain words:** the judge model grades each answer from 1 to 5 on four questions: is it correct, complete, on topic, and backed by the retrieved documents. This entry fixes what each number means, and why faithfulness is graded in a separate request.
- **Decision:** the judge prompt in `scoring/judging.py` defines anchors for each criterion. Accuracy: 5 = every stated fact agrees with the reference, 3 = main fact right but a secondary detail wrong, 1 = main fact wrong or missing, or any contradiction. Completeness: every part of what the question asks for, as the reference gives it (5 = every part, 3 = about half, 1 = none); supporting details the question does not ask for (such as the dates behind a computed duration) are not required; an invented answer to an unanswerable question scores 1. Relevance: 5 = answers exactly the question, 3 = adds unrelated material, 1 = off topic. Faithfulness: 5 = every claim stated in or computed from the retrieved context, 3 = the main claim supported but some other claims not, 1 = the main claim unsupported; judged only against the context, so a claim that matches the reference but not the context is unsupported (Antigravity review, 2026-10-27).
- **Refusals:** on an unanswerable question a refusal scores 5 on all four; on an answerable question a refusal scores accuracy 1 (and is counted by the false refusal rate, T19). A refusal makes no claims, so it is faithful (5) and relevant (5).
- **Two calls (user decision 2026-10-27, after a live failure):** accuracy, completeness and relevance are graded in one call that sees the question, the reference answer and the answer (no context); faithfulness in a second call that sees the question, the retrieved context and the answer, never the reference answer. In one combined call `gemini-3.5-flash-lite` gave faithfulness 5 to a correct answer the context did not support, saying it matched the reference (fix.md). Separating faithfulness from the reference is how RAGAS computes it (answer and context only). Alternatives rejected: a stronger judge (about 4 times the cost, still sees the reference), stronger wording (already tried, failed). Cost: about the same as one combined call, since the context is now sent once, to the faithfulness call only.
- **Invented-fact test (user decision):** an answer with a supported main claim and one invented extra claim scores 3 by this rubric; the live test checks faithfulness below 4 (the T08 gate), not 2 or less as first written, which contradicted the rubric.
- **Order:** the judge writes its feedback before the scores, so the scores follow its reasoning (a common practice in LLM-as-judge prompts, for example G-Eval's reasoning-first steps; Liu et al., 2023).
- **Why:** the plan defines what each criterion compares but not what each number means; without anchors the judge's scale drifts between runs and models.
- **Best practice:** explicit anchors are standard for LLM judges; the anchor wording is our own. It is validated by the human calibration (T20) before any experiment.

### T42 - How the stacks and the judge are tested - `accepted` 2026-10-27 (user decisions)
- **In plain words:** tests that cost nothing run on every test run; tests that call a paid API are marked `live`, skipped by default, and run by the user.
- **Offline tests ($0):** our side of each external call is tested with a fake client: the request we send, how replies are read, and errors (`tests/test_openai_store.py`, `tests/test_scoring_judging.py`). They cannot prove the external service behaves as expected; the live tests do that.
- **Live tests (run by the user):** Stack A on the S0 chunk set (`tests/test_live_stack_a.py`, about $0.001, OpenAI key) and the judge (`tests/test_live_judge.py`, about $0.01, OpenRouter key). Claude may run an OpenAI check only after the user approves its cost; Claude never uses the OpenRouter key.
- **Stack A live checks use explicit ranking** `ranker: none`, hybrid 1:1, `score_threshold: 0`, so Stack A has no built-in ranker that Stack B lacks (T12).
- **Stack B is tested with Qdrant in memory** (no server, no Docker). The Qdrant server is first exercised in Step 10 (Docker Compose).
- **A test of "X helps" must first show that "without X" fails** (lesson from the hybrid test, `fix.md`): the hybrid test checks that dense search alone ranks the exact code last, then that hybrid ranks it higher.
- **Best practice:** yes. Separating free unit tests from paid integration tests is standard.

### T43 - Cost estimate before a run - `accepted` 2026-10-29 (user decision; custom formula)
- **Decision:** per question, input tokens are counted from the real inputs (system prompt + K chunks at the chunk set's average chunk length + the question, and the same for the judge and the reranker); output tokens are assumed from plan.md 1.3 (about 150 per answer, 200 per judgement); everything is priced with live OpenRouter prices.
- **Why:** it works before any run exists and follows the settings (K, chunk size, reranking, models).
- **Alternatives:** the average cost per question of earlier runs with the same models (more accurate later, more code, still needs a fallback).
- **Limits:** a custom formula, not a standard. `gpt-6.1-sol` writes hidden reasoning tokens that cannot be predicted, so its estimate is low. Checked against one real 10-question run (plan check: within 50%).
- **Details (2026-10-29, built in `rag/estimate.py`):** inputs are counted on the real messages (real templates, prompt version, question and reference answer) with each chunk replaced by a filler of the chunk set's mean length, plus 4 tokens per message (OpenAI cookbook, "How to count tokens with tiktoken"). Answer output 150 tokens, each of the judge's two calls 200 (plan.md 1.3). The reranker's output is counted exactly: its reply is always the list of every candidate number. Tokens are counted with cl100k (the chunk sets' tokenizer); other models' tokenizers differ somewhat.
- **Observed:** on S0 (51 chunks, mean 694 tokens, K=2) an answer request is about 1,600 input tokens, well below plan.md 1.3's earlier guess of 4,500.
- **Best practice:** a reasonable practice; production systems usually also calibrate the estimate from measured usage.

### T44 - Spend recorded per paid call - `accepted` 2026-10-29 (user decision)
- **Decision:** a `spend` table in SQLite holds one row per paid OpenRouter call, written as soon as the call returns. Budget used (D15) = the sum of that table. A running job checks the budget before every question and stops cleanly when the next question could exceed `BUDGET_USD`.
- **Why:** the cost saved with each result is only written after judging, so money spent on a question that fails halfway would never be counted.
- **Alternatives:** sum of `results.cost_usd` (simpler; undercounts failed questions).
- **Limits:** a call that is billed but fails before its reply is read (for example a structured reply cut off at its length limit) reports no cost and is not recorded. OpenAI embedding cost for Stack A builds (under $0.05 per build) is not on OpenRouter and is not counted.
- **Best practice:** yes; per-call usage records are the usual basis for cost tracking.
- **Budget guard (2026-10-29, user decisions; built in `rag/pipeline.py`):** a run whose T43 estimate is above what is left of `BUDGET_USD` (budget minus all recorded spend, every run and spend outside runs) is refused and nothing is stored; an estimate exactly equal is allowed. Before each question, the run stops if spend so far plus the next question's assumed cost would pass `BUDGET_USD`. The assumed cost is the larger of the question's T43 estimate and the run's most expensive question so far (custom rule, not a standard: the estimate is low for `gpt-6.1-sol`'s hidden reasoning tokens). A run stopped this way is marked `failed` with the message "BudgetExceeded: Budget reached: ..." and keeps its results (alternative not taken: a new `stopped` status, which would change the runs table and every reader of the status). `BUDGET_USD` unset means $0, so a machine without it cannot spend.
- **Limits of the guard:** the real cost is known only after a question's calls return, so total spend can pass the cap by at most the error of one question's guess (about $0.003-$0.05 per question at plan.md 1.3 prices). Questions run one at a time; running questions in parallel, or two runs at once in the same environment, would need the guard to count spend still in flight (to handle when parallel questions are built).

### T45 - Top-K at most 8; S3 = best K of {2, 4, 6, 8} - `accepted` 2026-10-29 (user decision; custom choice)
- **Decision:** top-K is 1-8 everywhere (dashboard, sweeps, ladder) and enforced in code (`MAX_TOP_K` in `settings.py`; runs with a larger K are refused). The top-K sweep uses K = 2, 4, 6, 8 (2 is the S0 baseline). Ladder step S3 picks the best K of {2, 4, 6, 8} at S2's chunk set, on dev questions only, the same way S1 and S2 pick their values (T24). S5 keeps S3's K after reranking.
- **Why:** the KB is small: 48 documents, mean 730 tokens (150-1,550). At S0's 1,024-token chunks most documents are one chunk, so K=20 would hand the model 20 of 51 chunks (about 40% of the KB), not a realistic retrieval. Supersedes the 1-20 range (T35), the sweep 2, 5, 10, 20 and the fixed S3 K=10.
- **Trade-off:** with small chunks the cap limits recall: at 100-token chunks one document is about 8 chunks, so K=8 covers about one document and `multi_doc` questions (two gold documents) may miss one. The report states this ("small chunks need a higher K"). S3 as a best-of costs about 3 extra runs per stack (K=2 at S2's set is the S2 run itself). The reranker still retrieves 20 candidates (T21).
- **Best practice:** choosing K by a sweep on dev data is standard; the cap of 8 is a custom choice for this KB size.

### D21 - Runs and results are permanent in the database - `accepted` 2026-10-29 (user decision)
- **Decision:** SQLite triggers in `store.py` keep every run and result exactly as written, on every connection, not only through our functions. A new run starts `running` with no error; every column but `status` and `error` is permanent; a run changes once, from `running` to `done` or `failed`; `done` needs a result for every declared question; runs and results are never updated, deleted or replaced (`INSERT OR REPLACE` and UPSERT included). The same approach as prompt versions (T36).
- **Why:** runs are the evidence behind every score in the report. Review item 7 showed that plain SQL could still edit a finished run's settings and its stored answers and scores, delete it, or create a run already `done` with no answers (`fix.md`, 2026-10-29).
- **Alternatives:** the reviewer's narrower fix (lock only finished runs; no update or delete of results), which leaves running runs, deletion, replacement and runs created finished open; or rely on our functions only (no protection against a database tool or a stray script).
- **Trade-off:** a run cannot be removed or corrected once stored, even a test run on staging; that needs a new database file, as for prompt versions. A wrong run is replaced by a new run, never edited.
- **Limits:** a connection can still drop the triggers or the tables (schema changes are not blocked). The `spend` table (T44) is not locked: it is a budget record, not evaluation evidence; open if the user wants it locked.
- **Best practice:** yes for the principle (append-only records of experiments); in production the same is usually done with database permissions (a role that can only insert) on PostgreSQL rather than triggers.

### D22 - Review branch while Antigravity was unavailable, merged into `main` - `accepted` 2026-10-29 (user decision)
- **Decision:** from 2026-10-28 (Option 1), while Antigravity was unavailable, Step 6 increments were committed on the branch `step6-pending-review` and their review prompts queued in `review-queue.md` (private), oldest first. All 9 items were reviewed by Gemini 3.8 (Gemini 4 had reviewed the work before the branch), every finding verified by Claude, and the branch was merged into `main` by fast-forward (`cc40fe6`) and pushed on 2026-10-29.
- **After the merge:** work continues on `main`, with each increment reviewed by Antigravity before it is committed, as before the branch (stated by Claude when merging; the user can change it).
- **Why:** building could continue without putting unreviewed code on the public `main`.
- **Trade-off:** reviews ran later than the code, so a finding could touch work already built on top (item 3's finding led to items 7 and 9).
- **Best practice:** yes; a feature branch merged only after review is the usual pull-request workflow.

### D23 - Qdrant on the dev PC runs in Docker, like prod - `accepted` 2026-10-29 (user decision)
- **Decision:** for real runs on the dev PC, Stack B uses the same Qdrant server image as staging and prod (`qdrant/qdrant:v1.20.0`, `deploy/docker-compose.yml`), started in Docker Desktop and bound to `127.0.0.1:6333` only. Offline tests keep using Qdrant's in-process mode (`QdrantClient(":memory:")`).
- **Why:** dev results then come from the exact server version prod uses.
- **Alternatives:** Qdrant's local mode in the Python client (a folder under `var/`, no server): lighter on RAM, but a separate implementation, so results could differ from prod.
- **Trade-off:** Docker Desktop uses about 1-2 GB of the PC's 8 GB RAM while running; close it after a run.
- **Best practice:** yes; dev/prod parity.

### D24 - One recorded index per stack and chunk set - `accepted` 2026-10-29 (implements the `indexes` table of plan.md section 5)
- **Decision:** an `indexes` table records, for each (stack, chunk set), the OpenAI vector store id (Stack A, store named `rag-playground-{APP_ENV}-{chunk set id}`) or the Qdrant collection name (Stack B, the chunk set id), with its chunk count. An index is built once from the saved chunk set; building it again is refused. A run searches the index recorded for its stack and chunk set, with its own stored settings (Stack A: its stored `openai_ranking`; Stack B: its `hybrid` flag). Stack A's hybrid switch maps to fixed OpenAI ranking values (T40 revision), in `openai_vector_store.hybrid_ranking`.
- **Why:** Stack A's store id is only known once OpenAI creates the store, so it must be stored to be found again; a failed Stack A upload deletes its store, so no half-filled paid store is left; a Qdrant collection missing chunks is refused.
- **Limits:** no rebuild or delete yet (a changed chunk set needs a new id or a manual clean-up); the run does not store the Stack A store id itself, only its chunk set id. If the clean-up delete itself fails, or the process is killed during an upload, an unrecorded OpenAI store is left (never searched, but billed for storage until deleted by hand).
- **Best practice:** yes; a registry of built indexes is the usual way to tie experiments to their index.

### T46 - Small runs take questions round-robin by category - `accepted` 2026-10-29 (user decision; custom choice)
- **Decision:** a run of fewer questions than the full dev set (such as the first real 10-question run) takes the first question of each category in turn, then the second of each, until it has enough (`datasets.splits.round_robin`), in the file's category order. With 10 questions every one of the 7 categories appears, 3 of them twice. Both stacks get the same questions.
- **Why:** `tests.jsonl` is grouped by category, so the first 10 dev questions are all `direct_fact`; their cost and behaviour would not represent the set.
- **Alternatives:** a seeded random sample (can miss a category with 10 of 192); the first 10 in the file.
- **Limits:** with 10 questions the mix is not proportional to the category sizes; good enough for a cost check, not for scoring.
- **Best practice:** stratified sampling is standard; this particular round-robin order is a custom choice.
