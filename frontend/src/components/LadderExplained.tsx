const BEST = 'Best: the highest accuracy among options passing the gates; if a cheaper option is not really worse, the cheaper one.'
const REAL_GAIN = 'Kept only if accuracy or MRR really improves and every gate passes; otherwise the ladder goes on without it.'

const STEPS: [string, string, string, string][] = [
  ['S0', 'Baseline', '1,024-token chunks, overlap 200, top-K 2, no reranking, gpt-4.1-nano, default prompt; each stack uses its own default search.', 'The reference every later step builds on.'],
  ['S1', 'Chunk size', '100, 200, 400, 800, 1,024 and 1,600 tokens, the overlap kept at about 20% of the size.', BEST],
  ['S2', 'Overlap', '0%, about 20% and 25% of the chunk size S1 kept.', BEST],
  ['S3', 'Top-K', '2, 4, 6 and 8 chunks read by the answer model.', BEST],
  ['S4', 'Chunking method', 'LLM-enriched chunks (a model writes a headline and summary of each chunk, used for search only) against plain chunks.', REAL_GAIN],
  ['S5', 'Reranking', 'Reranking on (20 candidates reordered by a model, the best top-K kept) against off.', REAL_GAIN],
  ['S6', 'System prompt', 'default against at most 4 versions you saved on Prompt and tick in the stack\'s box.', BEST],
  ['S7', 'Answer model', 'A stronger model, gpt-6.1-sol, against the current one.', 'Reported only, never kept: a stronger model is a cost trade-off, not a RAG technique.'],
]

const POINTS: [string, string][] = [
  ['One setting per step', 'Each step changes one setting and the winner carries on to the next step, so every gain can be put down to the setting that made it.'],
  ['A fair starting point', 'S0 cuts and searches the documents with the documented defaults of a popular RAG framework (LlamaIndex), not a weak set-up chosen to make later gains look big.'],
  ['Rules fixed in advance', 'How each step picks its winner was decided before any result, and the ladder applies it by itself, so a result cannot be steered after seeing it.'],
  ['Search first, answer last', 'The search settings are tuned before the prompt, and the model comes last, since an answer can only be as good as the chunks it is given.'],
  ['Same ladder, two stacks', 'Both stacks climb the same steps, each keeping its own winners, so they can be compared step by step.'],
  ['Confirmed on unseen questions', 'Every choice is made on the 192 dev questions; the 48 held-out questions then confirm the starting and the final set-ups.'],
  ['What did not work is shown', 'A step whose option is not kept still appears on the chart and in the table, with its scores.'],
]

/** Why the ladder is a sound study and what each step changes: always shown, unlike the guide, which can be closed. */
export default function LadderExplained() {
  return (
    <section aria-label="Why the ladder is a sound study" className="card space-y-4 p-5 text-sm">
      <div className="space-y-3">
        <h2 className="font-semibold">Why the ladder is a sound study</h2>
        <p>Trying settings by hand and keeping whatever looks best tends to find gains that are only luck. The ladder answers
          one question at a time, in a fixed order, with the winner of each step chosen by a rule set before any run: it
          shows which RAG techniques really improve retrieval and answers, and by how much.</p>
        <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {POINTS.map(([title, text]) => (
            <li key={title} className="rounded-md border border-line p-3">
              <p className="font-medium">{title}</p>
              <p className="mt-1 text-muted">{text}</p>
            </li>
          ))}
        </ul>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <caption className="mb-2 text-left font-semibold">What each step changes</caption>
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr><th className="py-1 pr-3">Step</th><th className="pr-3">Setting</th><th className="pr-3">Options tried</th><th>How the winner is chosen</th></tr>
          </thead>
          <tbody>
            {STEPS.map(([step, setting, options, rule]) => (
              <tr key={step} className="border-t border-line align-top">
                <td className="py-1.5 pr-3 font-medium">{step}</td><td className="pr-3">{setting}</td>
                <td className="pr-3 text-muted">{options}</td><td className="text-muted">{rule}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted">Limits: settings are tuned one after another, so how two settings work together is not
        explored; the 48 held-out questions give wide intervals; and the gate thresholds are this project's own choice, not a standard.</p>
    </section>
  )
}
