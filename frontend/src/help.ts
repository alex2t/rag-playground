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
} as const
