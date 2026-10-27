# Evaluation design

What the data is, which tests are run, how the RAG is evaluated, and what success looks like. Values marked *(proposed)* are confirmed when the step that uses them is built.

## The data
The knowledge base is the internal documentation of **Larkspur Cloud Partners**, a fictional Salesforce consulting firm: 48 markdown documents (company overview, history and handbook; 3 staff directories; 10 services; 18 clients with 71 projects; 14 deployment runbooks).

It is synthetic so that every fact is known and every answer can be checked. It was built from a single fact model (`world.json`). Code checks and an independent model audited the facts, and then each document was written from its own facts and checked against them.

## The tests
240 questions in `backend/data/synthetic/tests.jsonl`. Each has a reference answer, the gold documents that contain the answer, and 1-3 answer keywords. Keywords are values copied from the gold documents and are used only for keyword recall, a secondary retrieval check (are the answer's source values in the retrieved chunks?). Answers are graded against the reference answer, never against keywords, so a computed answer (such as a number of days) is not a keyword.

| Category | Tests | Tests the ability to... |
|---|---|---|
| `direct_fact` | 38 | find one stated fact |
| `numerical` | 38 | find an exact number |
| `temporal` | 35 | handle dates, order of events and elapsed time |
| `exact_term` | 37 | return an exact name, setting or error message |
| `multi_doc` | 30 | combine a value from each of two documents |
| `comparative` | 37 | compare two entities |
| `unanswerable` | 25 | refuse when the answer is not in the knowledge base |

- **192 dev** tests are used for all tuning. **48 held-out** tests (a fifth) are used only to confirm the final result. The split is stratified by category, with a fixed seed.
- Every test was confirmed by an independent model reading the whole knowledge base: answerable (or truly unanswerable), unambiguous, correct, complete, with exactly the right gold documents.

## How the RAG is evaluated
- **Two stacks** index the same chunks: OpenAI Vector Store (hosted) and Qdrant with `nomic-embed-text-v1.5` (self-hosted).
- **Baseline:** LlamaIndex defaults (1,024-token chunks, 20-token overlap, top-2, no reranking, `gpt-4.1-nano`).
- **Improvement ladder:** one variable changes per step: chunk size, overlap, top-K, LLM-enriched chunks, reranking, then a stronger model (shown as a cost trade-off). The same steps run on both stacks.
- **Fixed:** temperature 0, prompt, judge model, test split.

| Measure | What it shows |
|---|---|
| MRR, Recall@K, nDCG@K, Hit@K | Did retrieval return the gold documents, and how high? |
| Accuracy, completeness, relevance, faithfulness (LLM judge, 1-5) | Is the answer correct, complete, on topic, and supported by the retrieved text? |
| Correct / false refusal rate | Does it refuse what it cannot answer, and only that? |
| Latency, cost per question | What does it cost to run? |

The judge, `google/gemini-3.5-flash-lite` *(proposed)*, is checked against 30 human-graded answers.

## What success looks like
1. A configuration is **eligible** only if it passes every gate *(proposed, custom thresholds)*: MRR ≥ 0.75, Recall@K ≥ 0.80, faithfulness ≥ 4.0, correct refusal rate ≥ 0.80.
2. The **best** configuration is the eligible one with the highest accuracy. If the difference is not significant, the cheaper one wins.
3. A change counts as an **improvement** only if a paired bootstrap (1,000 resamples, 95% confidence interval) is above zero. Changes that do not pass are reported under "what did not work".
4. The final numbers are confirmed on the **48 held-out** tests.
5. In deployment, the same evaluation is a **CI gate**: a release that falls below the gates is not promoted to production.

## Limitations
The data is synthetic and was checked by models, with a human review on top. 48 held-out tests give wide confidence intervals. `temporal` and `multi_doc` have fewer tests (35 and 30) because no fact is tested twice and no document type may supply more than 40% of a category. Some dev and held-out tests share one of two values (for example, two different comparisons that both involve the same service's duration), and 12 of 30 `multi_doc` questions follow one template ("how long had X been at the firm when..."). Most documents are shorter than the largest chunk sizes. The gate thresholds and the test-variety rules are custom choices.
