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
- **Built 2026-10-29 (`jobs.py`):** one worker thread, so jobs run one at a time (the budget guard counts spend only for one run in flight, T44). A job is an evaluation run; refusals (chunk set not indexed, over budget, held-out prompt not evaluated on dev) are raised when the job is submitted, before any run or job is stored. The worker opens its own SQLite connection and calls `execute` in its thread, so the spend listener records every paid call. A job moves forward only (queued, running, then done or failed; a database trigger). At startup, jobs left queued or running, and their runs, are marked failed with "interrupted: the app restarted". `GET /api/jobs/{id}` returns status, progress, message and error.
- **Revision 2026-11-02:** a job is now one of four kinds: an evaluation run, a ladder step (T50), a build (D29) or a sweep (T58), all on the same single worker, so builds and runs never overlap. The jobs table upgrades itself at connect when it lacks a kind (D29, `store.upgrade_jobs`). Ladder steps and sweeps share one run loop (`jobs.run_all`).

### D08 - Caddy basic auth - `accepted` (revised by D35: the server's Nginx asks for the password)
- **Why:** stops strangers from spending the API credits, with no application code.
- **Not best practice:** one shared password and no user identity. Production would use SSO/OIDC (Salesforce Identity, Auth0, Keycloak).

### D09 - One shared edge Caddy for TLS and routing - `superseded` by D35 (2026-11-07: the server's Nginx is the front door)
- **Decision:** a separate compose project (`deploy/edge`) runs Caddy on ports 80/443. It handles TLS for `staging.<domain>` and `<domain>`, basic auth, and reverse proxying to each environment's app.
- **Why:** certificates are issued and renewed automatically, and one entry point serves every environment.

### D10 - Secrets in `.env` files on the VPS, CI secrets in GitHub - `superseded` by D32 (2026-11-05: secrets in Doppler, no key file on the VPS)
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

### D13 - Staging and prod environments on the same VPS - `superseded` by D35 (2026-11-07: prod only)
- **Decision:** two compose projects, `rag-playground-staging` and `rag-playground-prod`, each with its own `.env`, data volume and Qdrant. **Revised by D32:** each with its own Doppler config instead of a `.env`, passed to the container by name in `deploy/docker-compose.yml`.
- **Why:** CI tests in staging before prod is touched.
- **Not best practice:** both environments share one host, so a host failure takes down both. Production would put them on separate infrastructure.
- **Cost:** about double the RAM (two apps with nomic loaded, two Qdrant instances). Fits a VPS with 8 GB.

### D14 - Observability: JSON logs and an Ops page - `accepted`
- **Decision:** structured JSON logs (request id, route, latency, tokens, cost, error). The Ops page shows spend against budget, error rate, p95 latency and the app version.
- **Why:** "how do you monitor it?" is a standard deployment question, and this answers it in the app itself.
- **Not best practice:** no central log store, alerting or tracing. Production would use an observability stack (OpenTelemetry with Grafana/Loki, Datadog, or an LLM-tracing tool).
- **Revision 2026-11-02 (D30):** the Ops page is built from stored jobs, runs and spend; how the error rate and answer times are measured is D30. The JSON logs come with Step 12.

### D15 - Global evaluation budget per environment - `accepted` 2026-10-28
- **Decision:** `BUDGET_USD` caps all evaluation spend recorded in SQLite: $60 for prod and $5 for staging (CI gates). It replaces `SWEEP_BUDGET_USD`, because spend from the ladder, sweeps and held-out runs all counts against the $60.
- **Why:** one cap covers every way of spending money, not only sweeps.
- **Funding status (2026-10-27):** the user's OpenRouter key has a $30 limit and the account a $3.12 balance (about $26.90 was spent on the Step 2 dataset). That covers the Step 5 live judge tests (about $0.01) and the first runs in Step 6 (about $0.50 each). The Step 13 experiments need about $60 more credit: raise it with the user before Step 13. Claude never uses the OpenRouter key; the user runs anything that calls it.

### D16 - Frontend built in priority order - `accepted`
- **Decision:** Story → Ask → Evaluate → Compare first, then Build, Sweep, Ops. One shared layout; make it work before polishing.
- **Why:** React is the largest time cost. The pages that carry the demo come first.

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
  - Picking the best run is built in Step 6 (`selection.pick_best`, `rag/best_run.py`); Step 5 built the gates only.
- **Built 2026-10-30, details the rule above left open (custom choices):**
  - **Which runs compete:** finished runs on every dev question, on the current dataset hash, graded by the current judge `canonical_slug`. Smoke runs, the 10-question first runs, held-out runs and failed runs never compete. Scores from another dataset or judge are not comparable, and held-out questions are never used to choose (T18).
  - **Ties:** the leader is the eligible run with the highest mean accuracy. A run is tied with it if the paired bootstrap (T09) does not find the leader's accuracy really higher, and the cheapest tied run wins. Each run is compared with the leader only, so two tied runs may differ really from each other. An exact cost tie goes to higher accuracy, then to the older run.
  - **Cost** is the mean recorded `cost_usd` per question, which includes the judge. Stack A's search fee is added to it (T53).
  - **Faithfulness gate** uses the mean over all questions, refusals included (plan.md section 4).
  - **No correction for many comparisons:** the leader is the top of many runs, so its lead is somewhat overstated, and each tie test stands alone at 95%. Not best practice; the production alternative is a multiple-comparison correction. The held-out run confirms the winner on questions it was not chosen on.
- **Tie rule kept (2026-10-31, user decision, after Stack A's S1):** S1 kept 800 tokens (4.208) over 1024 (4.313) on cost, saving about $0.03 per run. The user chose to keep the rule: it matters more at S3, where the cost gap is real, and changing a rule after seeing results would weaken the study.
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
- **Why:** no data was available. A fictional Salesforce consulting firm fits the project's topic and has no licensing issue.
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
- **Built 2026-11-02 (T58):** every guardrail above holds: one setting per sweep, Estimate then Confirm, values with a full dev run reused (oldest match), and the budget guard refusing a sweep estimated over what is left and stopping a run at the cap. The limitation is stated on the Sweep page.

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
- **Why:** hallucination is the main enterprise risk with RAG. A RAG that refuses safely is as important as one that answers well.
- **Trade-off:** prompts that make the model refuse more often can hurt the false refusal rate. Both metrics are reported, so the trade-off is visible.

### T20 - Judge calibration against human grades - `accepted`
- **Decision:** after the first real run, 30 answers are sampled, stratified by score, and graded blind by a human. Agreement is reported as: within ±1 on accuracy, and % agreement on pass/fail (accuracy ≥ 4). Target: ≥ 80% pass/fail agreement before the ladder runs.
- **Why (best practice):** an LLM judge is a measuring instrument and must be validated. "Who checks the judge?" is the first question an evaluation expert asks.
- **Limitation:** one human grader and 30 items is a light check, not a full inter-annotator study.
- **Result 2026-10-31 (calibration 1, runs 5 and 7, seed 44):** pass/fail agreement 80% (24 of 30; 95% Wilson interval 63% to 90%), within 1 point 83% (25 of 30). Of the judge's 10 passes the user confirmed 8 (49% to 94%); of its 20 fails, 16 (58% to 92%). Each stack had 3 disagreements. The target is reached exactly, with no margin, and the sample is 5/5/5 by score, not the real mix of answers.
- **What the 6 disagreements showed:** in 4 the judge gave 3 and the user 4: three day counts one too high and one 2-day duration error that led to a wrong conclusion. In 2 the judge gave 5 and the user 3: one answer gave only half of what was asked, and one was correct but left out a detail of the reference. Two judge weaknesses for the report: (1) the same kind of half answer scored accuracy 3 on one question (`multi_doc-019`) and 5 on a similar one (`multi_doc-020`, completeness 3), so accuracy must be read with completeness on multi-part questions; (2) the same one-too-high day count scored 1 on Stack A and 3 on Stack B. Day-count questions: 4 of 22 answers on the two runs were one too high; 3 of the 4 are on "from its start date to its end date" questions, which can be read as counting both ends, so that wording is a small dataset ambiguity (not changed: it would invalidate the runs).

### T48 - How the judge calibration is run - `accepted` 2026-10-30 (user decisions; details T20 left open)
- **Decision:**
  - The user grades in a terminal script, one answer at a time, and can stop and resume. It saves through the same backend as `/api/calibration`, which the Step 9 page will use.
  - The 30 answers come from the two baseline (S0) runs on all 192 dev questions, 15 from each stack. They are 30 distinct answers; each stack's sample is drawn on its own, so a question can appear twice, once with each stack's answer.
  - Sampling is equal per judge score: 15 answers from each run, split equally over the accuracy scores the judge used in that run, with a fixed seed; a remainder goes to the lowest scores. A score with too few answers is filled from the nearest scores, the lower one first on a tie.
  - **Revision 2026-10-30 (user decision, before any grade or sample existed):** the first rule took 3 answers per score of the 1-5 scale. On the full S0 runs the judge used only 1, 3 and 5 (Stack A 30/6/156, Stack B 27/5/160; about 82% scored 5), so that rule would have given 7 scores of 5 out of 30, barely testing the score most answers get. The new rule gives 5/5/5 on both stacks: 10 passes and 20 fails. Alternatives: keep the rule (7 and 23); half pass, half fail (15 and 15, a different method, says less about weak answers). The judge never using 2 or 4 is itself a finding for the report.
  - **Revision 2026-10-31 (user decisions, before any sample or grade existed):** the seed changed from 42 to 44. A review of the sample printed one question that fell in both stacks' samples, with the judge's scores for it. That question would have been the only one shown twice, so two answers were no longer blind, which could shift agreement by up to about 7 points. The new seed was fixed without looking at which answers it picks; only the 5/5/5 split was checked. Reviews must not print sampled ids or their scores. The report also gives agreement per side: of the judge's passes, and of its fails, how many the user confirmed, each with its 95% Wilson interval. These are for diagnosis only (each rests on few answers); the 80% target stays on overall pass/fail agreement.
  - The user grades accuracy only, seeing the question, the reference answer, the system's answer and the T41 score definitions, never the judge's score. The items come in shuffled order, so their order reveals neither the stack nor the score.
- **Storage (`rag/grading.py`, tables `calibrations` and `calibration_items`):** the sample is drawn once per pair of S0 runs and locked in the database, like runs and results. Only the full S0 run of each stack qualifies (finished, every dev question, S0 settings, current dataset and judge). Each run draws with its own seed (44 and 45): with one shared seed, two runs with similar scores would pick the same questions. Agreement is computed only when all answers are graded, so a partial figure cannot hint at the judge's scores. User decision 2026-10-30: a grade is final once saved, and the script asks to confirm it first.
- **Why a terminal script:** the judge must be validated before the paid ladder, and the dashboard comes later. Nothing is thrown away, because the page will reuse the backend.
- **Why both stacks:** the stacks are compared with each other, so the judge should be checked on answers from both. Both S0 runs are needed for the ladder anyway.
- **Why equal per score:** answers scoring 5 may dominate, and a random sample would barely test whether the judge spots weak answers.
- **Limits:** the 80% target then describes this balanced mix, not all answers, and the report must say so. Faithfulness, a gate in T08, gets no human check here, and the report must state that too. One human and 30 items stay a light check (T20): at exactly 80% (24 of 30), the 95% Wilson interval is 63% to 90%, so reaching the target does not rule out a true agreement well below it, and the report must give the interval. The 80% target is a custom choice.
- **Alternatives:** building the page first (delays calibration); a spreadsheet (an extra import step, and typos); one stack (cheaper, but Stack A's answers go unchecked); half pass, half fail, or the run's own mix (say less about weak answers); grading faithfulness too (about 45-60 minutes, with no target set).
- **Best practice:** stratified sampling and blind grading are; the equal allocation and the fill rule are custom choices.

### T21 - Reranking as a ladder step - `accepted` (reranker model `gpt-4.1-nano` accepted 2026-10-28)
- **Decision:** S5 retrieves 20 candidates, an LLM reranker (`gpt-4.1-nano`, temperature 0, structured output) reorders them, and the top K are kept. The reranker is applied the same way to both stacks.
- **Why:** reranking is one of the most widely recommended RAG improvements.
- **Why an LLM rather than a cross-encoder:** the common open-source cross-encoders read at most 512 tokens, so they would truncate our larger chunks. This is the same unfairness that removed MiniLM. An LLM reranker reads whole chunks.
- **Trade-off:** extra cost (about $0.10 per run) and latency. Both are reported.
- **Implementation (2026-10-28, `rag/rerank.py`):** listwise ranking as in RankGPT (Sun et al., 2023): the model returns every passage number, most useful first, as structured output; it sees chunk texts only, no source paths. `RERANK_CANDIDATES = 20` in `settings.py`. An invalid ranking (duplicates, unknown numbers, missing passages) is completed as RankGPT's `receive_permutation` does: valid first mentions kept, missing passages appended in retrieved order. Each completed ranking is flagged `repaired`, so the repair rate can be reported and a model that often fails is visible.

### T22 - Answer models reduced to 3 - `accepted`
- **Decision:** `gpt-4.1-nano` (cheap), `gpt-4.1-mini` (mid), `gpt-6.1-sol` (latest).
- **Why:** comparing models is not a RAG technique (the same reasoning as T14). Three price points are enough to show the cost trade-off, and they save budget and time.

### T23 - Metrics display: 8 in the report, 4 headline metrics live - `accepted`
- **Decision:**
  - The report shows all 8 core metrics (MRR, Recall@K, nDCG@K, Hit@K, Accuracy, Completeness, Relevance, Faithfulness), plus trust and operational metrics.
  - The live dashboard defaults to 4 headline metrics (MRR, Recall@K, Accuracy, Faithfulness), with a "show all" toggle.
- **Why:**
  - The written report has room to explain every metric.
  - In a live session, 4 metrics map to two plain questions: did we find it, and did we say it correctly?
  - When the app is shown live, use the 4-metric view.

### T24 - Overlap values reduced to 0% and 25% - `accepted`
- **Why:** 10% and 50% rarely change the conclusion. Dropping them saves runs.
- **Revision 2026-10-27 (user decision, after T27's overlap became 200 tokens):** ladder step S2 picks the best overlap from {0%, about 20% (S0's 200/1024 share), 25%}, at S1's chunk size, the same way S1 picks the best chunk size. A fixed 25% would only be a small change from S0's 20%. Cost: about one extra run per stack, since the 20% run already exists from the size sweep. Any other overlap (0-50%) is available on the dashboard (T35).

### T25 - Wikipedia dataset moved to phase 2 - `accepted`
- **Why:** its keyword signal is weak (it has no gold passage labels in our schema), and it is unrelated to the knowledge base's domain. Removing it halves the runs.
- **Consequence:** synthetic-data bias (T11) has no external check in the report. Listed as a limitation.

### T26 - Report rules - `accepted`
- **Decision:** the README findings and the report must include:
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
- **Why:** lets anyone using the dashboard try any configuration live, not only the precomputed grid.
- **Ranges (custom choice):** 2,048 tokens stays far below both embedding models' context (OpenAI's 4,096-token chunk limit for vector store files, nomic's 8,192). Below 64 tokens a chunk rarely holds a full fact. 50% overlap is OpenAI's own default (800/400), the upper end of common practice.
- **Revision 2026-10-29 (T45):** top-K is 1-8, not 1-20.
- **Revision 2026-11-02 (D29):** a chunk set not yet built on a chosen stack is offered by the settings panel and built on the Build page, each with an estimate of its chunks and cost and a confirming click, and only on the stacks that lack it. No build time is shown: Stack A builds were never timed and Stack B was measured once (84 chunks in 81 s, model load included), so a time would be invented.
- **Trade-off:** more chunk sets to store and index (each a few cents of OpenAI embedding cost and about a minute). Results outside the ladder are exploratory: only dev questions, and the paired bootstrap still decides what is an improvement.

### T36 - System prompt editable as named versions - `accepted` 2026-10-27
- **Decision:** the answer model's system prompt is editable on the dashboard. Each saved edit is a named, immutable version; every run stores the version and its hash. The default version is used by S0, the ladder, the held-out confirmation and the CI gate.
- **Why:** the prompt strongly affects accuracy, faithfulness and refusals (T19), so it is a real RAG setting. Versioning keeps every result reproducible.
- **Rule:** a prompt change is one variable, compared on dev questions only with the paired bootstrap. Never tuned on held-out questions.
- **Trade-off:** prompt tuning can overfit the dev questions; the held-out confirmation is what guards against it.
- **Revision 2026-10-29 (user decision): the prompt is a ladder step, S6** (the stronger answer model moves to S7). The ladder with the default prompt only would find the best settings for that prompt, not the best configuration for the demo. S6 runs at most 4 prompt versions, all written before the step runs, on the 192 dev questions at S5's configuration, and keeps the best (same selection as the other steps). The default prompt is used from S0 to S5 and in the CI gate. Held-out runs may use the default or a version that has a finished dev run (enforced in `pipeline.start_run`); held-out questions confirm a choice, never make one. Limit, stated in the report: one-variable steps never guarantee the best combination (settings chosen with the default prompt may not be best with another). Cost: about $0.23 per version per stack at `gpt-4.1-nano`.
- **Default text approved by the user 2026-10-28** (`DEFAULT_TEXT` in `rag/prompts.py`, custom wording, not a standard): role (internal assistant of the fictional firm), audience and topics, answer only from the retrieved context, say when the answer is not in the knowledge base, compute durations and totals from the context, answer concisely. A first draft without role and task was rejected by the user. The text gives the task type only, never an answer, and is identical for every run on both stacks.

### T37 - Hybrid search (keyword + vector) as a setting - `accepted` 2026-10-27
- **Decision:** a hybrid search on/off setting, available on the dashboard and in sweeps, not a ladder step. Stack B: Qdrant with a sparse BM25 model from fastembed (`Qdrant/bm25`, no torch) next to the nomic dense vectors, fused with reciprocal rank fusion (RRF) in Qdrant's query API. Stack A: OpenAI's own hybrid mode (`ranking_options.hybrid_search` weights, with `ranker: none`), found in Step 4 (see below).
- **Why:** keyword matching finds exact strings (commands, error messages, names) that dense vectors often rank low; about 15% of the tests (`exact_term`) ask for these. Widely used in production RAG, cheap (no LLM calls).
- **Alternatives rejected (user decision):** query rewriting (our questions are already precise; one more LLM call per question), score threshold (the two stacks' scores are on different scales), neighbour-chunk expansion.
- **Trade-off:** the two hybrid modes are similar, not identical: OpenAI's keyword scoring is undocumented, Stack B uses BM25.
- **Step 4 result (2026-10-27):** Stack A has an equivalent: `ranking_options.hybrid_search` with `embedding_weight` and `text_weight`, fused by RRF (k=60, see T12). It is only effective with `ranker: "none"`. So hybrid search can be part of the comparison.
- **Stack B detail (custom choice):** `HYBRID_PREFETCH = 50` candidates from each list (dense and BM25) before RRF, at least 2.5 times the maximum top-K of 20 (since T45 the maximum is 8, so the margin is larger). Qdrant's RRF uses its default constant.

### T38 - t-SNE embedding map for the report - `accepted` 2026-10-27
- **Decision:** a script draws a 2D t-SNE map (scikit-learn, seed 42) of one chunk set's embeddings for each stack: chunks coloured by KB folder, test questions overlaid, and optionally one question with its gold chunks and its retrieved chunks marked. Stack B uses nomic embeddings (local, free). Stack A's embeddings cannot be read back from the OpenAI vector store, so the chunks are embedded again with an OpenAI embedding model (about $0.01). Which one is still to decide when the map is built: OpenAI does not document the vector store's model (Step 4 result below). Default chunk set: 200 tokens, so the map has enough points to read.
- **Why:** shows readers how the documents and questions sit in embedding space, and why a question can land near the wrong document.
- **Limitations (stated with the image):** t-SNE keeps local neighbourhoods but not global distances, so the distances between clusters and the cluster sizes mean nothing; the two stacks' maps are separate fits, so only their structure can be compared, not their axes. It is an illustration, not evidence: results come from the metrics.
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
- **Consequences:** Stack A-only settings (the OpenAI ranker) are shown only when Stack A is selected; side-by-side results with `ranker: auto` are labelled, since Stack B has no equivalent. The ladder (S0-S7) is a fixed set of configurations, so it states its Stack A ranking values explicitly (still to decide, T12).
- **Best practice:** yes. Explicit configuration recorded per run is standard for reproducible evaluation.
- **Revision 2026-10-28 (user decision): one identical menu for both stacks.** Different menus would make a side-by-side comparison not like for like. The menu is the same for A and B: chunk size, overlap, top-K, hybrid on/off, reranking on/off, answer model, prompt version; the user still sets every one. Stack A's hybrid switch is translated into fixed OpenAI settings (custom choice, not a standard): off = ranker `none`, `embedding_weight` 1, `text_weight` 0, `score_threshold` 0 (meaning search only, like Stack B off); on = ranker `none`, both weights 1, `score_threshold` 0 (both lists fused equally by RRF, like Stack B on). The run's `hybrid` flag is what the user set on both stacks, and `openai_ranking` stores the translated values.
- **Revision 2026-10-29 (user decision): each stack runs independently; supersedes the 2026-10-28 revision.** The user configures each stack on its own: Stack A offers OpenAI's own search options (ranker, the two hybrid weights, score threshold), Stack B its hybrid on/off switch. No setting of one stack is mapped onto the other. Why: the first real run (2026-10-29) showed the 2026-10-28 mapping for 'off' (ranker `none`, weights 1:0) found a gold document for 2 of 9 answerable questions on Stack A (Stack B: 9 of 9), confirming T12's finding that this OpenAI mode is not plain vector search. A head-to-head result states each stack's settings (T12 reporting rule).
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
- **First real run (2026-10-29, runs 1-2, 10 dev questions each, S0):** the estimate was 64% above the real cost on Stack A and 60% on Stack B, failing the plan's check (within 50%). Cause, proven from the spend rows: counted input cost matched within 1-7% ($0.00858 estimated, $0.00869 and $0.00918 actual); the error was entirely the assumed output lengths (answers 150 tokens assumed, 29 measured; judge replies 200 assumed, about 58 measured; the judge's output costs $2.50 per million tokens). Two of 20 `gpt-4.1-nano` calls were billed below list price (consistent with OpenAI's discount for cached prompt input), which makes the estimate slightly high, never low.
- **Revision 2026-10-29 (user decision):** assumed output lengths set to the measured means, 30 tokens per answer and 60 per judge reply (source: runs 1-2, `gpt-4.1-nano`; other answer models keep these values, and `gpt-6.1-sol`'s hidden reasoning is covered by the budget guard's "largest so far" rule). The check is repeated on the next 10 round-robin dev questions (batch 2), not on the questions the lengths were measured on.

### T44 - Spend recorded per paid call - `accepted` 2026-10-29 (user decision)
- **Decision:** a `spend` table in SQLite holds one row per paid OpenRouter call, written as soon as the call returns. Budget used (D15) = the sum of that table. A running job checks the budget before every question and stops cleanly when the next question could exceed `BUDGET_USD`.
- **Why:** the cost saved with each result is only written after judging, so money spent on a question that fails halfway would never be counted.
- **Alternatives:** sum of `results.cost_usd` (simpler; undercounts failed questions).
- **Limits:** a call that is billed but fails before its reply is read (for example a structured reply cut off at its length limit) reports no cost and is not recorded. OpenAI embedding cost for Stack A builds (under $0.05 per build) is not on OpenRouter and is not counted.
- **Best practice:** yes; per-call usage records are the usual basis for cost tracking.
- **Measured 2026-11-01 (open question closed):** OpenAI bills Stack A's vector store searches at $0.0025 each. The user's bill matches the stored runs exactly: 20 searches = $0.05 (2026-10-29), 192 = $0.48 (10-30), 1,344 = $3.36 (10-31); $3.89 in all, not in `spend`, `results.cost_usd` or `BUDGET_USD`. Each question makes one search, so a 192-question Stack A run costs about $0.48 more than recorded. Within one stack the fee is the same for every configuration, so ladder decisions so far stand; a Stack A vs Stack B cost comparison is wrong until the fee is counted. Counted since T53.
- **Budget guard (2026-10-29, user decisions; built in `rag/pipeline.py`):** a run whose T43 estimate is above what is left of `BUDGET_USD` (budget minus all recorded spend, every run and spend outside runs) is refused and nothing is stored; an estimate exactly equal is allowed. Before each question, the run stops if spend so far plus the next question's assumed cost would pass `BUDGET_USD`. The assumed cost is the larger of the question's T43 estimate and the run's most expensive question so far (custom rule, not a standard: the estimate is low for `gpt-6.1-sol`'s hidden reasoning tokens). A run stopped this way is marked `failed` with the message "BudgetExceeded: Budget reached: ..." and keeps its results (alternative not taken: a new `stopped` status, which would change the runs table and every reader of the status). `BUDGET_USD` unset means $0, so a machine without it cannot spend.
- **Limits of the guard:** the real cost is known only after a question's calls return, so total spend can pass the cap by at most the error of one question's guess (about $0.003-$0.05 per question at plan.md 1.3 prices). Since T51 the guard counts spend in flight within a run; total spend can pass the cap by at most the error of the guesses of one batch. Two runs at once are still not allowed (one job worker).

### D30 - What the Ops page measures - `accepted` 2026-11-02 (user decisions; custom choices within D14)
- **Decision (user):** the error rate is the share of background jobs (runs, ladder steps, builds, sweeps) finished in the last 7 days (`OPS_WINDOW_DAYS`) that failed by a fault, with every failure listed newest first. A stop at the budget cap (error starting `BudgetExceeded:`) and a job cut off by an app restart are counted and shown apart: they stop work on purpose, not through a model or a stack. Answer time is p50 and p95 per stack of the time to search and answer one question (not grading), over questions of runs started in the last 7 days, with the number of questions.
- **Built:** `GET /api/ops` (`rag/ops.py`): spend against `BUDGET_USD` counted as the budget guard counts it (paid calls plus Stack A's search fees), split into runs and calls outside runs (Ask, enrichment); the failures; the answer times; the app version and whether Qdrant answers (as `/api/health`, D17).
- **Percentiles:** interpolated between stored times (Python's `statistics.quantiles` with the "inclusive" method, the same as numpy's default). One question gives that time for both.
- **Limits:** only jobs count, so a run started by a terminal script (`scripts/first_run.py`) is not in the error rate. Ask's questions are not stored, so their time is not counted. A stored question has no time of its own; its run's start places it in the window. Request errors and latency per route come with the JSON logs of Step 12.
- **Best practice:** p50 and p95 are standard service measures; the window, the causes and counting jobs instead of requests are custom choices for an app without request logs yet.

### T58 - Sweeps vary one setting against the base configuration - `accepted` 2026-11-02 (user decisions; custom choices within T15)
- **Decision (user):** a sweep varies any one setting of the settings panel: chunk size, overlap, top-K, chunking method, reranking, answer model, prompt version, Stack B hybrid, or one of Stack A's ranker, weights and threshold (a stack's own setting on that stack only, T40). At most 6 values (`SWEEP_MAX_VALUES`), the base configuration's own value included and added if missing, since every other value is compared with it. Each value is a full run on the 192 dev questions. One sweep job per stack builds any missing chunks, then runs the values still missing, in order; a failure stops the rest.
- **Results (user):** each value's accuracy and MRR with their 95% intervals (T52), and the paired change against the base value (T09), read as better, worse or no real difference. Labelled exploratory: dev questions only, no winner picked; the ladder makes the decisions.
- **Reuse:** a value whose settings match a full dev run of the current dataset and judge reuses it, the oldest match, like the ladder (shared `ladder_runs.stored_runs`); nothing is paid twice. Enrichment is counted once per chunk set.
- **Built:** `POST /api/sweeps/plan` gives each value with its stored run and scores, or its estimate, and the total for the values still to run; nothing stored. `GET /api/sweeps/latest/{stack}` gives the stack's latest sweep job, so the page shows a running sweep as soon as it opens. `POST /api/sweeps` queues one job (`kind = sweep`) running the missing values in order, each after building its chunks, through the run loop shared with the ladder (`jobs.run_all`); refused with nothing stored (409) if a sweep of that stack waits or runs (a partial unique index also stops two at once), if every value has a run, or if the estimate, enrichment included, is over the budget. The jobs table gains kind `sweep`; `store.upgrade_jobs` now copies whatever columns the old table has, so a table from before builds or from the build era both upgrade.
- **Limits:** one setting at a time misses interactions (T15). A sweep and a ladder step queued on the same stack before either runs can both run one configuration: results do not change (the oldest run wins), but that run is paid twice. Many values tested at once can show a real-looking difference by luck: no correction for multiple comparisons (as T57). The estimate is the T43 estimate; Stack A index builds are not counted (T44).
- **Best practice:** one-factor sweeps with paired tests on the same questions are standard for exploration; the limit of 6 and the base-value rule are custom choices.

### D29 - Builds run as background jobs; the jobs table upgrades itself - `accepted` 2026-11-02 (user decision on the upgrade; other choices custom)
- **Decision:** the Build page prepares one chunk set on one stack per job (`kind = build`), through the same worker as runs (D07), so builds and runs never overlap and the budget guard keeps working (T44). `POST /api/builds/estimate` gives the set's id, chunk count, what enriching it would still cost, the stacks it is built on and what is left of the budget; it saves only the free base split. `POST /api/builds` queues a build (202), and is refused with nothing stored (409) if the set is built on that stack, if its build is waiting or running (a partial unique index also stops two clicks at once), or if its enrichment is estimated over the budget. `GET /api/builds` lists what is built and every build job. The ladder and the Build page share `rag/builds.py`.
- **Upgrade (user decision):** SQLite cannot change a CHECK in place, so a jobs table made before build jobs is recreated at connect: new table, rows copied with their ids, old table dropped, new one renamed, all in one transaction under a write lock, with the check repeated under the lock. The trigger and indexes are then recreated. It runs the same on the VPS copy. Checked on a copy of the real database: all 5 rows kept, foreign key and integrity checks clean.
- **Alternatives:** recreate the table by hand (the VPS copy would need the same step); no job, building inside the request (a large Stack B build keeps the page waiting for minutes and could overlap a run).
- **Costs:** a fixed build is free on Stack B (local embedding); on Stack A it uploads files to OpenAI, whose storage fee is not counted (T44). Enrichment is paid once per chunk set, shared by both stacks.
- **Limits:** no progress inside a build (queued, building, built or failed only); no rebuild or delete (D24).
- **Best practice:** yes for running long work outside the request and for an all-or-nothing table rebuild (SQLite's documented way to change a table's constraints). Not best practice: a hand-written upgrade instead of a migration tool; with one changed table this stays simpler.

### T57 - What the Compare page reads - `accepted` 2026-11-01 (user decisions; custom choices, built on T09, T18, T20)
- **Decision:** `GET /api/compare?before=&after=` takes two finished runs that asked every question of the same split, on the same dataset version. It returns both reports, the paired change (T09) of accuracy and MRR, read both ways (better, worse, or no real difference), and the questions fixed or broken. Runs of different stacks may be compared; each keeps its own settings and cost.
- **Fixed or broken:** a question crosses the pass mark of T20 (accuracy 4 or more) between the two runs. A move on one side of it, such as 4 to 5 or 1 to 3, is only counted, not listed. A custom rule: it matches what calibration checked, and it hides small moves that a judge with 80% agreement cannot tell apart.
- **Refused:** the same run twice, a sample or smoke test (their questions are not comparable, and the manual keeps them out), a dev run against a held-out run (different questions, so a paired test is impossible), an unfinished run, another dataset version.
- **Held-out:** two held-out runs compare overall only, with no question list (T18, T56).
- **Limits:** no correction for many comparisons (T08): comparing many pairs will find a real-looking difference by luck. Accuracy and MRR are tested; other scores are shown side by side without a test.
- **Best practice:** yes for paired testing on the same questions; the pass-mark rule for fixed and broken is custom.

### T56 - What the Evaluate page reads - `accepted` 2026-11-01 (user decision on the held-out rule; other choices custom)
- **Decision:** `POST /api/runs/estimate` gives questions, cost, time and what is left of the budget, and stores nothing. It uses the run's own `pipeline.plan_run`, so an estimate and the run's budget check are the same number. Over budget is shown, not refused: the start refuses it. `GET /api/runs` lists every run, newest first, with settings and progress and no scores, so the page can return to a run after you leave it. `GET /api/runs/{id}/report` gives a finished run's scores.
- **Held-out rule:** a held-out run reports overall scores only, with no category scores and no question table. Reading them could steer later choices (T18); `GET /api/runs/{id}/answers` already refuses such runs.
- **Time:** `SECONDS_PER_QUESTION`, 1.35 s on Stack A and 2.5 s on Stack B, measured on S2 (384 questions at 5 at a time, K=2, no reranking). A custom figure: reranking, a higher K or a stronger model will take longer, so the page says "about".
- **Failed runs:** no report, since a partial run would give scores on an arbitrary part of the questions. Their answers stay readable through View answers.
- **Runs from another dataset version:** no report (422 with the reason). Their questions may have changed, and `best_run` leaves them out for the same reason. All 21 stored runs use the current version.
- **No refusal rate is invented:** every run the app can start includes unanswerable questions, as `round_robin` covers each category from 7 questions up. A hand-made run without any gets a 422, not a made-up 1.0, which would pass a gate.
- **Check on real data:** the report gives the recorded accuracy exactly for run 19 (Stack A, 4.188) and run 15 (Stack B, 4.323).
- **The page:** Evaluate waits for a fresh Estimate, and any change of settings or question set clears it. "Both side by side" starts two runs, which go one at a time. The list is polled every 2 s only while a job works on a run, so leaving and coming back keeps following it. "Open in Ask" loads that run's exact settings into the panel, overwriting the saved values, and picks the question. Bands follow plan.md 4.9; keyword recall and the false refusal rate have none.
- **Limits:** Evaluate can still start held-out runs with any settings (T50), and overall scores alone leak a little if repeated. Nothing stops the same paid run being started twice, except that each start needs a new Estimate. On "both", if the second start is refused, the first run still goes ahead. A report reads the chunk set file for nDCG, so a database moved without `var/chunk_sets` gives a plain 500: the VPS copy step must carry those files too.
- **Best practice:** yes for reporting scores from one calculation, and for keeping held-out detail out of tuning.

### T55 - The shared settings panel - `accepted` 2026-11-01 (user approved the manual text; custom choices, within T35 and T54)
- **Decision:** `GET /api/panel` gives the page the ranges, the answer models and S0's values, so nothing from `settings.py` is copied into the frontend. The page checks the values only to say why in plain words; the API checks them again. The panel opens with the last values used on this browser (`localStorage`), or S0's. A saved model or prompt that no longer exists falls back to S0's. "Both side by side" sends two separate requests, each with its own stack's search settings, so one stack can fail while the other answers.
- **Live demo:** the user sets the best configuration once and asks one question; Ask then opens with it loaded on that browser. Nothing loads the best run by itself.
- **No cost shown before asking:** one question costs a fraction of a cent, guests should not confirm each one, and T54's check still refuses a question over the budget. The cost is shown with the answer. Every other paid action keeps its estimate and confirmation.
- **Alternatives:** a fixed list of models in the page (breaks the one-place rule); loading `best_run` automatically (it can differ per stack and needs a choice between stacks; a later button on Story can do it).
- **Limits:** the panel does not know which chunk sets are built, so an unbuilt one is refused after pressing Ask, with nothing paid; building from the panel comes with the Build backend. The values live in one browser: another browser opens with S0's.
- **Revision 2026-11-02 (D29):** the panel now knows: it reads the built chunk sets (`GET /api/builds`), says which chosen stacks lack the panel's chunks, and offers to build them, showing any build of them already waiting or running.
- **Best practice:** yes for one source of truth and validation at the API; browser storage is fine for a convenience.

### T54 - Questions on the Ask page - `accepted` 2026-11-01
- **Decision:** `POST /api/ask` answers one question with the settings panel's values, through the same `pipeline.search_and_answer` as a run. It stores no run and no result, only what it cost. A test question is also judged; a typed one is not. Only dev test questions can be picked: a held-out id gets the same 404 as an unknown one (T18). Any saved prompt version may be used. Every question is checked against `BUDGET_USD` first (T43 estimate; the judge only for a test question).
- **Fee:** with no stored result, T53's count misses Ask, so each Stack A search outside a run writes one `spend` row (`run_id` NULL, model `openai/vector-store-search`, 0 tokens) as soon as the search returns. A later failure still leaves it paid. Runs keep T53's count, so no search is counted twice.
- **Alternatives:** a separate table for searches (a second place to sum, for the same result); storing Ask questions as runs (a run asks declared test questions, so a typed question has no place in one).
- **Errors:** a failure of OpenAI, OpenRouter or Qdrant is a 502 with the service's message, as a failed run shows it; anything else is a bug and a plain 500.
- **Limits:** two guests asking at the same moment can each pass the check, so spend can pass the cap by about one question. A reasoning model can pass it by more, since its reasoning tokens cannot be estimated (T43). No limit on the length of a typed question: the estimate counts its real tokens, so a very long one is refused only when it is over the budget. A chunk set that is not indexed is refused; building it from the panel comes with the Build backend.
- **Best practice:** yes for the shared path and the held-out refusal; the budget race is accepted for a study tool behind basic auth.

### T53 - Stack A's search fee counts as spend - `accepted` 2026-11-01 (user decision)
- **Decision:** `STACK_A_SEARCH_USD = 0.0025` in `settings.py`, one fee per Stack A question, with or without the reranker. It counts in `spend.total` (so in `BUDGET_USD`), in every estimate and in `cost_per_question`. The user may raise `BUDGET_USD` when needed; the cap stays.
- **How:** worked out from stored results (Stack A results times the fee), not stored. Runs and results are locked by triggers in `store.py`, so old runs could not gain the fee, and storing it only for new runs would make old and new Stack A runs incomparable. `results.cost_usd` stays paid LLM calls only.
- **Why:** the study compares the stacks on cost, and the fee is about twice Stack A's LLM cost per question at S0. It changes no ladder decision (one stack, same fee), but `best_run` ranks both stacks together, so a tie (T08) between stacks can now go to Stack B.
- **Source:** measured from the user's OpenAI bill (see T44), not a published price quoted by us. Update by hand if OpenAI changes it; the past would then be recomputed at the new fee.
- **Limits:** a question that fails after its search is not counted (no stored result; none so far: the bill matched exactly). Within a batch the fee is covered by each question's assumed cost until its result is stored. OpenAI's embedding cost for index builds stays uncounted (T44). Searches that store no result, on the Ask page, are counted by T54.
- **Alternatives:** one `spend` row per search (exact on failed questions, but a backfill of 1,556 rows and a second source of cost); a warning on every comparison instead (leaves the budget blind).
- **Best practice:** yes for the principle (count every cost of a compared system); a fixed price in code is a shortcut, production would read the provider's usage API.

### T51 - Five questions at a time within a run - `accepted` 2026-10-31 (user decision; custom choice)
- **Decision:** `PARALLEL_QUESTIONS = 5` in `settings.py`. The first question of a run goes alone, then batches of up to 5. A batch ends completely before its results are stored, in question order. Before each batch, the guard keeps only the questions whose assumed costs fit together in what is left of `BUDGET_USD`.
- **Why:** one question takes about 5 s, one 192-question run about 15 minutes, and a ladder about 8 hours or more. Scores do not depend on the order of questions, since each is answered and judged on its own.
- **Alternatives:** a sliding window (faster, but the budget and result order get harder to reason about); more than 5 (more rate-limit risk).
- **Limits:** per-question `latency_s` of a parallel run is not comparable with a one-at-a-time run. On Stack B it includes waiting for the embedding lock, so do not report latency across S0, S1 on Stack A and later runs; a latency comparison needs its own one-at-a-time measurement. A rate-limit failure fails the run, and running the step again pays for that run again. Measured on Stack B's S1: 43 minutes against 82 for Stack A's, about 1.75 s per question, no rate-limit failure.
- **Best practice:** yes for bounded parallelism; the batch size is a custom choice.

### T52 - Intervals and change marks on the ladder chart - `accepted` 2026-10-31 (plan.md Step 9 asks for them; the method is a custom choice)
- **Decision:** each kept point on the Story chart shows a 95% percentile bootstrap interval of that run's mean, resampling its questions (same 1,000 resamples and seed as T09). A `+` or `-` beside a point means the paired test of T09 finds a real rise or fall from the step before, on that metric. The table and the CSV show each option's interval.
- **Why two intervals:** the bars show how uncertain one score is. The paired test decides whether a change is real, and it is narrower because both runs answer the same questions, so two bars can overlap while a change is still real. Reading overlap as "no difference" would be wrong; the mark is the answer.
- **Alternatives:** Wilson or normal-theory intervals (do not fit means of 1 to 5 scores as simply); marking against S0 instead of the step before (hides which step caused the change).
- **Limits:** a kept run can sit below the step before without a mark, because the tie rule (T08) compares with the leader. There is no correction for many comparisons (T08). Intervals are on dev questions; the quoted result stays the held-out one.
- **Not a change to decisions:** the shared `percentile_interval` keeps T09's exact seeded calculation, pinned by a test, and is cached per process since stored runs never change.
- **Best practice:** percentile bootstrap is standard; the display rule is a custom choice.

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
- **Decision:** an `indexes` table records, for each (stack, chunk set), the OpenAI vector store id (Stack A, store named `rag-playground-{APP_ENV}-{chunk set id}`) or the Qdrant collection name (Stack B, the chunk set id), with its chunk count. An index is built once from the saved chunk set; building it again is refused. A run searches the index recorded for its stack and chunk set, with its own stored settings (Stack A: its stored `openai_ranking`; Stack B: its `hybrid` flag). (The fixed mapping of a shared hybrid switch onto OpenAI ranking values, built here first, was removed the same day: each stack takes its own search settings, T40 revision 2026-10-29.)
- **Why:** Stack A's store id is only known once OpenAI creates the store, so it must be stored to be found again; a failed Stack A upload deletes its store, so no half-filled paid store is left; a Qdrant collection missing chunks is refused.
- **Limits:** no rebuild or delete yet (a changed chunk set needs a new id or a manual clean-up); the run does not store the Stack A store id itself, only its chunk set id. If the clean-up delete itself fails, or the process is killed during an upload, an unrecorded OpenAI store is left (never searched, but billed for storage until deleted by hand).
- **Best practice:** yes; a registry of built indexes is the usual way to tie experiments to their index.

### T46 - Small runs take questions round-robin by category - `accepted` 2026-10-29 (user decision; custom choice)
- **Decision:** a run of fewer questions than the full dev set (such as the first real 10-question run) takes the first question of each category in turn, then the second of each, until it has enough (`datasets.splits.round_robin`), in the file's category order. With 10 questions every one of the 7 categories appears, 3 of them twice. Both stacks get the same questions.
- **Why:** `tests.jsonl` is grouped by category, so the first 10 dev questions are all `direct_fact`; their cost and behaviour would not represent the set.
- **Alternatives:** a seeded random sample (can miss a category with 10 of 192); the first 10 in the file.
- **Limits:** with 10 questions the mix is not proportional to the category sizes; good enough for a cost check, not for scoring.
- **Best practice:** stratified sampling is standard; this particular round-robin order is a custom choice.

### D25 - The request that starts an evaluation run - `accepted` 2026-10-29 (follows T35, T40, T46)
- **Decision:** `POST /api/runs` takes every setting of the settings panel, all required (no hidden defaults, T40): stack, chunk size and overlap (T35 ranges), top-K (1-8, T45), reranking, answer model (the catalogue only), prompt version, and `questions` (`dev` = 192, `heldout` = 48, `smoke` = 20 dev questions round-robin by category, T46). Each stack takes its own search settings (T40 revision 2026-10-29): Stack A `openai_ranking` (ranker `none` or `auto`, two weights of 0 or more, threshold 0-1), Stack B `hybrid`; sending the other stack's field is refused. Unknown fields are refused. It returns 202 with the job id; the UI polls `/api/jobs/{id}` (D07).
- **Stack A's `hybrid` flag** (stored for every run) is derived, not sent: it records whether OpenAI's keyword list takes part, `text_weight > 0`. Custom rule; with ranker `auto` the weights have no measurable effect (T12), so it then records the setting sent, not a measured effect.
- **Refusals, nothing stored:** 404 (chunk set not indexed on that stack, unknown prompt version), 409 (over the remaining `BUDGET_USD`), 422 (invalid settings, or a held-out run with a prompt version not evaluated on dev). The message says why.
- **Best practice:** yes; validation at the API boundary with the reason returned to the user.
- **Revision 2026-10-30 (T47):** the request also takes `chunking_method`, `fixed` or `llm_enriched`, required like every other setting. `llm_enriched` needs that chunk set to be indexed; otherwise the run is refused with 404, which also covers a set still being enriched.

### D28 - The app serves one dataset; a new one is a developer job - `accepted` 2026-10-30 (user decision)
- **Decision:** there is no data import. The app serves the one committed dataset, and changing it stays out of scope for this study. The known risk below is recorded and must be fixed before anyone swaps the data.
- **Known risk (not fixed):** chunk set ids (`fixed__c1024__o200`) and the `indexes` table name only the method, size and overlap, not the dataset. If the documents were replaced, `chunk_sets.load_or_build` would return the old saved chunks and `indexes.lookup` the old index, so a run could search the old documents while recording the new `dataset_sha256`. Enriched sets check their chunks against the documents, but fixed sets do not. This cannot happen with the current data.
- **The fix, when needed:** include the dataset hash in the chunk set's identity, or give each dataset its own environment and database.
- **What a new dataset needs:** Markdown documents in the KB folder; `tests.jsonl` with questions, reference answers and gold documents in the current seven categories (the current set cost about $27 to generate, plus human review); a judge calibration (T20); a review of the gates (T08), the default prompt (T36) and the top-K cap (T45, set for a small KB); and new runs, since best-run selection ignores other datasets. Without prepared questions, **Ask** still works, but no run can be scored.
- **Why:** the study needs one fixed dataset, so that every result stays comparable.
- **Not best practice:** a product would version its datasets and tie every index to a dataset version, and would have an import flow.

### D26 - SQLite WAL mode - `accepted` 2026-10-30 (user decision)
- **Decision:** the database uses SQLite's write-ahead log (`PRAGMA journal_mode = WAL` in `store.SCHEMA`; the setting persists in the database file).
- **Why:** with the background job writing results while the dashboard polls `/api/jobs/{id}` (D07), the default rollback journal locks readers out while a write commits; Python's driver gives up with "database is locked" after 5 s. Reproduced on 2026-10-30 with a writer holding the exclusive lock a commit takes: a new `store.connect` failed with exactly that error, and passes with WAL. Writes are single small rows (milliseconds), so the risk was low, not zero; no such error had been seen in a real run.
- **Alternatives:** keep the default journal and rely on the 5-second wait (simple, but a rare random failure during paid runs); a client-server database (far more than one writer needs).
- **Trade-off:** two small extra files next to the database (`-wal`, `-shm`), inside the same Docker volume. Existing databases convert when next opened. A backup must use SQLite's backup command, not a copy of the `.db` file alone.
- **Best practice:** yes; WAL is the usual set-up for one writer with concurrent readers.

### D27 - Strict types in run requests - `accepted` 2026-10-30 (user decision)
- **Decision:** `RunRequest` and `OpenAIRanking` (D25) use Pydantic's strict mode, so `"3"` is not accepted as K=3, `"yes"` as reranking on, or `0` as hybrid off. Whole numbers remain valid for the float fields (weights, threshold), because JSON has one number type.
- **Why:** runs are paid and permanent (D21), so a stored setting must come from an exact value, with no conversion to reason about. Before this, Pydantic's default (lax) mode converted such values; the stored setting always matched their meaning, so no stored run is affected. Found by Claude when checking Antigravity's review of D25.
- **Alternatives:** keep lax mode (accepts more input, but every caller must know the conversion rules).
- **Trade-off:** a hand-written API call with a loosely typed value gets a 422 instead of working.
- **Best practice:** yes; an API that refuses ambiguous input is easier to trust.

### T49 - A ladder step with one option is kept only if its gain is real - `accepted` 2026-10-30 (user decision)
- **Decision:** S4 (enrichment) and S5 (reranking) each test one option against the step before, on each stack separately. The option is kept for the later steps only if the paired bootstrap (T09) finds accuracy or MRR really better on dev questions. Otherwise the ladder continues from the step before, and the step goes under "what did not work" (T26). `fixed` stays the default until then.
- **Why:** the plan said each step "keeps the winner", which did not define a winner for a step with one option. Keeping an option with no shown benefit would add cost and complexity to every later step.
- **Scope:** the stacks may end with different settings, since each runs independently (T40 revision). S1-S3 and S6 still pick the best of several values, and S7 stays a reported cost trade-off.
- **Alternatives:** keep every option whatever the result (simple, but keeps what did not help).
- **Best practice:** using a significance test to accept a change is common; applying it this way, per step and per stack, is a custom choice, and it has no correction for many comparisons (see T08).

### T50 - How the ladder picks winners and how it runs - `accepted` 2026-10-31 (user decisions)
- **Winner at S1, S2, S3 and S6:** the T08 rule at each step: pass the gates, highest mean accuracy, and a gap that is not real (T09) is a tie that goes to the cheapest run. If no option passes the gates, the step keeps the setting it started from. Full S0 runs 5 and 7 pass every gate, and each step's options include the setting it started from at S2, S3 and S6, and at S1 the 1,024-token run, so a valid winner normally exists.
- **S4 and S5:** T49, and the kept option must also pass the gates, since a run failing one can never be best (T08). Claude's reading, not a separate user decision.
- **S6:** the user's at most 4 versions, plus the prompt already in use, whose run exists from S5 and costs nothing. Skipping S6 (no version chosen) moves on to S7.
- **S7:** reported only. The stronger model is never kept, so the final configuration is S6's.
- **Running:** one step per click: the page shows the step's estimate, then runs it. Nothing else is needed to stop at S4 (cost shown first, T49) or S6 (prompts written first).
- **State:** none of its own. `rag/ladder.walk` replays the steps over the stored runs, which are permanent (D21), so a stored run is reused, runs 5 and 7 count as S0, and a restart loses only the unfinished work.
- **Alternatives:** highest accuracy alone (can pay more for a gap that is only noise); keep the old value unless the gain is real (strict, but would not adopt a cheaper equal value); one click with pauses (less clicking, less seen before spending, more code).
- **Built 2026-10-31 (custom choices):** one job per step (`jobs.submit_step`, `kind = ladder_step`), running the step's missing configurations in order; `jobs.run_id` holds its current run, so startup recovery closes it as for an evaluation (D07). Before each run it builds what is missing: chunk set, paid enrichment, index. A second click while a step of that stack waits or runs is refused, since it would pay twice. After a failure, finished runs stay and a new click pays only for the rest. S6's choice is stored once per stack (`ladder_prompts`, locked like runs), because changing it later would rewrite the ladder's past; it is saved only after passing every check, so a step refused by the budget can be chosen again. A partial unique index stops two clicks at the same moment.
- **Routes (custom choices):** `POST /api/story` starts one step on one stack, so a click on both stacks is two requests, each checked against the budget by itself; the running job's cap still stops a combined overrun (T44). `GET /api/story/{stack}` works out the state from stored runs, and may build a free chunk set to estimate a step. A click arriving while a step runs gets 409, also when it lost the race at the database, and a request with no valid next step gets 422.
- **Held-out confirmation (custom choices within T18):** one click per stack, only once its ladder is finished, running S0 and the final configuration, or S0 alone if the ladder kept its settings. It uses the step job, so one lock covers both. A configuration is confirmed once: the oldest matching run counts and a repeat is refused, so held-out questions cannot be re-rolled until a number looks better. A held-out run started from Evaluate with the same settings counts as that run. The result quoted is the paired interval (T09) of the final configuration against S0, for accuracy and MRR, and it is reported even when no gain is real. **Limit:** Evaluate (`POST /api/runs`) can still start a held-out run at any time, even before the ladder is finished. Such a run cannot change a ladder decision, since the ladder reads dev runs only, but it lets a person see held-out scores early, and nothing stops that; the discipline is the user's. The first matching run stays the one reported.
- **Story page (custom choices):** no router yet, since there is one page; the page's logic is in plain TypeScript, tested with Node's built-in test runner (`npm test`), so no test library was added. Components have no automated tests; they were checked by building and by looking at the page. A click on S4 or S6 asks to confirm, and S6 cannot run on an estimate that does not cover the typed prompts.
- **Estimate:** the step's runs (T43) plus enrichment still to pay. Stack A's search fees are counted (T53); its index builds are not (T44).
- **Limit:** a run is matched by model name, not by the provider's dated model version (`answer_slug`). If OpenRouter moved `gpt-4.1-nano` to a new version in the middle of the ladder, earlier runs would still count, and two steps would differ in a second variable. A changed judge version does stop the ladder (T08 filter). Runs 5 and 7 store `openai/gpt-4.1-nano-2025-04-14`.
- **Trade-off:** a tie can move to a cheaper value with slightly lower accuracy, so a stack's line can dip a little. About 7 clicks per stack.
- **Best practice:** choosing values on dev data and confirming on held-out is standard; the per-step rule is a custom choice, with no correction for many comparisons (T08).

### T47 - LLM enrichment of chunks (ladder step S4) - `accepted` 2026-10-30 (user decisions)
- **Decision:**
  - The LLM reads the chunk and its whole document, and writes a headline and a summary.
  - Headline and summary are used for search only. The answer model and the judge read the original chunk text.
  - Every chunk is enriched; there is no rule for "meaningful" chunks.
  - The model is `openai/gpt-4.1-mini` (`ENRICH_MODEL`), at temperature 0, through OpenRouter.
- **Why the whole document:** a chunk can lose its subject (a piece saying "the rollout took 6 weeks" may not name the client). Adding document context to each chunk before indexing is a published technique ("Contextual Retrieval", Anthropic, 2024). Our prompt and the headline-plus-summary format are a custom choice.
- **Why search only:** S4 then measures one thing, better search. An LLM mistake in a summary cannot reach an answer, or be counted as supported by the judge's faithfulness check.
- **Why every chunk:** "meaningful" had no definition, and a rule to define it would be invented and could hide a chunk a question needs. The cost saved would be pennies.
- **Why mini:** the output is made once and reused by every later run, so quality matters more than a small one-time cost.
- **Cost:** projected $0.04 to $0.27 per chunk set (48 to 469 chunks), assuming 150 tokens of instructions (the real text is 111, so this errs high) and 80 tokens of output per chunk (a guess), at the live prices of $0.40 / $1.60 per million tokens. Not measured yet. The plan's "about $1" was a first guess.
- **Budget (built 2026-10-30):** enrichment counts toward `BUDGET_USD`, as plan.md 1.4 budgets it, with one `spend` row per call and no run id (T44). The estimate uses each chunk's real input tokens and the assumed output, for chunks not paid for yet (a custom formula, like T43). A build estimated over what is left is refused before any paid call, and each next chunk is sent only if its estimate fits. A chunk that costs more than estimated can pass the cap by that difference, a fraction of a cent. `scripts/enrich.py`, run by the user, does the build and the indexing.
- **Alternatives:** the chunk alone (cheaper, but cannot add what the chunk leaves out); passing the summary to the answer model too (changes search and answers together); `gpt-4.1-nano` (about a quarter of the cost, weaker summaries).
- **Best practice:** yes for the technique. Keeping the original text for answers is our own choice, to keep one variable per ladder step.

### D31 - Dashboard redesign: guided pages and a shared style - `accepted` 2026-11-03 (user decisions)
- **Why:** the first real use (run 25) showed every page confusing: no page said what it was for or what to do first, Evaluate's report could not be found, Prompt did not lead to a test, Sweep looked like Evaluate with no difference explained (top of `fix.md`). Full plan: `ux-redesign.md` (private).
- **Decisions (user, all as recommended):**
  - Q1: our own shared Tailwind components (Card, Button, Table, Guide, Badge); no component library.
  - Q2: a Home page that explains where to start and which page does what.
  - Q3: Compare's verdict says "better" only when the paired bootstrap shows a real accuracy difference (the T08 rule already used by Story); otherwise "no real difference" and it points to the cheaper run. A custom wording of an existing rule, not a new statistic. Built 2026-11-03: the advice also applies T08's gates, as Story does: a run that fails a gate is never the one to keep, and when both fail, neither is advised (found by Antigravity reviewing increment 4).
  - Q4: failed logins rate-limited with fail2ban on Caddy's log (Step 10).
  - Q5: the whole site stays behind the password (D08), pages and API alike; no public read-only view. Guests at a live demo need the password too. **Revised 2026-11-05 by D32:** prod is public to read, the password guards every other request.
  - Q6: the redesign comes before Step 9's remaining checks, so the checks run on the final pages.
- **Revision 2026-11-04 (user decisions):** the settings panel picks a chunk set among those already built (labelled with the stacks that hold it), instead of free size, overlap and method; building is on the Build page only (the panel's build offer is removed). Ask, Evaluate and Sweep refuse to ask, estimate or start while a chosen stack lacks the chosen set (before, Sweep built a missing base set by itself). Every setting has an "i" button with what it is for; Ask always shows where the answers come from and filters its test questions. The site is dark only, on a black page (the light theme is removed).
- **Access guards (Step 10):** basic auth on every request (D08; **revised 2026-11-05 by D32:** on prod, every request that is not GET or HEAD); the app and Qdrant reachable only through Caddy, firewall open on 22, 80, 443 only; `BUDGET_USD`; a credit limit on the OpenRouter key and a monthly budget on the OpenAI project key; a post-deploy check that every page and API route answers 401 without the password (on prod: every request that is not GET or HEAD, D32).
- **Alternatives:** shadcn/ui (polished faster, adds Radix and several packages); public read-only results with a password for paid actions only (needs login code in the app and a guard on every new paid route).
- **Best practice:** guided pages and shared components are standard. Q5 keeps D08's limit: one shared password, no per-user identity; production would use single sign-on (OIDC).

### D32 - Secrets in Doppler; prod public to read, password to act - `accepted` 2026-11-05 (user decisions; revises D31 Q5 and the scope of D08)
- **Decision (user):** `OPENROUTER_API_KEY`, `OPENAI_API_KEY` and `BUDGET_USD` live in Doppler, one config per environment (staging, prod). The container gets them at start (`doppler run -- docker compose up -d`) with a read-only Doppler service token per environment on the VPS; no key file stays on the VPS. Prod is public to read: Caddy asks for the password (D08) on every request that is not GET or HEAD, so visitors see Story, Compare, reports and stored answers, and only the owner can start anything paid or write (runs, builds, sweeps, ladder steps, Ask, prompts, calibration, estimates). Staging keeps the password on every request.
- **Why:** the project can be shown publicly without anyone else spending the API credits. Keys no longer sit in a file on the VPS, and the keys and the spending cap change from one place. The rule goes by HTTP method, not by route, so a paid route added later is covered with no change, and the app needs no login code.
- **Guards:** checked 2026-11-05 in `main.py`: the 14 GET routes only read and the 12 POST routes pay, write or estimate. A new GET route must never pay or write. The post-deploy check of D31 becomes: on prod, pages and GET routes answer without the password and every other request answers 401; on staging every request answers 401. The owner may also remove the keys in Doppler while not using the paid pages.
- **Read-only notice (user decision 2026-11-05):** a `READ_ONLY` setting, kept in Doppler, read by the pages through a free GET route. When on, every button that starts something paid or writes is disabled and the page says it is a read-only demo. The owner turns it off in Doppler (and restarts the app) to work on prod; the password still guards every action, so a visitor in that window gets the browser's password prompt. The setting is a convenience for visitors, not a guard.
- **Admin sign-in (user decision 2026-11-08; the user chose the word admin):** turning `READ_ONLY` off meant a Doppler change and an app restart each time, impractical when the owner is asked to show the RAG live. In a read-only demo the notice now has an "Admin sign-in" button: it sends `POST /api/sign-in` (free, writes nothing), on which the server's Nginx asks for the password like on every request that is not GET or HEAD; when it answers 200, that browser turns every button on (until the page is reloaded; the browser keeps the password until it is closed, so signing in again does not ask). Visitors keep the read-only view. Security is unchanged: Nginx's password check is still the only guard, the flag decides only what the page shows. The route must stay a POST, or Nginx would let anyone through (tested: a GET is not answered by it). Not best practice: HTTP basic auth has no sign-out; a production site would use a session login.
- **No rate limit on reads (user decision 2026-11-05). Not best practice:** reads are free (local database only) and every action is behind the password; plain Caddy has no rate limit without a custom build with an extra module; failed logins are already limited by fail2ban (D31 Q4). Production alternative: a rate limit at the edge or a CDN in front of the site. Add one if the site is abused.
- **Alternatives:** the whole site behind the password (D31 Q5 before this revision: nothing to show publicly); a login page in the app (more code to write and secure); keys set only while used, with no password on writes (anyone visiting meanwhile could spend up to `BUDGET_USD`).
- **Best practice:** a secrets manager instead of key files is standard. A password by HTTP method is a simple custom guard; production would use single sign-on (OIDC) and per-route authorisation.

### D33 - Edge: Caddy on the host network, fail2ban limits, password in Doppler - `superseded` by D35 2026-11-07 (its fail2ban values and its HTTP/3 lesson carry over; `deploy/edge` removed)
- **Decision (user):** `deploy/edge` runs Caddy 2.11.9 with host networking. It proxies prod to `127.0.0.1:8000` and staging to `127.0.0.1:8001`; `www` redirects to the main domain. Caddy writes a JSON access log that fail2ban reads on the host: 10 refused logins (status 401) within 10 minutes ban the address for 1 hour. `DOMAIN`, `AUTH_USER` and `AUTH_HASH` (a bcrypt hash from `caddy hash-password`) live in Doppler's prod config; the edge starts with prod's service token.
- **Why:** with host networking the apps publish no public port, the log holds the visitor's real address (on a Docker network it would hold Docker's gateway, so fail2ban would ban everyone or no one), and fail2ban's host firewall rules apply to Caddy directly. One Doppler config keeps every secret in one place.
- **Checked 2026-11-06 (local Docker, the real Caddyfile, stand-in apps):** prod GET and HEAD open, every other method 401 without the right password; staging 401 on everything without it; the 401 carries `WWW-Authenticate: Basic`; `fail2ban-regex` matched exactly the 10 refused requests of 18 lines; a request whose path and User-Agent imitate a refused line is not matched (quotes are escaped in the log); the `Authorization` header is logged as `REDACTED`.
- **Review fixes (Antigravity, Gemini 3.8, both confirmed by Claude):** (1) fail2ban bans TCP only (`protocol = tcp` in `jail.conf`), while Caddy also served HTTP/3 over UDP 443, so a banned address could keep guessing; **user decision: HTTP/3 off** (`protocols h1 h2`), so nothing listens on UDP and the firewall needs TCP 80/443 only. Not chosen: banning every port, which would also cut the owner's SSH after 10 mistyped passwords. (2) Caddy's admin API on `localhost:2019` showed the password hash and accepted a new configuration from any program on the VPS: `admin off` (Caddy is restarted, never reloaded). Re-checked: admin refuses connections, no UDP listener, no `Alt-Svc` header, the password matrix and `fail2ban-regex` unchanged.
- **Custom choice:** the fail2ban values (10, 10 minutes, 1 hour) are not a standard. A mistyped password 10 times locks that address out for an hour.
- **Alternatives:** Caddy on a shared Docker network (bans then need rules in Docker's `DOCKER-USER` chain, and the real address needs care); a separate Doppler config for the edge (cleaner split, one more token).
- **Best practice:** a reverse proxy with automatic TLS and brute-force bans is common for one VPS. Production would use single sign-on (D08) and a managed edge with rate limits (D32).

### D34 - The release image is built by GitHub Actions and kept on GHCR, public - `accepted` 2026-11-07 (user decisions; moves part of Step 11 into Step 10)
- **Decision (user):** a workflow on every push to `main` runs the offline backend tests, the frontend lint and tests, then builds `backend/Dockerfile` with `APP_VERSION=<git-sha>` and pushes `ghcr.io/alex2t/rag-playground:<git-sha>`. The image is public. No `latest` tag: every deploy names a SHA. On the VPS, `deploy/deploy.sh <sha> <staging|prod>` pulls that image; the owner runs it. Deploying over SSH from GitHub, the evaluation gate and the approval before prod stay in Step 11.
- **Why:** staging and prod run the very same image from the first deploy, the VPS needs no build tools and spends no CPU on builds, and a rollback is a pull of an image that already exists. Building on the VPS now would be thrown away in Step 11.
- **Deploy script (increment 5b, 2026-11-07):** `deploy/deploy.sh <sha> <staging|prod>` pulls the image, starts the compose project with `--no-build --pull never` (so the VPS never builds), and waits up to 180 s for `/api/health` to answer `ok` with that SHA as its version; otherwise it prints the app's log and fails. Each environment's Doppler service token is scoped to `/srv/rag-playground/<env>` (`doppler configure set token --scope`, the pattern Doppler's docs recommend for servers), and the script runs `doppler run` from there; the edge starts from the prod directory. A failed deploy is not rolled back by itself: the owner runs the previous SHA. **Revised by D35:** prod only, `deploy/deploy.sh <git-sha>`, the prod token scoped to `/srv/rag-playground`.
- **Public image:** the repo is public and the image holds only its code, the fictional dataset and Stack B's public models; keys come from Doppler at start (D32). So the VPS pulls with no login and no token to store or renew.
- **Alternatives:** build on the VPS from a git checkout (no registry, but a build per environment and work replaced in Step 11); a private image (a read token on the VPS, hiding nothing that is not already public); the whole Step 11 pipeline now (needs the gate's funding decision and a GitHub SSH key on the VPS first).
- **Best practice:** build once in CI and deploy the same image by an immutable tag is standard. Not yet best practice until Step 11: deploys are started by hand.

### D35 - A shared VPS behind its Nginx, prod only - `accepted` 2026-11-07 (user decisions; supersedes D09, D13 and D33, revises D08, D32 and D34)
- **Decision (user):** the app runs on the owner's existing VPS, which already serves other sites. Its CloudPanel Nginx owns ports 80 and 443 and stays the front door: one CloudPanel "Reverse Proxy" site for `<domain>` sends traffic to the app on `127.0.0.1:8000`, and CloudPanel issues its certificate. The other sites, their proxies and their Docker networks are never touched. **No staging (user decision):** one owner and no planned features, so the project runs prod only (`rag-playground-prod`). `deploy/deploy.sh <git-sha>` deploys prod; the prod Doppler token is scoped to `/srv/rag-playground`.
- **Why:** a second VPS costs money every month. Nginx already holds ports 80 and 443 for the other sites, so the project's own edge Caddy (D33) cannot start there, and adding the site to another site's proxy would put that site at risk. Without staging the project needs at most 2.5 GB, not 5.5 GB.
- **Memory limits:** app 2 GB, Qdrant 512 MB (`mem_limit` in `deploy/docker-compose.yml`). Measured on the release image: about 190 MB idle, 65 MB for an empty Qdrant, 950 MB with nomic loaded and answering, up to 2 GB during a Stack B index build. The server had 5.7 GB available. If the app reaches its limit, Docker stops that container only (and restarts it); a job it was running fails.
- **Password (D32 kept):** in the site's Nginx config, `limit_except GET { auth_basic ...; }` at the top of CloudPanel's `location @reverse_proxy`, next to `proxy_pass` (`deploy/nginx/password-rule.conf`; revised 2026-11-08: in `location /` an authorised POST got 404, see `fix.md`): reading is public, every other method needs the password. The hash lives in `/etc/nginx/rag-playground.htpasswd` (`AUTH_USER:AUTH_HASH` from Doppler). **Cost 10, not 14:** Nginx checks bcrypt on every protected request with no cache; measured on Ubuntu 24.04, cost 14 took 0.77 s per request, cost 10 took 0.08 s. Cost 10 is OWASP's stated minimum for bcrypt. Ubuntu 24.04's crypt library accepts `$2a$`, `$2b$` and `$2y$` (tested).
- **fail2ban:** the server's fail2ban gets one jail (`deploy/fail2ban/rag-playground.local`) with the standard `nginx-http-auth` filter on the site's Nginx error log; D33's values (10 in 10 minutes, 1 hour). `backend = auto` is required: the server's default backend is systemd, which reads the journal and would ignore the log file. The site must not enable HTTP/3 (`listen 443 quic`): bans are TCP only (D33's lesson).
- **Checked 2026-11-07 (local Docker):** Nginx on Ubuntu 24.04 with the real rule: prod GET and HEAD 200 without a password, POST and DELETE 401, wrong password or unknown user 401, right password 200. fail2ban 1.1.1 with the server's defaults copied: the filter matched the 3 failure lines; 9 failures no ban, the 10th banned; with `backend = auto` removed the jail never banned. `deploy.sh`: refusals, deploy, limits applied (2 GiB and 512 MiB, port on 127.0.0.1 only), rollback kept the data volume.
- **Checked on the VPS 2026-11-08:** over HTTPS with the real certificate: GET 200; POST with no password or a wrong one 401; POST with the right password reaches the app (422 on an empty body, seen in the app log); `nginx -t` successful; the jail's filter matched a real mismatch line. The local check above had `proxy_pass` directly in `location /`, unlike CloudPanel's `try_files` to a named location, so it missed the 404 of the first placement.
- **Not best practice:** no staging, so a broken version reaches the public site until the owner rolls back (one command, about 10 s), and paid tests spend prod's budget. The project shares a server with other sites, so its load and theirs affect each other (bounded by the limits). Production would use a separate server and a staging environment. Step 11's evaluation gate cannot run on staging; it will run on the GitHub runner against the new image before the deploy (to be decided in Step 11).
- **Alternatives:** a second VPS with the D33 edge (no shared risk, monthly cost); the site added to another site's existing Caddy (risks that site); keeping staging (about 2 GB more memory, a second site, a second Doppler config).

### D36 - The evaluation gate and the deploy from GitHub - `accepted` 2026-11-08 (user decisions; completes D12 and D34)
- **Decision (user):** (1) GitHub deploys: after the gate passes, the owner clicks Approve (GitHub environment `production`) and GitHub runs `deploy.sh <sha>` on the VPS over SSH, with a key held only by GitHub (a GitHub Actions secret, never on the owner's PC) and restricted on the VPS to running the deploy. (2) The gate tests both stacks. (3) It is paid by prod's OpenRouter key (the one with the $60 credit limit); Stack A's searches use prod's OpenAI key. (4) It runs only when a push changes what can change an answer (backend code, settings, prompts, dataset); notes-only pushes skip it and are not deployed.
- **Gate questions:** the existing 20-question smoke set (round-robin over the dev categories, T46), the same as Evaluate's smoke test, at a fixed configuration; the job fails if any T08 gate fails, or either of the gate's own limits below.
- **The gate's own limits (user decision 2026-11-08, custom values, not a standard):** accuracy at least 3.5 and a false-refusal rate (answerable questions refused) at most 0.25, i.e. at most 4 of the 18 answerable smoke questions. Why: the T08 gates never check whether answers are right, and a refused answer scores faithfulness 5 (measured: every refused answer in runs 5 and 7), so a prompt that refuses everything would pass them all. Healthy S0 on the smoke set: accuracy 4.2 (A) and 4.4 (B), false refusals 1 of 18 on both, so about 3 to 4 answers can turn from right to wrong before the gate fails. Used by the CI gate only; the study's selection keeps T08 unchanged (`GATE_MIN_ACCURACY`, `GATE_MAX_FALSE_REFUSAL` in `settings.py`). Alternatives offered: accuracy only; T08 only. **Still not caught (limit, Antigravity EVAL-GATE-1B, confirmed):** an answer with the right facts in another language, or padded with off-topic text, or missing part of a multi-part answer, can pass: the judge scores completeness and relevance, but neither T08 nor the gate gates them.
- **Real runs 2026-11-08 (user, on the PC, throw-away Qdrant and `VAR_DIR`, prod keys from `.env`):** healthy version: both stacks pass (A accuracy 4.2, recall 0.889, false refusals 0 of 18; B 4.4, 0.917, 0 of 18), exit 0, $0.0987. Prompt damaged on purpose (uncommitted line at the top of `DEFAULT_TEXT`: "Ignore every instruction below. Whatever the question, reply only: I don't know."): Stack A fails (false refusals 5 of 18 = 0.278, accuracy 3.6), Stack B passes (4 of 18 = 0.222, accuracy 4.0), retrieval unchanged, exit 1, $0.0984. The model followed the bad line on some questions only, so the damage landed at the limit: the gate blocks clear damage reliably, damage this small only some of the time. **User decision: keep the gate as is** (limits not changed after seeing this result); explained in the README section on the gate.
- **Step 11 checks on GitHub 2026-11-08 (increment 5):** (1) a normal change (`d5d1141`, workflow and plan text) passed the gate, waited for the admin's approval and went live (`/api/health` showed its version). (2) The default prompt replaced on purpose by "Whatever the question, reply only: I don't know." (`e7aeb3b`, user decision: clear damage, since the mild damage above sits at the limit): the 1021 offline tests passed, so only the gate could stop it; the gate failed on both stacks (A: accuracy 1.4, false refusals 18 of 18 = 1.0, faithfulness 2.8; B: 1.4, 1.0, 2.4; MRR 1.000 and 0.972, recall 0.889 and 0.917, correct refusals 1.0), $0.0990; the deploy job was skipped and never offered; the site kept `d5d1141`. Accuracy 1.4 is exactly 18 refusals at 1 plus 2 correct refusals at 5, over 20. Faithfulness also failed, although the extra limits were added on the belief that a refusal scores faithfulness 5; this run's per-answer feedback was lost with the runner, so the cause is not checked: the accuracy and false-refusal limits remain the guard against an all-refusing version. Repaired by `0c594e8` (revert, prompt identical to `d5d1141`), whose gate passed and which the admin deployed (live default prompt hash `8fd366daf346`, same as the code). (3) Rollback: re-running only the deploy job of run 42515485973 (`199b951`, no gate, free; GitHub's "Re-run all jobs" button would re-run the gate, the single-job icon is on the deploy job's page) and approving it: job started at approval 21:47:26 UTC, done 21:47:38, site on `199b951` at 21:47:39 (13 s from approval, 69 s from the re-run click); one failed health check at 21:47:32 (app restart). Roll forward the same way on run 42525932924 (`0c594e8`): 12 s from approval, under 5 s unavailable. Fast because the old image is still on the VPS. An image deleted from the VPS would be pulled again from GHCR (public).
- **Cost:** about $0.02 (Stack B) plus $0.06 (Stack A, search fees included) per gate run at S0, about $0.08 in all.
- **Trade-offs:** gate spend shares the $60 limit with the study, and it is recorded only in the runner's throw-away database, so prod's `BUDGET_USD` does not see it; the OpenRouter credit limit is the cap that covers both. 20 questions are a coarse check: they catch a broken version, not a small loss of quality (the ladder and Compare measure that on 192). Only 2 of the 20 smoke questions are unanswerable, so one wrong answer to them gives a refusal rate of 0.50 and fails the 0.80 gate: the refusal gate is the most sensitive at this size. Checked 2026-11-08 on the stored full S0 runs (5 and 7) restricted to the 20 smoke questions: both pass every gate (Stack A accuracy 4.2, recall 0.889; Stack B 4.4, 0.917; refusals 2/2 on both). Not best practice: a separate key with its own limit would isolate gate spend (offered, declined).
- **Gate configuration (user decision 2026-11-08):** S0 (`S0` in `settings.py`) for now; when the ladder finishes, switching the gate to the winning configuration is proposed as a separate decision.
- **Keys for the gate (user decision 2026-11-08):** GitHub repository secrets `OPENROUTER_API_KEY` and `OPENAI_API_KEY`, so GitHub holds only those two (a Doppler token would read every prod secret). Trade-off: a changed key is changed in Doppler and in GitHub.
- **What triggers the gate (user decision 2026-11-08, increment 4):** a push that changes `backend/`, `frontend/` or the workflow; notes-only pushes skip it. **Only a commit whose gate ran and passed is deployed** (the deploy job needs the gate job), so a notes-only push made after a failed gate, whose image holds the failed code, is never deployed (Antigravity EVAL-GATE-3, confirmed).
- **The deploy (user decisions 2026-11-08):** a `deploy` job in the GitHub environment `production` (the owner's approval required, the SSH key an environment secret) connects as root with an ed25519 key held only by GitHub, forced in `/root/.ssh/authorized_keys` to `command="/usr/local/bin/rag-playground-deploy",restrict` (`deploy/ci-deploy.sh`, installed outside the checkout it updates). Its only input is the commit's full SHA, checked before use; it checks out that commit in `/srv/rag-playground` (detached) and runs that commit's `deploy.sh`. The VPS host key is pinned (`StrictHostKeyChecking=yes`). The key is generated on the VPS, its private half copied into GitHub, then deleted from the VPS. One deploy at a time (concurrency group). Rollback: re-run the deploy job of an earlier successful run. Alternative rejected: a separate `deployer` user (the docker group it needs is root-equivalent, and it needs its own Doppler token). Not best practice: root login with a password stays enabled on the server (server-wide setting, outside this project).


### D37 - Request logs: built-in logging, JSON lines on standard output - `accepted` 2026-11-09 (user decisions; Step 12 increment 1)
- **Decision (user):** Python's built-in `logging` with a small JSON formatter (`logs.py`), no new library; lines go to the container's standard output, read with `docker logs` (no log file on the VPS).
- **What is logged:** one line per request (`main.log_request`): time (UTC), level, logger, message (`request`), `request_id` (a new random id per request, also returned to the client in the `X-Request-ID` header), method, path, status, `latency_ms`. The query string is not logged. **Increment 2a:** one line per OpenRouter call that returns (`openrouter.paid`, logger `rag_playground.spend`, message `paid call`): model, prompt, completion and reasoning tokens, `cost_usd`; a line written during a request carries its `request_id` (the context variable `logs.request_id`), a background job's lines carry none (its threads do not inherit the request's context). Stack A's search fees are not calls and are not logged. uvicorn's own access line is turned off (`--no-access-log` in `backend/Dockerfile`, user decision): it repeated the request line in plain text and included the query string; uvicorn's start and error messages stay. **Increment 2b (user decisions 2026-11-09):** an unhandled request error logs `server error` (logger `rag_playground.requests`) with its trace in `exception`, then the request line with status 500, and goes on to Starlette's plain 500 (no `X-Request-ID` on it); a failed background job logs `job failed` (logger `rag_playground.jobs`) with its `job_id` and trace, a budget stop included. Every line at ERROR or above is also appended to `<var_dir>/errors.log` (`logs.ErrorFile`), in the app's data volume on the VPS, so it outlives the container; read with `docker exec rag-playground-prod-app-1 tail -n 20 /app/var/errors.log` (README). Handled errors (404, 409, 422, the 502s for an unreachable service) are request lines only. The plan's "errors listed on Ops" is dropped (user decision): errors are read on the VPS only. The user's idea of committing the file to GitHub was not taken: it needs a GitHub write key on the VPS (which can then change the deployed code) and would make error traces public. Limits: the file is not rotated (few errors expected: the site serves a study and a small number of runs); there is no alert, someone has to look.
- **Alternatives offered:** `structlog` (a library for structured logs); a log file on the VPS (needs rotation and a mounted folder).
- **Trade-offs:** Docker keeps standard output in its default json-file log with no size limit unless one is set, so logs grow until the container is recreated (each deploy recreates it). The request id is made by the app, not taken from the incoming request, so a client cannot choose it. Best practice for a container (logs to standard output, the platform collects them); no log search or retention, which a log service would add.

### D38 - Nightly database copy on the VPS, beside Hostinger's weekly backup - `accepted` 2026-11-09 (user decisions; Step 12 increment 3)
- **Facts (Kodee, read-only, 2026-11-09):** Hostinger backs up the whole VPS weekly (last 2026-11-04, 2 kept), a point-in-time disk backup that includes the Docker volumes; daily backups are off; a restore rolls back the whole VPS (every site on it), cannot be cancelled and removes snapshots; no single file can be taken out of a backup; a manual snapshot is one per VPS and lasts one day.
- **Decision (user):** keep Hostinger's weekly backup for losing the server, and add a nightly copy of `rag_playground.db` at 03:00 server time, the last 7 kept, in the app's data volume (`/app/var/backups/`, so the weekly backup holds them too). `chunk_sets/` (never changed once written) and `errors.log` are not copied.
- **How:** `python -m rag_playground.backup` (`backup.py`) inside the app container, started by `/etc/cron.d/rag-playground-backup` (`deploy/cron/`) as root with `docker exec`. SQLite's backup API copies a consistent state while the app runs (writes still in the WAL file included); the copy is written under a temporary name, switched to journal mode DELETE (one self-contained file; the app turns WAL back on when it opens it), checked with `PRAGMA integrity_check`, then renamed `rag_playground-<UTC date>.db`. A second run the same day replaces that day's copy. A missing database is an error (it is not created empty). Logged as JSON on standard output (cron appends it to `/var/log/rag-playground-backup.log`); a failure also goes to `errors.log` and exits non-zero.
- **Alternatives offered:** Hostinger's weekly backup alone (restore = whole VPS, up to 7 days lost); Hostinger's daily option (still a whole-VPS restore, price not found).
- **Trade-offs:** the copies sit on the same disk as the database, so a lost disk is covered only by the weekly backup (up to 7 days lost). Nothing alerts on a failed night: the log and `errors.log` must be read. About 22 MB per copy, about 150 MB for 7. The integrity-check failure path is not tested (a corrupt copy could not be produced without faking SQLite). Best practice would add an off-site copy; not done (it needs a storage account and its credentials on the VPS).
- **Review (Antigravity EVAL-BACKUP-3, 2026-11-09): fit to commit, 0 findings; two points of its checks confirmed.** (1) A copy that fails halfway leaves `rag_playground-<date>.partial` (about 22 MB); a retry the same day replaces it, but pruning never removes one from an earlier day: accepted limit (failures expected to be rare), delete by hand. (2) After an app crash, the latest writes may sit only in `rag_playground.db-wal`: the README's restore steps now copy the database with its `-wal` and `-shm` files to `before-restore/` before removing them.
