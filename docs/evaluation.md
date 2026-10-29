# How this project evaluates RAG

This document explains what the project measures and how:
- the data;
- the test questions;
- the experiment and the settings you can change;
- every metric, with a worked example;
- the rules that decide what counts as an improvement. It assumes no prior knowledge of the project.

**Status:** the dataset is built and checked (knowledge base and 240 tests). Chunking, indexing, scoring and the evaluation runs are still being built, so there are no results yet. Values marked *(proposed)* are confirmed when the step that uses them is built.

## In one paragraph

A **RAG** system (retrieval-augmented generation) answers a question in two stages. First it **retrieves** the most relevant passages from a document collection. Then an **LLM writes an answer** from those passages. Both stages can fail: retrieval can miss the right passage, and the LLM can answer wrongly or invent facts the passages do not contain. This project starts from the out-of-the-box defaults of a popular RAG framework, changes **one setting at a time** (chunk size, overlap, number of passages, enrichment, reranking, model), and measures whether each change really improves retrieval and answers. It runs the same experiment on two retrieval stacks, a hosted one and a self-hosted one, so that they can be compared fairly.

## Key terms

| Term | Meaning |
|---|---|
| Knowledge base (KB) | The collection of documents the RAG system searches. |
| Chunk | A piece of a document (for example, 400 tokens). Documents are split into chunks, and the system retrieves chunks, not whole documents. |
| Top-K | The number of chunks retrieved for each question (for example, K = 5). |
| Gold document | A document that holds the answer to a test question. Each test lists its gold documents. |
| Reference answer | The correct answer, written and verified when the test set was built. |
| Stack | One retrieval system: **Stack A** is OpenAI Vector Store (hosted); **Stack B** is Qdrant with the open-source `nomic-embed-text-v1.5` embedding model (self-hosted). |
| Judge | A separate LLM that grades each answer on a 1-5 scale. |
| Dev / held-out | The tests are split in two. **Dev** tests are used to choose settings. **Held-out** tests are never used for choosing; they only confirm the final result. |

## 1. The data: what the knowledge base contains

The knowledge base is the internal documentation of **Larkspur Cloud Partners**, a fictional Salesforce consulting firm with offices in Austin, Dublin and Toronto. It is 48 markdown documents, about 24,000 words in total, in five folders:

| Folder | Documents | What each document holds |
|---|---|---|
| `company/` | 3 | **Overview:** mission, offices, services offered. **History:** the firm's milestones by year (offices opened, services launched). **Employee handbook:** six policies (expenses, travel, remote work, certification bonus, on-call, data security), each with numbered rules such as limits, deadlines and amounts. |
| `employees/` | 3 | One **staff directory per office**, 20 employees in total. For each person: job title, start date, manager, Salesforce certifications, skills, a short bio and notable facts. |
| `services/` | 10 | One per **service the firm sells** (for example, Service Cloud Rollout): Salesforce product, pricing model, price, typical duration, launch year, service lead, deliverables, what is included and excluded, and client prerequisites. |
| `clients/` | 18 | One per **client account**: industry, country, client since, annual contract value, account lead, facts about the client, client-side stakeholders, and 3-5 **projects** (71 in total). Each project has the service used, start and end dates, team, summary, objectives and results such as "migrated 138 knowledge articles". |
| `deployment-runbooks/` | 14 | One per **deployment procedure** (for example, Production Deployment Rollback): owner, last review date, hands-on time and monitoring window, purpose, prerequisites, step-by-step procedure with a check for each step, rollback steps, and known issues with their fixes, including exact error messages and commands. |

Documents range from about 100 words (company overview) to about 1,100 words (employee handbook). The documents link to each other by name. A client document names its account lead, whose details are in a staff directory. A project names its service, whose price and limits are in a service document. Some questions therefore need two documents.

An excerpt from `clients/kerrawell-community-trust.md`:

```
| Client since | 2022 |
| Annual contract value (USD) | 74,800 |
| Account lead | Everett Nakamura-Boyle |
...
### Kerrawell Donor Journeys
- **Service:** Marketing Cloud Journey Setup
- **Start date:** 2022-10-03
- **End date:** 2022-11-28
- **Team:** Matthias Eklund, Aoife Brannigan
```

**Why synthetic data?** With invented data, every fact is known, so every answer can be checked exactly, and no model can answer from what it memorised during training. The data was built in three stages:
1. A single fact model (`world.json`) was generated and checked for contradictions, by code and by an independent model.
2. Each document was written from its own facts only. Each fact is stated in exactly one document, so a question's gold documents are unambiguous.
3. Every document was checked against its facts: no fact added, changed or missing.

## 2. The tests

240 questions in `backend/data/synthetic/tests.jsonl`. Each test has:
- `question`;
- `reference_answer`;
- `category`;
- `source_docs`: the gold documents;
- `keywords`: values copied from the gold documents, used only for the secondary keyword check below;
- `split`: `dev` or `heldout`.

| Category | Tests | Tests the ability to... | Example |
|---|---|---|---|
| `direct_fact` | 38 | find one stated fact | "Which API is used for the full Account load in the Bulk Data Migration with Data Loader runbook?" (Bulk API 2.0) |
| `numerical` | 38 | find an exact number | "What is the typical duration of Revenue Cloud Quote-to-Cash?" (16 weeks) |
| `temporal` | 35 | handle dates, order of events and elapsed time | "On what date did Julien Archambault start at the Toronto office?" (2024-06-03) |
| `exact_term` | 37 | return an exact name, command or error message | "Which command is used to log in again after the 'expired access/refresh token' error?" (`sf org login jwt` or web) |
| `multi_doc` | 30 | combine a value from each of two documents | "How many more knowledge articles could the Kestrelmoor Complaint Handling Rollout have migrated before reaching the article cap of the Service Cloud Rollout service?" (138 from the client document, 150 from the service document: 12 more) |
| `comparative` | 37 | compare two entities | "Which needs more hands-on time, the Change Set Deployment to Production or the Salesforce CLI Metadata Deployment from Source Control?" (120 vs 85 minutes) |
| `unanswerable` | 25 | refuse when the answer is not in the KB | "How many people work in the Mumbai office?" (there is no Mumbai office) |

- **Split:** 192 dev tests (20 unanswerable) and 48 held-out tests (5 unanswerable), stratified by category with a fixed seed (42), so every category has the same share in both splits.
- **How the tests were checked:**
  - An independent model read the whole knowledge base and confirmed each test. Each answerable test must have exactly one correct answer, that answer must be complete, and its gold documents must be exactly the documents that hold it. Each unanswerable test must truly have no answer.
  - Code checks confirmed the gold documents exist and that keywords appear in them. They also reject any question whose answer depends on a counting convention (for example, years between "client since 2015" and an exact date).
  - A second model (Gemini) reviewed the test set over four rounds, and every finding was fixed or recorded as a limitation.
  - A selection rule ensures no fact is tested twice, so dev and held-out never test the same fact.

## 3. The experiment

Every question goes through the same pipeline:

```
question -> retrieve the top-K chunks -> (optional) rerank -> answer LLM writes the answer -> judge grades it
```

**Two stacks, identical inputs.** Both stacks index exactly the same chunks. These are made once by LlamaIndex's default splitter, which cuts at paragraph and sentence boundaries where it can. Prompt, answer model, K and test questions are also the same. The only difference is the retrieval engine. Stack A uploads each chunk as its own file, so OpenAI does not re-split it.

**The baseline and the improvement ladder.** Each step changes one setting compared with the step before, on each stack:

| Step | What changes | Setting |
|---|---|---|
| S0 | Baseline | LlamaIndex out of the box: its default splitter (`SentenceSplitter`) with 1,024-token chunks and a 200-token overlap, top-2. No reranking, `gpt-4.1-nano` (these two are our choice, not LlamaIndex defaults). |
| S1 | Chunk size | The best size from a sweep of 100, 200, 400, 800, 1,024 and 1,600 tokens |
| S2 | Overlap | The best of 0%, about 20% (the baseline's share) and 25% of the chunk size |
| S3 | Top-K | The best of 2, 4, 6 and 8 chunks |
| S4 | Chunk enrichment | An LLM adds a headline and a summary to each chunk |
| S5 | Reranking | Retrieve 20 chunks, an LLM reorders them, keep the top K (S3's value) |
| S6 | System prompt | The best of at most 4 prompt versions, written before the step runs and compared on dev questions only |
| S7 | Answer model | A stronger model, shown as a cost trade-off rather than a RAG technique |

The baseline is the framework's documented defaults, not a deliberately weak setup. A weak baseline would inflate every gain.

**Beyond the ladder: every setting on the dashboard.** The dashboard lets anyone run a configuration of their choice, and a sweep varies one setting over a list of values:

| Setting | Range | Notes |
|---|---|---|
| Stack | A, B or both | With both, the same settings run on each stack and the results are shown side by side. |
| Chunk size | 64-2,048 tokens | A chunk set that does not exist yet is built and indexed on both stacks after a cost estimate and a confirmation. |
| Overlap | 0-50% of the chunk size | |
| Top-K | 1-8 | The knowledge base is small (48 documents of about 730 tokens), so more than 8 chunks would hand the model a large share of it. |
| Chunking method | fixed or LLM-enriched | |
| Hybrid search | off / on | Combines keyword matching (BM25) with vector similarity, merged by reciprocal rank fusion. It helps with exact strings such as commands and error messages. On Stack B it uses Qdrant's sparse vectors. On Stack A it uses OpenAI's own hybrid mode, with a semantic weight and a keyword weight. |
| Reranking | off / on | |
| OpenAI ranking (Stack A only) | ranker `none` or `auto`; hybrid weights; score threshold | OpenAI's `auto` ranker is an undocumented ranking step with no Stack B equivalent; results that use it are labelled. |
| Answer model | the 3 catalogue models | |
| System prompt | named versions | The prompt can be edited and saved as a new version. Saved versions never change, and every run records which version it used. |

Every setting is chosen explicitly; nothing falls back to a library or vendor default, and every run records all of them.

Results outside the ladder are exploratory. They use dev questions only, and the same statistical test decides whether a change is an improvement.

**Held fixed in every run:** temperature 0, the judge model (pinned to an exact version) and the test split. The system prompt is the default version from S0 to S5 and in the CI gate. Ladder step S6 compares at most 4 prompt versions, written before it runs, on dev questions only; from then on the chosen version is used, including in the held-out confirmation. Held-out questions never choose a prompt. One model, `gpt-6.1-sol`, does not accept a temperature setting, so its results are labelled "temperature not controlled".

**Reproducibility:** every run stores the git commit, the exact model versions, the system prompt version and its hash, a hash of the dataset, the chunk set and the search settings (including hybrid search).

**Embedding map (for the presentation).** A script draws a 2D picture of each stack's embedding space with t-SNE, a method that places points that are close in the original space close together on the page. It uses a 200-token chunk set:
- each chunk is a dot coloured by its folder (company, employees, services, clients, runbooks);
- the test questions are overlaid;
- one question can be highlighted with its gold chunks and the chunks actually retrieved for it.

This shows how a question can land next to the wrong document. Stack B's embeddings come from the local nomic model. OpenAI's vector store does not return its embeddings, so for Stack A the chunks are embedded again with an OpenAI embedding model (about $0.01). OpenAI does not document which model its vector store uses, so the map names the model actually used. **How to read it:** t-SNE keeps local neighbourhoods but not global distances, so the gaps between clusters and the cluster sizes mean nothing. The two maps are separate fits: compare their structure, not their positions. The map is an illustration; the conclusions come from the metrics.

## 4. The metrics, and how each is computed

Each question gets a score, and a run reports the mean over all its questions.

### 4.1 Retrieval: did the right documents come back? (computed by code, no LLM)

These metrics only use answerable questions. A retrieved chunk counts as relevant if it comes from a gold document. The **rank** of a gold document is the position of the first retrieved chunk that comes from it (1 = top).

| Metric | What it answers | How it is computed |
|---|---|---|
| **Hit@K** | Did at least one gold document appear? | 1 if any gold document is in the top K, otherwise 0. |
| **Recall@K** | Did all the needed documents appear? | Gold documents found in the top K / number of gold documents. Matters most for two-document questions. |
| **MRR** (mean reciprocal rank) | How high was the first right result? | 1 / the rank of the first chunk from any gold document: rank 1 scores 1.0, rank 2 scores 0.5, rank 4 scores 0.25, and 0 if none is in the top K. This is the standard definition (TREC question answering track, Voorhees 1999). Whether all gold documents were found is measured by Recall@K. |
| **nDCG@K** | Are the relevant chunks near the top? | Each relevant chunk at position *i* earns 1 / log2(*i* + 1), so lower positions earn less. The total is divided by the best possible total, so 1.0 means a perfect order (Järvelin and Kekäläinen, 2002). It measures how full the top K is of gold-document chunks, not coverage: a two-document question can reach 1.0 with every chunk from one document, which Recall@K catches. |
| Keyword recall *(secondary)* | Do the retrieved chunks contain the answer's source values? | Keywords found in the top K chunks / number of keywords. It is a weaker signal, because a chunk can contain "2015" without answering the question. It is kept only as a cross-check. |

**Worked example.** The question is the Kestrelmoor `multi_doc` example above. Its gold documents are the Kestrelmoor client document (G1) and the Service Cloud Rollout service document (G2). With K = 5, the retrieved chunks come from:

| Position | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Source | another service | G1 | G1 | G2 | another client |

- Hit@5 = **1** (a gold document was found).
- Recall@5 = 2 / 2 = **1.0** (both gold documents were found).
- MRR = 1/2 = **0.5** (the first gold chunk is at position 2).
- nDCG@5: the relevant chunks at positions 2, 3 and 4 earn 0.63 + 0.50 + 0.43 = 1.56. If the index held exactly these three relevant chunks, the best order would put them at positions 1-3 and earn 1 + 0.63 + 0.50 = 2.13. nDCG = 1.56 / 2.13 = **0.73**.

Here, retrieval found everything (recall 1.0), but the first useful chunk was only second (MRR 0.5) and the second document came fourth. With K = 2, as in the baseline, G2 would have been missed and the answer could not be computed.

### 4.2 Answers: is the answer right? (LLM judge, 1-5)

A judge model, `google/gemini-3.5-flash-lite`, grades every answer. It is from a different model family than the answer models (all OpenAI), which reduces the bias of a model favouring its own style. It runs at temperature 0 and returns a fixed structured format. It grades each answer in two separate requests: accuracy, completeness and relevance from the question, the reference answer and the answer; faithfulness from the question, the retrieved chunks and the answer, without the reference answer. In one combined request, the judge was seen giving full faithfulness to a correct answer that the retrieved chunks did not support, because it matched the reference answer.

| Metric | Compares | Question to the judge |
|---|---|---|
| **Accuracy** (primary) | answer vs reference answer | Is it factually correct? Any wrong fact scores 1. For an unanswerable question, a refusal scores 5 and an invented answer scores 1. |
| **Completeness** | answer vs reference answer | Does it cover everything in the reference answer? |
| **Relevance** | answer vs question | Does it answer only what was asked? |
| **Faithfulness** | answer vs retrieved chunks | Is every claim supported by the retrieved text? |

Faithfulness and accuracy catch different failures. Suppose retrieval missed the gold document, and the model answered "16 weeks" from its own general knowledge. Accuracy is 5 (the answer is correct), but faithfulness is 1 (nothing retrieved supports it). That answer was a lucky guess, and the system cannot be trusted to repeat it.

**Who checks the judge?** After the first real run, 30 answers, chosen to cover all score levels, are graded by a human who does not see the judge's scores. The judge is accepted if it agrees on pass/fail (accuracy ≥ 4) for at least 80% of them. Otherwise, the judge model is changed before any experiment runs.

### 4.3 Trust: does it refuse correctly?

The judge also flags whether the system refused to answer.
- **Correct refusal rate:** unanswerable questions refused / all unanswerable questions. Higher is better.
- **False refusal rate:** answerable questions refused / all answerable questions. Lower is better.

A system that refuses everything scores perfectly on the first and badly on the second, so both are reported.

### 4.4 Cost and speed
Latency per question (median and 95th percentile) and cost per question in USD.

## 5. What counts as success

1. **Gates.** A configuration is **eligible** only if it passes every gate *(proposed thresholds, our own choice, not an industry standard)*:
   - MRR ≥ 0.75;
   - Recall@K ≥ 0.80;
   - faithfulness ≥ 4.0;
   - correct refusal rate ≥ 0.80.
2. **Best configuration:** the eligible one with the highest mean accuracy. If the difference is not statistically significant, the cheaper one wins.
3. **Is an improvement real?** We use a paired bootstrap. Both configurations answer the same questions, so we take the per-question difference in score, resample those differences 1,000 times (seed 42), and compute a 95% confidence interval for the mean difference. The change counts as an improvement only if the whole interval is above zero. Changes that fail this test are reported under "what did not work".
4. **Final numbers** are confirmed on the 48 held-out tests, which played no part in choosing settings.
5. **In deployment**, the same evaluation is a **CI gate**: a release that falls below the gates is not promoted to production.

## 6. Fairness and known asymmetries

- **OpenAI's search defaults are not plain vector search.** Checked live: by default OpenAI fuses a semantic list with a keyword list, then applies an undocumented ranking step (`auto`). The ranker can be switched off (`none`), and the weights of the two lists can be set. Qdrant returns plain similarity scores. Every comparison of the two stacks states the OpenAI ranking settings, and results with the `auto` ranker say that Stack A's advantage may come from it.
- **OpenAI's "semantic only" mode is not plain vector similarity.** In a 12-question check, that mode (ranker off, keyword weight 0) found the right document for 7 of 12 questions. The same chunks embedded directly with OpenAI's `text-embedding-3-small` or `-large` and ranked by plain cosine similarity found all 12, as did Stack B's semantic search. What the mode computes is not documented, so its results are not presented as a measure of OpenAI's embeddings.
- Relevance is judged per document, not per passage: a chunk from the right document might be the wrong part of it. Faithfulness and accuracy catch this downstream.

## 7. Limitations

- **Synthetic data.** It is clean and consistent, so real documents (with contradictions, duplicates and messy formatting) are likely harder. It was checked by models, with human review on top.
- **Small samples.** 48 held-out tests give wide confidence intervals. `temporal` (35) and `multi_doc` (30) have fewer tests than the other categories, because no fact is tested twice and no document type may supply more than 40% of a category.
- **Overlap and repetition in the tests.**
  - Some dev and held-out tests share one of their two values (for example, two different comparisons that both involve the same service's duration).
  - 12 of the 30 `multi_doc` questions follow one template: "how long had X been at the firm when...".
- **Document length.** Most documents are shorter than the largest chunk sizes, so at those sizes a chunk is often a whole document.
- **Custom choices.** The gate thresholds, the dashboard setting ranges and the test-variety rules are our own choices, not standards.
- **Hybrid search is similar, not identical, on the two stacks.** Both fuse a semantic and a keyword list, but OpenAI's keyword scoring is not documented, while Stack B uses BM25.
- **Undocumented vendor behaviour.** OpenAI does not document its `auto` ranker or which embedding model its vector store uses.
- **Judge check.** The judge is checked against one human on 30 answers. That is a light check, not a full agreement study.
