/** What each setting and question box is for, shown by its "i" button. */
export const HELP = {
  stack: 'Which search engine finds the chunks. Stack A: OpenAI\'s vector store, run by OpenAI (it charges $0.0025 per search). '
    + 'Stack B: nomic embeddings stored in Qdrant, run by this app (free). Both search the same chunks and the same answer '
    + 'model writes the answer; only the search differs. "Both side by side" asks each stack and shows the two answers next to each other.',
  chunks: 'Before any search, the documents are cut into pieces called chunks; a stack finds chunks, not whole documents. '
    + 'Each choice reads size / overlap, then the stacks that hold it. Size is the length of a chunk in tokens (a token is about three quarters of a word). Overlap is how many tokens '
    + 'neighbouring chunks repeat, so a fact cut at a border still appears whole in one of them. Fixed chunks are plain '
    + 'pieces of text; LLM-enriched chunks also get a headline and summary written by a model, used for search only. '
    + 'Only chunk sets already built are listed, with the stacks that hold them. Build new ones on the Build page.',
  topK: 'How many of the best chunks the answer model reads. More chunks give more chances that the answer is among them, '
    + 'but cost more and add unrelated text that can mislead the model. The documents are few (48), so at most 8.',
  ranker: 'How OpenAI orders its results. auto: OpenAI re-sorts them with a ranker it picks itself (its latest one). '
    + 'none: results stay in the order given by the two weights below.',
  threshold: 'From 0 to 1. Results scoring below this value are dropped, even if fewer than Top-K remain. 0 keeps every result.',
  semantic: 'Weight of the meaning-based search, which finds text with the same meaning as the question even in other words. '
    + 'It counts when the ranker is none.',
  keyword: 'Weight of the word-matching search, which finds the exact words of the question, such as names, codes or numbers. '
    + '0 turns it off. It counts when the ranker is none.',
  hybrid: 'Off: Stack B searches by meaning only (nomic embeddings). On: it also runs a word-matching search (BM25) and '
    + 'merges the two rankings (Reciprocal Rank Fusion). Word matching helps with exact names, codes and numbers.',
  rerank: 'The stack first fetches 20 candidate chunks. A model then reads them all together with the question and puts '
    + 'them in order of usefulness, and the best Top-K are kept. Why: search scores the question and each chunk apart, '
    + 'while a model reading both at once often judges better which chunk answers. It costs one more model call per question and takes longer.',
  answerModel: 'The model that writes the answer from the chunks it is given, called through OpenRouter. Larger models cost '
    + 'more per question. Temperature is set to 0 where the model accepts it, so answers vary as little as possible.',
  prompt: 'The instructions given to the answer model before the chunks and the question, for example to answer only from '
    + 'the chunks and to say so when they do not hold the answer. Write new versions on the Prompt page.',
  typed: 'Any question about the documents. It has no reference answer, so it gets no scores: you judge the answer yourself.',
  test: 'One of the 192 prepared dev questions, each with a reference answer. The answer is scored by the judge model '
    + '(accuracy, completeness, relevance, faithfulness, from 1 to 5), and the documents that hold the answer are highlighted. '
    + 'Type in the filter box to shorten the list.',
  questionSet: 'Smoke test: 20 dev questions, to check that a set-up works; it stays out of Compare, Story and the findings. '
    + 'Dev: the 192 questions used to choose settings. Held-out: 48 questions never used to choose anything, run only to '
    + 'confirm a final choice; their report shows overall scores only, so they cannot leak into tuning.',
  gates: 'A set-up is eligible as the best only if it passes every gate: MRR at least 0.75, Recall@K at least 0.80, '
    + 'faithfulness at least 4.0 and correct refusal rate at least 0.80. Among eligible set-ups, the highest accuracy wins. '
    + 'These thresholds are this project\'s own choice, not an industry standard. The colours are a guide of the same '
    + 'kind: green from 0.9 (or 4.5 out of 5), amber from 0.75 (or 4), red below.',
  sweepVariable: 'Sweep makes one run per value you pick, on the 192 dev questions. Each run is the set-up in the Settings '
    + 'box with only this setting replaced; the Settings box itself does not change. The base\'s own value is always one '
    + 'of the runs, since every other value is compared with it. Example: pick prompt versions default, v2 and v3 to see '
    + 'whether a new prompt helps on your current search set-up. Prompt versions must be saved on the Prompt page first.',
} as const

/** What each score of a run means and how it is computed (docs/evaluation.md section 4). */
export const METRIC_HELP: Record<string, string> = {
  mrr: 'Mean reciprocal rank: how high the first chunk from a document holding the answer came. Rank 1 scores 1, rank 2 '
    + 'scores 0.5, rank 4 scores 0.25, not found scores 0, averaged over the answerable questions. Computed by code against '
    + 'each question\'s known source documents, with no model involved. Gate: at least 0.75.',
  recall: 'Recall@K: the share of the documents holding the answer that appear among the top K chunks; 1 means all were '
    + 'found. It matters most for questions that need two documents. Computed by code, no model. Gate: at least 0.80.',
  accuracy: 'Is the answer factually correct compared with the reference answer? Graded 1 to 5 by the judge model, from '
    + 'another model family than the answer models. Any wrong fact scores 1; for an unanswerable question, refusing scores 5. '
    + 'The main score: an answer passes at 4 or more, and the best set-up is the eligible one with the highest accuracy.',
  faithfulness: 'Is every claim in the answer supported by the retrieved chunks? Graded 1 to 5 by the judge in a separate '
    + 'request that does not see the reference answer. A correct answer taken from the model\'s own knowledge scores low: '
    + 'it was a lucky guess the system cannot be trusted to repeat. Gate: at least 4.0.',
  ndcg: 'nDCG@K: how well the retrieved chunks are ordered. A chunk from a right document at position i earns '
    + '1 / log2(i + 1), and the total is divided by the best possible, so 1 is a perfect order. Computed by code.',
  hit: 'Hit@K: 1 if at least one chunk from a document holding the answer is among the top K, otherwise 0, averaged. '
    + 'Computed by code.',
  keyword_recall: 'The share of the answer\'s key values (names, numbers, commands copied from the right documents) found in '
    + 'the retrieved chunks. A weaker cross-check: a chunk can contain "2015" without answering the question.',
  completeness: 'Does the answer cover everything in the reference answer? Graded 1 to 5 by the judge.',
  relevance: 'Does the answer address only what was asked, without padding? Graded 1 to 5 by the judge.',
  correct_refusal_rate: 'The share of unanswerable questions (the answer is not in the documents) that the system refused '
    + 'instead of inventing an answer. Higher is better. Gate: at least 0.80.',
  false_refusal_rate: 'The share of answerable questions that the system refused. Lower is better. It is shown with the '
    + 'correct refusal rate, because a system that refuses everything would score perfectly on that one alone.',
  cost_per_question: 'What one question cost on average, in US dollars: the answer model, the reranker if on, the judge, '
    + 'and Stack A\'s search fee. Lower is better.',
  latency_s: 'The average time to search and answer one question, in seconds; grading by the judge is not counted. Lower is better.',
}

/** What the verdict tiles of Compare test. */
export function changeHelp(score: string): string {
  return `Is After's ${score} really different from Before's? Both runs answered the same questions, so the test looks at `
    + 'the difference question by question and resamples those differences 1,000 times (a paired bootstrap) to get a '
    + '95% interval for the true change. "After is better" or "After is worse" only when the whole interval is on one side '
    + 'of zero; otherwise the gap could come from chance and the verdict is "No real difference".'
}

/** What each question category tests (docs/evaluation.md section 2). */
export const CATEGORY_HELP: Record<string, string> = {
  direct_fact: 'Find one fact stated in one document. Example: which API is used for the full Account load in a data migration runbook.',
  numerical: 'Find an exact number, such as a price, a duration or a count. Example: the typical duration of a service (16 weeks).',
  temporal: 'Handle dates, the order of events and elapsed time. Example: the date an employee started at an office.',
  exact_term: 'Return an exact name, command or error message. Example: the command to log in again after an expired token error.',
  multi_doc: 'Combine one value from each of two documents. Example: an article count from a client document and the cap '
    + 'from a service document, to work out the difference. Retrieval must find both documents.',
  comparative: 'Compare two things, such as two services, runbooks or people. Example: which of two runbooks needs more hands-on time (120 vs 85 minutes).',
  unanswerable: 'The answer is not in the documents; the right response is to say so. Example: how many people work in an '
    + 'office that does not exist. Scored by refusing (5) or inventing (1).',
}
