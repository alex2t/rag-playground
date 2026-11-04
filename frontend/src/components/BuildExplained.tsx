import { hashOf } from '../route.ts'

const LINK = 'text-accent-text underline'

/** Fixed against LLM-enriched chunks, side by side. */
export function MethodsCompared() {
  return (
    <section aria-label="Fixed or LLM-enriched chunks" className="card space-y-3 p-5 text-sm">
      <h2 className="font-semibold">Fixed or LLM-enriched chunks?</h2>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-line p-3">
          <p className="font-medium">Fixed</p>
          <p className="mt-1 text-muted">LlamaIndex's sentence splitter cuts the 48 documents into pieces of the chosen size,
            at paragraph and sentence boundaries where it can. Each piece is stored exactly as it is. Free.</p>
        </div>
        <div className="rounded-md border border-line p-3">
          <p className="font-medium">LLM-enriched</p>
          <p className="mt-1 text-muted">The same pieces, then a model (gpt-4.1-mini) reads each one together with its whole
            document and writes a headline (at most 12 words naming the client, service, person or policy) and a summary (at
            most 2 sentences). The search uses the headline, the summary and the text; the answer model, the reranker and
            the judge read the original text only. Paid once per chunk set and shared by both stacks: Estimate shows the cost.</p>
        </div>
      </div>
      <p><strong>Why enrich?</strong> A piece cut from the middle of a document often does not name what it is about, for
        example "the cap is 150 articles" without saying which service. The headline puts that context back, so the search
        can match it to a question. Whether it really helps is measured, not assumed: it is ladder step S4 on Story.</p>
    </section>
  )
}

/** What a built chunk set is for, and where to use it next. */
export function AfterBuilding() {
  return (
    <section aria-label="After building" className="card space-y-2 p-5 text-sm">
      <h2 className="font-semibold">After building</h2>
      <ul className="list-disc space-y-1 pl-5">
        <li>The chunk set appears in the <strong>Chunks</strong> list of the Settings box on <a className={LINK} href={hashOf('Ask')}>Ask</a>,{' '}
          <a className={LINK} href={hashOf('Evaluate')}>Evaluate</a> and <a className={LINK} href={hashOf('Sweep')}>Sweep</a>, marked with the stacks that hold it.</li>
        <li>Try a few questions with it on <strong>Ask</strong>, then score it on the 192 dev questions on <strong>Evaluate</strong>.</li>
        <li>Test that run against your current base on <a className={LINK} href={hashOf('Compare')}>Compare</a>: is the gain real?</li>
        <li>A prompt is not part of a build: every saved prompt works with every chunk set. Pick one in the Settings box,
          or try several at once by varying "System prompt version" on Sweep. Write new ones on <a className={LINK} href={hashOf('Prompt')}>Prompt</a>.</li>
      </ul>
    </section>
  )
}
