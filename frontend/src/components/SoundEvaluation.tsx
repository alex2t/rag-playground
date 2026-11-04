const POINTS: [string, string][] = [
  ['Known answers', 'The documents describe a fictional company written for this project, so every fact in them is known. Each of the 240 test questions has one checked correct answer and the list of documents that hold it. Since the company does not exist, no model can know the answers from its training: it has to find them in the documents.'],
  ['Search and answer measured apart', 'Retrieval (did the right documents come back?) is scored by code; the answer (is it right, is it supported?) by a judge model. A bad answer can be traced to the search or to the model.'],
  ['A checked judge', 'The judge comes from another model family than the answer models, grades faithfulness without seeing the reference answer, and agreed with a human on pass or fail for 24 of 30 answers (80%).'],
  ['Separate questions to choose and to confirm', 'The 240 questions are split in two. The 192 dev questions are used to compare set-ups and pick the best one. The 48 held-out questions are never used for that: they are run at the end, on the chosen set-up and on the starting set-up for comparison. If the score holds on questions it was never tuned on, the gain is real and not fitted to the dev questions, like practising on mock exams and being graded on a final exam you have not seen.'],
  ['Refusals count', 'Some questions have no answer in the documents. A good system says so instead of inventing one, and refusing answerable questions counts against it.'],
  ['Reproducible', 'Every run stores the code version, the exact model versions, the prompt, a fingerprint of the dataset, the chunk set and the search settings.'],
  ['Real differences only', 'Two runs always differ a little by chance: a few answers come out better or worse. Before calling one set-up better, Compare checks that the gap is larger than that chance variation (a paired bootstrap: the per-question differences are resampled 1,000 times). Every set-up must also reach the same minimum scores, the gates, so none is judged by a looser rule.'],
]

/** Why the scores on Evaluate can be trusted: always shown, unlike the guide, which can be closed. */
export default function SoundEvaluation() {
  return (
    <section aria-label="Why this is a sound RAG evaluation" className="card space-y-3 p-5 text-sm">
      <h2 className="font-semibold">Why this is a sound RAG evaluation</h2>
      <p>A RAG system can look right on the few questions you try by hand and still fail on many others. Evaluate runs one
        set-up over a fixed set of test questions whose correct answers are known, scores the search and the answer
        separately, and gives numbers that can be compared from one set-up to the next. That is how you learn whether a
        change (bigger chunks, reranking, another model) really helps, instead of trusting a few good-looking answers.
        It uses the same settings as <strong>Ask</strong>.</p>
      <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {POINTS.map(([title, text]) => (
          <li key={title} className="rounded-md border border-line p-3">
            <p className="font-medium">{title}</p>
            <p className="mt-1 text-muted">{text}</p>
          </li>
        ))}
      </ul>
      <p className="text-muted">Limits: the documents are synthetic and cleaner than real ones, the judge was checked by one person
        on 30 answers, and the gate thresholds are this project's own choice, not a standard.</p>
    </section>
  )
}
