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

## The two stacks

A stack is the part that stores the documents and finds the chunks for a question. Both stacks index the same chunks, and both answer with the same model and the same judge, so a difference in score comes from the search.

| | Stack A: OpenAI Vector Store | Stack B: Qdrant + nomic |
| --- | --- | --- |
| What it is | A managed service: OpenAI stores the chunks, embeds them and runs the search | Self-hosted: Qdrant is an open-source vector database, and `nomic-embed-text-v1.5` is an open-source embedding model running on our own machine |
| Default search | OpenAI's default, measured as hybrid search (meaning plus keywords) with its "auto" ranker | Plain vector search (meaning only); hybrid can be switched on |
| Advantages | Nothing to run or maintain; no local memory or processor needed; quick to start | Full control and visibility of the embedding model and search; data stays on our server; no per-search fee |
| Disadvantages | The embedding model cannot be chosen or seen, and the ranking is partly hidden; depends on one vendor; pays a fee per search; embedding is outside the recorded spend | We run and maintain it; embedding uses local processor and memory (about 2 GB at peak on this PC) and is slower on a small server |

Each stack keeps its own search settings and picks its own winners on the ladder. See D01, T12 and T40 in [decision.md](decision.md).

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

## The held-out questions: why the final numbers can be trusted

**What they are.** The 240 test questions are split once, with a fixed seed, into two groups. Every question type has the same share in both, including the questions the documents cannot answer. No fact is tested twice, so the two groups never ask the same thing.

| Group | Questions | Cannot be answered | Used for |
| --- | --- | --- | --- |
| Dev | 192 | 20 | Trying settings and choosing the best ones |
| Held-out | 48 | 5 | Confirming the final choice, and nothing else |

A **held-out run** is a run on those 48 questions.

**Why it matters.** The ladder tries many options and keeps whichever scores best on the dev questions. Some of that gain is real, and some is luck: an option can suit those 192 questions without being better in general. So a score on the questions used for choosing tends to flatter the winner. It is like marking students on the practice questions they studied.

The held-out questions are the exam. They played no part in any choice, so they measure how the system does on questions it was never tuned on. Without them, the study could only say "this scored well on the questions we tuned it on".

**How they are used.**
1. The ladder finishes on the dev questions, on each stack separately.
2. Each stack then runs two configurations on the held-out questions: the S0 baseline and its final choice.
3. A paired bootstrap on the same 48 questions shows whether the final choice is really better than the baseline.

**What the results are for.**
- **The quoted result:** these are the numbers reported for each stack, not the dev scores.
- **The real gain:** the final configuration against S0, on questions neither of them was tuned on.
- **A check for overfitting:** a held-out score well below the dev score means part of the dev gain was luck. Some drop is normal.
- **Never for tuning:** a weak result is reported as it is. Changing a setting and running again would turn the exam into more practice, and the number would stop meaning anything.

**How the app protects them.**
- The Ask page cannot pick a held-out question, and asking for one by its id gets the same answer as an id that does not exist.
- A held-out run shows overall scores only: no answers, no question table and no scores per category.
- Story confirms each configuration once and only after the ladder is finished.
- A prompt version can run on held-out questions only after a finished dev run, or if it is the default.

**Limits.**
- 48 questions give wide confidence intervals, so only a fairly large difference can be shown to be real.
- All 240 questions were written by an LLM from the same documents, so held-out questions show how the system handles new questions of the same kind, not every question a real user might ask.
- Some dev and held-out questions share one of their two values, for example two different comparisons that involve the same service's duration.
- The Evaluate page can still start a held-out run with any settings, so the rule against tuning on them depends partly on the person using it. Every run is stored and cannot be changed or deleted, so such runs stay visible.

**Status:** the ladder has reached S2, so no held-out run has been made yet. See T18 and T56 in [decision.md](decision.md) and [docs/evaluation.md](docs/evaluation.md).

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

## The evaluation gate: stopping a worse version before it goes live

**The problem it solves.** A RAG answer is made in two steps: a search finds the documents that match the question, then an answer model writes the reply from those documents, following a set of instructions (the prompt). Ordinary software tests check that the code runs. They cannot tell whether the answers are still right. A changed prompt, a search setting or a new model version can make the answers worse while every test still passes. The models are also not fully predictable, so a change can only be judged by measuring its answers.

**Why it is good practice.** Releasing software normally goes through automatic checks that block a broken version. For a RAG system, answer quality is part of what can break, so it needs its own automatic check: a fixed set of questions with known answers, run on every new version, with minimum scores the version must reach. Measuring a version this way before release, instead of trusting a few answers that look right, is the same idea as the rest of this study, applied to every release.

**How it works.**
1. When the backend code, settings, prompts or questions change, the new version answers 20 fixed test questions on both stacks, at the S0 baseline. The questions cover every question type, including 2 that the documents cannot answer.
2. A judge model grades each answer against its known reference answer, exactly as in the study.
3. The version must reach every minimum below, on both stacks. If it fails any one of them, it is not released.

| Check | Limit | Why |
| --- | --- | --- |
| Search finds the right document early (MRR) | at least 0.75 | the search still works |
| Search finds the right documents (recall) | at least 0.80 | the search still works |
| Answers invent nothing (faithfulness) | at least 4.0 out of 5 | no made-up facts |
| Unanswerable questions are refused | at least 80% | no guessing |
| Answers are right (accuracy) | at least 3.5 out of 5 | the answers are still correct |
| Answerable questions wrongly refused | at most 25% (4 of 18) | the system still answers |

The first four are the study's own minimums. The last two exist for the gate only: a version that answers "I don't know" to everything invents nothing and refuses the right questions, so it would pass the first four. All six values are this project's own choice, not a published standard.

**Tested on purpose.** A guard that has never blocked anything may not work, so it was tried both ways (2026-11-08, about $0.10 per run):

| | Healthy version | Prompt damaged on purpose |
| --- | --- | --- |
| What changed | nothing | one line added at the top of the prompt: "ignore every instruction below, reply only: I don't know" |
| Stack A: accuracy / wrongly refused | 4.2 / 0 of 18 | 3.6 / 5 of 18: **fails** |
| Stack B: accuracy / wrongly refused | 4.4 / 0 of 18 | 4.0 / 4 of 18: passes |
| Search scores | normal | unchanged (the prompt does not affect the search) |
| Result | **released** | **blocked** |

**What this shows.**
- The gate passes a healthy version and blocks a damaged one, as it should.
- The damaged prompt did not make the model refuse everything. It received contradictory instructions, one line saying "refuse" and the rest saying "answer from the documents", and it refused only some answerable questions. The damage landed right at the limit: 5 wrong refusals on one stack, 4 on the other. One question more or less is normal variation, so it says nothing about one stack being sturdier.
- So the gate reliably catches clear damage, but a version damaged this little is caught only some of the time.
- On GitHub, a version whose prompt was replaced by "reply only: I don't know" passed every ordinary test, then failed the gate on both stacks (accuracy 1.4, every answerable question refused). The deploy was never offered, and the live site kept the previous version.

**Limits.**
- 20 questions keep each check cheap, but they only catch clear damage. Small losses of quality are measured by the study itself, on 192 questions.
- With only 2 unanswerable questions, one wrong answer to them fails the refusal check.
- An answer with the right facts in another language, padded with unrelated text, or missing part of a multi-part answer can still pass: completeness and relevance are graded but not checked by the gate.
- The gate tests the S0 baseline. Once the study picks its final configuration, switching the gate to it is a separate decision.

See D36 in [decision.md](decision.md).

## How a change reaches the live site

Every push to `main` starts [`.github/workflows/build.yml`](.github/workflows/build.yml) on GitHub. A change reaches the server only after the admin approves it:

1. **Tests:** the backend and frontend tests run. A failure stops everything.
2. **Image:** the app is built into one Docker image, named after the commit (`ghcr.io/alex2t/rag-playground:<commit>`).
3. **Gate:** if the push changed `backend/`, `frontend/` or the workflow, the [evaluation gate](#the-evaluation-gate-stopping-a-worse-version-before-it-goes-live) runs on that exact image. A push that changes only notes skips the gate, and then nothing is deployed: only a version whose gate ran and passed can go live.
4. **Approval:** the deploy job waits in the GitHub environment `production` until the admin clicks **Approve and deploy**.
5. **Deploy:** GitHub connects to the server over SSH with a key that can run one script only, [`deploy/ci-deploy.sh`](deploy/ci-deploy.sh). The script accepts nothing but a commit id, checks out that commit and runs [`deploy/deploy.sh`](deploy/deploy.sh), which starts the new image with [`deploy/docker-compose.yml`](deploy/docker-compose.yml) and waits until the app reports that version as healthy.

**Rollback:** re-run the deploy job of an earlier run on GitHub. It puts that run's version back, without running the gate again.

See D36 in [decision.md](decision.md).

## Limitation: one dataset

The app runs on the one dataset in this repository and has no data import. Using other documents is a developer job: they must be Markdown, scoring needs new prepared questions and reference answers, and the judge must be calibrated again. Chunk sets and indexes are not yet tied to a dataset, so the old ones must be cleared first, or a run could search the old documents. See D28 in [decision.md](decision.md).

## Run locally

```
cd backend && uv run uvicorn rag_playground.main:app --reload
cd frontend && npm run dev
```

If the dashboard says "Cannot reach OpenRouter's model list: ... CERTIFICATE_VERIFY_FAILED", the backend's HTTPS check failed. When an antivirus inspects HTTPS traffic, its own certificate must be trusted: set `SSL_CERT_FILE` to it. When the antivirus does not inspect that process, `SSL_CERT_FILE` must not be set, or the real certificate is refused with the same error. In Windows cmd, `set SSL_CERT_FILE=` clears it for that window only; a `set` lasts until the window is closed.

## Run in Docker

```
docker compose --env-file .env -f deploy/docker-compose.yml -p rag-playground-dev up -d --build
curl http://127.0.0.1:8000/api/health
```

The container reads its keys and settings only from the shell that runs compose: `--env-file .env` locally, `doppler run --` on the VPS (D32).

## Tests

```
cd backend && uv run pytest
```
