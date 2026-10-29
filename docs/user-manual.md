# Dashboard user manual

How to use the RAG Playground dashboard: ask questions, run evaluations, compare set-ups and prepare the live demo.

> **Status (2026-10-29):** the dashboard is designed but not built yet (plan step 9). This manual follows the design in `plan.md` and will be updated when the pages exist. The evaluation engine behind it is built and tested.

## 1. What the app does

The app answers questions about the documents of an invented consulting firm (48 documents: clients, services, staff, runbooks, company history). It does this with **RAG** (retrieval-augmented generation): it first finds the passages of the documents that match the question, then asks a language model to answer from those passages only.

Two complete RAG systems, called **stacks**, run side by side:

| Stack | Stores and searches the passages with | Its search settings |
|---|---|---|
| **Stack A** | OpenAI's hosted vector store | OpenAI's own options: ranker, two hybrid weights, score threshold |
| **Stack B** | Qdrant, self-hosted, with the open nomic embedding model | Hybrid search on or off |

Each stack runs independently: you set each one's search settings yourself. The other settings (below) are the same kind on both.

## 2. Words used in the app

| Word | Meaning |
|---|---|
| **Chunk** | A passage cut from a document. The search returns chunks, not whole documents. |
| **Chunk size** | How long a chunk is, in tokens (a token is about three quarters of a word). |
| **Overlap** | How much each chunk repeats the end of the previous one, so a sentence cut in two is not lost. |
| **Top-K** | How many chunks are sent to the answer model for each question (1 to 8). |
| **Chunking method** | `fixed` (plain cuts) or `llm_enriched` (an LLM adds a headline and a summary to each chunk). |
| **Hybrid search** | Combines meaning-based search with keyword search. |
| **Reranking** | Retrieves 20 chunks, lets an LLM reorder them, and keeps the best K. |
| **Answer model** | The language model that writes the answer: `gpt-4.1-nano` (cheapest), `gpt-4.1-mini`, `gpt-6.1-sol` (strongest). |
| **System prompt** | The instructions given to the answer model. Saved as named versions that never change. |
| **Judge** | A separate model that grades each answer against the reference answer. |
| **Dev / held-out** | The 240 test questions are split into 192 **dev** questions (used to choose settings) and 48 **held-out** questions (used only to confirm the final choice). |
| **Run** | One evaluation: a set of questions answered and graded with one configuration. |
| **Ladder** | The fixed sequence of steps S0 to S7, each changing one setting. |

## 3. Before you start

- Open the app at `https://<domain>` (production) or `https://staging.<domain>` and sign in with the user name and password you were given.
- Every paid action shows its estimated cost first and waits for you to confirm.
- All spending counts against one budget per environment (`BUDGET_USD`: $60 in production, $5 in staging). The **Ops** page shows what is left. A run that would go over the budget is refused, and a running one stops before it would pass it.

## 4. The settings panel

The **Ask**, **Evaluate** and **Sweep** pages share one settings panel:

1. **Stack:** A, B, or both side by side.
2. **Chunk size** (64 to 2,048 tokens), **overlap** (0 to 50% of the chunk size) and **chunking method**.
3. **Top-K** (1 to 8).
4. **Search settings of each selected stack:**
   - Stack A: ranker (`auto` = OpenAI's own re-ranking, `none` = off), the semantic and keyword weights, and the score threshold.
   - Stack B: hybrid search on or off.
5. **Reranking** on or off.
6. **Answer model.**
7. **System prompt version.**

If the chunks for your chunk size and overlap do not exist yet, the panel shows how long building them takes and what it costs, and builds them only after you confirm.

## 5. The pages

### Ask: try one question
Use it to see how one configuration answers.
1. Choose the settings in the panel.
2. Type any question, or pick one of the test questions.
3. Press **Ask**.

You see the answer, the chunks it was given (document, rank and score), and for a test question also the reference answer, the documents that hold the answer (highlighted where they were retrieved) and the judge's scores. A question you type yourself has no reference answer, so it shows no scores.

### Evaluate: score one configuration
Use it to measure a configuration on many questions.
1. Choose the settings and the question set: **dev** (192), **held-out** (48), or the 20-question **smoke test**.
2. Press **Estimate** to see the number of questions, the cost and the time.
3. Press **Evaluate**. Progress updates while it runs; you can leave the page.

The result shows 4 headline tiles (MRR, Recall@K, Accuracy, Faithfulness), a **show all** switch for the other metrics, refusal rates, scores by question category, and a table of every question that opens it in **Ask**. Export it as CSV.

Any saved prompt version can be used, yours or the default. For a **held-out** run, the version must first have finished a run on dev questions (the default always may): prompts are chosen on dev questions and only confirmed on held-out ones.

### Compare: is one configuration really better?
Pick two finished runs. You see the metrics side by side, whether the difference is real (see section 7), which questions one run fixed or broke, and cost against accuracy.

### Story: the ladder
Runs the fixed ladder on one or both stacks and draws one line per stack across the steps:

| Step | What changes |
|---|---|
| S0 | Baseline: framework defaults (1,024-token chunks, 200-token overlap, K=2, no reranking, `gpt-4.1-nano`); each stack uses its own default search. The starting prompt is the default one, until S6 picks the best |
| S1 | Chunk size: the best of 100 to 1,600 tokens |
| S2 | Overlap: the best of 0%, about 20% and 25% |
| S3 | Top-K: the best of 2, 4, 6 and 8 |
| S4 | Chunking method: LLM-enriched |
| S5 | Reranking on |
| S6 | System prompt: the best of at most 4 versions, written before the step runs |
| S7 | A stronger answer model, shown as a cost trade-off |

Each step keeps the winner of the step before. Choices are made on dev questions only; the **held-out** panel then confirms the baseline and the best configuration on the 48 held-out questions. The best eligible run is highlighted.

### Prompt: edit the instructions
Write your own system prompts: start from the default or any saved version, edit it, and save it under a new name. Save as many versions as you like; each can be picked in the settings panel on **Ask**, **Evaluate** and **Sweep**. A saved version never changes, and the page lists the runs that used each one.

For the ladder's prompt step (S6), choose up to 4 of your versions before the step runs; the best one is kept for the rest of the ladder and for the demo.

### Build: prepare chunks
Choose the chunking method, chunk size, overlap and stacks, then press **Embed**. A green message confirms the chunks are stored on each stack; a red one says what failed.

### Sweep: try several values of one setting
Pick a base configuration, the setting to vary (for example chunk size, K, hybrid search or prompt version) and its values. Press **Estimate**, then **Confirm**. Combinations already run are reused, not paid twice.

### Ops: health and spend
Spend against the budget, error rate, slowest-answer time (p95) and the app version.

## 6. Common tasks

### Prepare a live demo
1. Run the ladder (**Story**) on both stacks, and confirm on held-out questions.
2. Note the best eligible configuration (highlighted), including its prompt version.
3. Load it in the settings panel and open **Ask**.
4. Let your guests type their own questions. Each costs about $0.0002 to $0.0003 with `gpt-4.1-nano`, more with a stronger model.

### Find out whether a setting helps
1. **Evaluate** the configuration without the change, on dev questions.
2. **Evaluate** it again with only that setting changed.
3. **Compare** the two runs, and trust the difference only if it is marked as real.

### Test a new system prompt
1. Save the new version on **Prompt**.
2. **Evaluate** it on dev questions, and **Compare** it with the same configuration using another version (for example your current best, or the default).
3. Only a version with a finished dev run can then be used on held-out questions.

## 7. Reading the results

- **Retrieval metrics** (did the search find the right documents?): **MRR** (how high the first right document ranks: 1.0 = always first), **Recall@K** (share of the right documents found in the top K), nDCG@K and Hit@K.
- **Answer metrics** (judge, 1 to 5): **Accuracy** (correct against the reference answer), Completeness, Relevance, **Faithfulness** (every claim is supported by the retrieved chunks).
- **Trust:** the correct refusal rate (questions with no answer in the documents that the model correctly declined) and the false refusal rate (answerable questions it wrongly declined).
- **Colours:** green, amber or red against fixed bands (for example MRR green from 0.90, judge scores green from 4.5).
- **Eligible ("best") runs** must pass all gates: MRR at least 0.75, Recall@K at least 0.80, faithfulness at least 4.0, correct refusal rate at least 0.80. Among them, the highest accuracy wins; if the gap is not real, the cheaper run wins.
- **Is a difference real?** The app runs a paired bootstrap (1,000 resamples of the per-question differences). If the 95% interval is above 0, the improvement is real; if it includes 0, it is not.
- **Labels:** results from `gpt-6.1-sol` say "temperature not controlled" (it does not accept a fixed temperature); Stack A results with ranker `auto` say "OpenAI ranker on" (Stack B has no equivalent step). A comparison always shows each stack's search settings.

## 8. Costs (from the first real run, 2026-10-29)

| What | About |
|---|---|
| One question, `gpt-4.1-nano`, K=2 (answer and grading) | $0.0012 per stack |
| A full dev run (192 questions), `gpt-4.1-nano`, K=2 | $0.23 per stack |
| The same at K=8 (projected from token counts) | $0.55 per stack |
| A full dev run with `gpt-6.1-sol` | $2.50 or more per stack (not measured yet) |
| One question typed on **Ask** (no grading) | $0.0002 to $0.0003 with `gpt-4.1-nano` |

Most of the cost of an evaluation is the judge. Stack A may add OpenAI's own search fees (being checked).

## 9. If something goes wrong

| Message or symptom | What it means | What to do |
|---|---|---|
| "The run is estimated at ..., but only ... is left" | The run would pass the budget. | Choose fewer questions or a cheaper model, or raise `BUDGET_USD`. |
| A run ends **failed** with "Budget reached" | It stopped before a question that could pass the budget. Its finished questions are kept. | As above; start a new run. |
| A run ends **failed** with another error | A model or a stack did not respond. | Check **Ops**, then start a new run (a finished run is never re-run). |
| "... is not indexed on Stack ..." | The chunks for this configuration are not built on that stack. | Build them on **Build**, or accept the offer in the settings panel. |
| "Held-out runs use the default prompt or a version evaluated on dev questions" | This prompt version has no finished dev run. | Evaluate it on dev questions first. |
