# Dashboard user manual

How to use the RAG Playground dashboard: ask questions, run evaluations, compare set-ups and prepare the live demo.

> **Status (2026-11-03):** Every page is built.

## 1. What the app does

The app answers questions about the documents of an invented consulting firm (48 documents: clients, services, staff, runbooks, company history). It does this with **RAG** (retrieval-augmented generation): it first finds the passages of the documents that match the question, then asks a language model to answer from those passages only.

Two complete RAG systems, called **stacks**, run side by side:

| Stack | Stores and searches the passages with | Its search settings |
|---|---|---|
| **Stack A** | OpenAI's hosted vector store | OpenAI's own options: ranker, two hybrid weights, score threshold |
| **Stack B** | Qdrant, self-hosted, with the open nomic embedding model | Hybrid search on or off |

Each stack runs independently: you set each one's search settings yourself. The other settings (below) are the same kind on both.

**Read-only demo.** The public site can be set to read-only (the `READ_ONLY` setting). A notice at the top of every page says so, and every button that pays or saves is turned off: Ask, Estimate, Evaluate, Embed, Confirm, Save new version and the Story Run buttons. Every stored result, report, chart and answer can still be browsed. Sweep results are shown only after an estimate, so a read-only visitor does not see them.

## 2. Words used in the app

| Word | Meaning |
|---|---|
| **Chunk** | A passage cut from a document. The search returns chunks, not whole documents. |
| **Chunk size** | How long a chunk is, in tokens (a token is about three quarters of a word). |
| **Overlap** | How much each chunk repeats the end of the previous one, so a sentence cut in two is not lost. |
| **Top-K** | How many chunks are sent to the answer model for each question (1 to 8). |
| **Chunking method** | `fixed` (plain cuts) or `llm_enriched` (an LLM writes a headline and a summary for each chunk, used for search only; answers read the original text). |
| **Hybrid search** | Combines meaning-based search with keyword search. |
| **Reranking** | Retrieves 20 chunks, lets an LLM reorder them, and keeps the best K. |
| **Answer model** | The language model that writes the answer: `gpt-4.1-nano` (cheapest), `gpt-4.1-mini`, `gpt-6.1-sol` (strongest). |
| **System prompt** | The instructions given to the answer model. Saved as named versions that never change. |
| **Judge** | A separate model that grades each answer against the reference answer. |
| **Dev / held-out** | The 240 test questions are split into 192 **dev** questions (used to choose settings) and 48 **held-out** questions (used only to confirm the final choice). |
| **Run** | One evaluation: a set of questions answered and graded with one configuration. |
| **Ladder** | The fixed sequence of steps S0 to S7, each changing one setting. |

## 3. Before you start

- Open the app at `https://<domain>`. Reading is open to everyone; the browser asks for the user name and password the first time you start, save or change something.
- Every paid action shows its estimated cost first and waits for you to confirm. One question on **Ask** is the exception: it costs a fraction of a cent, so it runs at once and shows its cost with the answer.
- All spending counts against one budget (`BUDGET_USD`: $60). The **Ops** page shows what is left. A run that would go over the budget is refused, and a running one stops before it would pass it.
- Every page opens with a box that says what the page is for and lists its steps in order. Close it once you know them: this browser remembers.

## 4. The settings panel

The **Ask**, **Evaluate** and **Sweep** pages share one settings panel:

1. **Stack:** A, B, or both side by side.
2. **Chunks:** a chunk set already built, shown as size / overlap in tokens, grouped by chunking method, with the stacks that hold it. To get another one, use **Build a new chunk set**, which opens the Build page.
3. **Top-K** (1 to 8).
4. **Search settings of each selected stack:**
   - Stack A: ranker (`auto` = OpenAI's own re-ranking, `none` = off), the semantic and keyword weights, and the score threshold.
   - Stack B: hybrid search on or off.
5. **Reranking** on or off.
6. **Answer model.**
7. **System prompt version.**

The panel opens with the last values you used on this browser, or with the S0 baseline the first time.

If the chosen chunk set is not built on a chosen stack, the panel says so under the list, and the page will not ask or start a run until you pick another set or another stack. Each setting has an **i** button: click it for what the setting does and why you would change it.

## 5. The pages

### Home: where to begin
The app opens here. It says what the app does, shows the budget left and the latest finished run (with a link to its report), a recommended order (Build, Ask, Evaluate, Sweep, Compare, then repeat Sweep and Compare for each setting: chunk size, overlap, top-K, enrichment, reranking, prompt, and the answer model last), the rules behind it (tune the search before the answer, change one setting at a time and make each winner the new base), and a table of which page does what and what it costs.

### How an evaluation works
Building and evaluating are two separate actions:

1. **Build** prepares the chunks and stores them on a stack. It answers no questions and gives no scores.
2. A **run** evaluates what was built. For each test question, the stack searches, the answer model answers, and the judge grades the answer against that question's reference answer. The scores also check whether the search found the documents that hold the answer.

Both stacks are tested on the same 240 prepared questions, with the same reference answers, so their scores can be compared. A run uses one question set: **dev** (192), **held-out** (48), or the 20-question **smoke test**, never all 240 at once. The smoke test only checks that a configuration works, and it stays out of Compare, Story and the findings.

### Ask: try one question
Use it to see how one configuration answers.
1. Choose the settings in the panel.
2. Type any question, or pick one of the test questions.
3. Press **Ask**.

You see the answer, its settings, time and cost, the chunks it was given (document, rank and score), and for a test question also the reference answer, the documents that hold the answer (highlighted where they were retrieved) and the judge's scores. A question you type yourself has no reference answer, so it shows no scores.

A box at the top of the page, always shown, says where the answers come from: both stacks search the same chunks and the same model writes the answer; only the search engine differs (Stack A: OpenAI's vector store; Stack B: nomic embeddings in Qdrant, run by this app). Type in the filter box above the test questions to shorten the list.

### Evaluate: score one configuration
Use it to measure a configuration on many questions.

A box at the top, always shown, explains why the scores can be trusted: known answers, search and answer scored separately, a judge checked against a human, settings chosen on dev questions only, refusals counted, every run reproducible, and gates set in advance. It also states the limits. Every score, the gates line, the question set and each question category have an **i** button: click it for what it means and how it is computed.
1. Choose the settings and the question set: **dev** (192), **held-out** (48), or the 20-question **smoke test**.
2. Press **Estimate** to see the number of questions, the cost and the time.
3. Press **Evaluate** (it turns on only after Estimate). The new run opens at once under **All runs**, with a progress bar (for example "12 of 192 questions"); you can leave the page. Runs go one at a time: a second run waits as **queued** until the first finishes.

**All runs** lists every run, newest first: its stack, question set, main settings, status and date. Press **Open** on a row to show that run under the table; the newest run is shown when the page opens. The box at the top of the page repeats these steps; close it once you know them.

The result shows 4 headline tiles (MRR, Recall@K, Accuracy, Faithfulness), a **show all** switch for the other metrics, refusal rates, scores by question category, and a table of every question that opens it in **Ask**. Export it as CSV. A **held-out** run shows its overall scores only, with no category scores and no question table: those questions stay out of tuning.

Any saved prompt version can be used, yours or the default. For a **held-out** run, the version must first have finished a run on dev questions (the default always may): prompts are chosen on dev questions and only confirmed on held-out ones.

### Compare: is one configuration really better?
Choose the **Before** set-up one setting at a time, from stack down to prompt: each list offers only values a finished run has, and a list with one value fills itself in. When several runs share those settings, the oldest is used. Choose the **After** set-up the same way, from runs of the same question set (full dev or held-out, not a smoke test), or pick it from **Runs that differ in one setting only**, which fills it in. A table shows the settings that differ between them; when more than one differs, the page says it can still tell which set-up is better, but not which of those settings made the difference. **What this means**, at the top of the result, says in plain words whether After is really better or worse on accuracy, using the paired test Story uses (see section 7), and which set-up to keep; with no real difference, it points to the cheaper run. As on Story, a run that fails a gate is never the one to keep. Below it you see the metrics side by side, which questions After fixed or broke (each opens in **Ask** with After's settings), and cost against accuracy. An answer passes at an accuracy of 4 or more out of 5: a question is **fixed** when it failed in Before and passes in After, **broken** when it passed in Before and fails in After. Two held-out runs compare overall only, with no question list. The verdicts read **After is better**, **After is worse** or **No real difference**. The Accuracy and MRR verdicts and every row of **All scores** have an **i** button that explains them.

### Story: the ladder
Runs the fixed ladder one step per click, on each stack separately, and draws one line per stack across the steps. Each stack's button shows the step's estimated cost before you click, including Stack A's search fee; OpenAI's index building is not included. A step that pays for enrichment (S4) asks you to confirm. If a step fails, the finished runs are kept, and the next click pays only for the rest.

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

Each step keeps the winner of the step before. The ladder decides this by itself, using a rule fixed in advance: enrichment (S4) and reranking (S5) carry on to the later steps only if their gain is real. If not, the later steps run without them, and the step still appears on the chart. You can still choose either setting yourself on **Evaluate** and **Ask**. Choices are made on dev questions only; the **held-out** panel then confirms the baseline and the best configuration on the 48 held-out questions. The best eligible run is highlighted.

**Read the chart.** The bar on each point shows the range the true score is likely to fall in. A **+** or **-** above a point means a real rise or fall from the step before. No mark means the change is too small to be sure of. Two bars can overlap and the change can still be real, so go by the mark.

**Save a chart.** **Download PNG**, at the top of each chart, saves it as an image file, in the colours you see on the page.

**See the best configuration.** Once a step has finished, a highlighted box shows the best configuration so far, with its scores and cost. When the ladder is finished, the box shows the final choice.

**Download the results.** Under **Every option tried**, **Download CSV** saves every option as a spreadsheet file, one row per option.

**See what a run actually answered.** Open **Every option tried** and click **View answers** next to a run. You get all of that run's questions, with the worst-scored ones at the top. Click a question to see what the system answered, what the correct answer was, how the judge scored it and why, and which chunks of text the system read.

This doesn't work for held-out runs, because those questions are kept separate from tuning.

The held-out confirmation opens when a stack's ladder is finished, and each configuration is confirmed once. At S6, tick at most 4 of the prompt versions saved on **Prompt** (besides `default`, which the ladder already uses) and press **Estimate**, and press it again if you change them; ticking none skips S6. A box at the top of the page, always shown, explains why the ladder is a sound study and what each step changes, with the options it tries and how its winner is chosen. The choice is final for that stack.

### Prompt: edit the instructions
Write your own system prompts: start from the default or any saved version, edit it, and save it under a new name. A name cannot contain a comma, and the text must differ from every saved version. Save as many versions as you like; each can be picked in the settings panel on **Ask**, **Evaluate** and **Sweep**. A saved version never changes, and the page lists the runs that used each one.

Under the editor, **Test on Evaluate** opens Evaluate with the selected version chosen and the 20-question smoke test selected; you still press Estimate, then Evaluate. **Try on Ask** opens Ask with the version chosen. Both test the saved text, so save your edits first. Each run that used the version has an **Open** button that shows its report on Evaluate.

For the ladder's prompt step (S6), choose up to 4 of your versions before the step runs; the best one is kept for the rest of the ladder and for the demo.

### Build: prepare chunks
Choose the chunking method, chunk size, overlap and stacks, then press **Estimate**. It shows the chunk set, its number of chunks, the stacks that already have it, and the cost: only `llm_enriched` costs money, paid once for both stacks. Press **Embed** to build it on the stacks that do not have it yet. Each build is listed below: green once the chunks are stored, red with the reason if it failed. Stack B builds on this computer and needs Qdrant running; 84 chunks took about 80 seconds. Stack A uploads each chunk to OpenAI, whose storage fee is not counted in the budget. Each field has an **i** button. A box next to the form compares fixed and LLM-enriched chunks: an LLM-enriched chunk gets a headline and a summary written by a model, used for search only, to put back the context a piece cut from a document often lacks. A box below says what to do after building: the chunk set appears in the **Chunks** list on Ask, Evaluate and Sweep; any saved prompt works with any chunk set.

### Sweep: try several values of one setting
Use it to see how one setting changes the scores with everything else fixed, for example top-K = 2, 4, 6 and 8. Evaluate measures one set-up you choose; Story runs the study's fixed ladder, where a rule set in advance picks each step's winner; a sweep picks no winner. To decide between two set-ups, use **Compare**.

The settings panel is the base configuration. Pick the one setting to vary and its values: type numbers separated by commas, or tick values from a list. At most 6 values, the base configuration's own value included, since every other value is compared with it. With both stacks, only settings both share can be varied; a stack's own search settings are swept on that stack alone. Press **Estimate** to see each value's run or cost, then **Confirm**. Each value runs on the 192 dev questions; values with a run already are reused, not paid twice. The charts show each value's accuracy and MRR with their 95% interval, and + or − where a value is really better or worse than the base. Sweeps are exploratory: no winner is picked. Varying a setting never changes the settings panel: each run is the panel's set-up with only that setting replaced. To vary the system prompt, save the versions on **Prompt** first. Once a sweep has run, test its most promising value against your base on **Compare**; if the gain is real, choose that value in the panel, and it becomes your new base.

**Confirm** turns on only after **Estimate**, and stays off when every value already has a run. Each value's run number opens its report on **Evaluate**.

### Ops: health and spend
Spend so far against the budget, split into runs and the rest (Ask, enrichment); past the budget, it says by how much. The error rate is the share of background jobs (runs, ladder steps, builds, sweeps) finished in the last 7 days that failed through a fault; stops at the budget cap and jobs cut off by an app restart are counted apart. Answer time per stack: the median (p50) and the slowest 5% (p95) of the time to search and answer one question, over runs started in the last 7 days; grading and questions asked on **Ask** are not counted. Also the app version, whether Qdrant answers, and every failed job with its message. **Refresh** reloads the figures. Each figure has an **i** button that says what it counts and what it leaves out.

## 6. Common tasks

### Prepare a live demo
1. Run the ladder (**Story**) on both stacks, and confirm on held-out questions.
2. Note the best eligible configuration (highlighted), including its prompt version.
3. Load it in the settings panel and open **Ask**.
4. Let your guests type their own questions. Each costs about $0.0002 to $0.0003 with `gpt-4.1-nano`, more with a stronger model; Stack A adds $0.0025.

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
| One question, `gpt-4.1-nano`, K=2 (answer and grading) | $0.0012 on Stack B, $0.0037 on Stack A |
| A full dev run (192 questions), `gpt-4.1-nano`, K=2 | $0.23 on Stack B, $0.71 on Stack A |
| The same at K=8 (projected from token counts) | $0.55 on Stack B, $1.03 on Stack A |
| A full dev run with `gpt-6.1-sol` | $2.50 or more on Stack B, $2.98 or more on Stack A (not measured yet) |
| One question typed on **Ask** (no grading) | $0.0002 to $0.0003 with `gpt-4.1-nano`, plus $0.0025 on Stack A |
| Building an `llm_enriched` chunk set | $0.04 to $0.27, once per chunk set (projected, not measured yet) |

On Stack B, most of the cost of an evaluation is the judge. On Stack A, the largest part is OpenAI's search fee of $0.0025 per question, which counts against the budget.

## 9. If something goes wrong

| Message or symptom | What it means | What to do |
|---|---|---|
| "The run is estimated at ..., but only ... is left" | The run would pass the budget. | Choose fewer questions or a cheaper model, or raise `BUDGET_USD`. |
| A run ends **failed** with "Budget reached" | It stopped before a question that could pass the budget. Its finished questions are kept. | As above; start a new run. |
| A run ends **failed** with another error | A model or a stack did not respond. | Check **Ops**, then start a new run (a finished run is never re-run). |
| A run ends **failed** with "interrupted: the app restarted" | The app restarted while the run was queued or running. Its finished questions are kept. | Start a new run. |
| "Not found: ..." with a prompt name | No saved prompt version has that name. | Pick a saved version on **Prompt**. |
| "Not found: ... is not indexed on Stack ..." | The chunks for this configuration are not built on that stack. | Build them on **Build**, or pick a chunk set built on that stack. |
| "Held-out runs use the default prompt or a version evaluated on dev questions" | This prompt version has no finished dev run. | Evaluate it on dev questions first. |
