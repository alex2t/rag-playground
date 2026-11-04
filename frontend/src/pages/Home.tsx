import { useEffect, useState } from 'react'
import { getOps } from '../api/client.ts'
import type { OpsSummary } from '../api/types.ts'
import { useRuns } from '../api/useRuns.ts'
import { questionsLine } from '../evaluate.ts'
import { latestFinished, NEEDS, PATH } from '../home.ts'
import { budgetLine, leftLine } from '../ops.ts'
import { hashOf, pageLink } from '../route.ts'

function Status() {
  const { runs } = useRuns()
  const [ops, setOps] = useState<OpsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getOps().then(setOps).catch((e: Error) => setError(e.message))
  }, [])

  const latest = runs ? latestFinished(runs) : null
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <section aria-label="Budget" className="min-w-0 card p-5">
        <h2 className="text-sm text-muted">Budget</h2>
        {ops && <p className="text-xl font-semibold">{budgetLine(ops)}</p>}
        {ops && <p className="text-sm">{leftLine(ops)}. <a className="text-accent-text underline" href={hashOf('Ops')}>Details on Ops</a></p>}
        {!ops && <p className={`text-sm ${error ? 'text-danger' : 'text-muted'}`}>{error ?? 'Loading...'}</p>}
      </section>
      <section aria-label="Latest result" className="min-w-0 card p-5">
        <h2 className="text-sm text-muted">Latest finished run</h2>
        {latest && <p className="text-xl font-semibold">Run {latest.id}, Stack {latest.stack}</p>}
        {latest && <p className="text-sm">{questionsLine(latest)}, {latest.created_at.slice(0, 10)}. <a className="text-accent-text underline" href={pageLink('Evaluate', { run: String(latest.id) })}>Open its report</a></p>}
        {runs && !latest && <p className="text-sm text-muted">No run has finished yet. Start one on <a className="underline" href={hashOf('Evaluate')}>Evaluate</a>.</p>}
        {!runs && <p className="text-sm text-muted">Loading...</p>}
      </section>
    </div>
  )
}

function Path() {
  return (
    <section aria-label="Recommended order" className="space-y-3">
      <h2 className="text-lg font-semibold">Recommended order</h2>
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PATH.map((step, index) => (
          <li key={step.title}>
            <a href={hashOf(step.page)} className="block h-full card p-5 hover:border-accent">
              <span className="text-xs font-semibold uppercase tracking-wide text-accent-text">Step {index + 1}</span>
              <span className="mt-1 block text-lg font-semibold">{step.title}</span>
              <span className="mt-1 block text-sm text-muted">{step.text}</span>
            </a>
          </li>
        ))}
      </ol>
      <div className="card space-y-2 p-5 text-sm">
        <p><strong>Search first, answer last.</strong> An answer can only be as good as the chunks it is given, so tune the
          search before the prompt. Test the answer model last: a stronger model usually helps but costs more per question,
          so it is a cost trade-off rather than a RAG technique.</p>
        <p><strong>One setting at a time.</strong> Change one thing per test, so you know what made the difference, and make
          each winner the new base before testing the next setting.</p>
        <p className="text-muted"><a className="underline" href={hashOf('Story')}>Story</a> runs this whole ladder for you, with
          rules fixed in advance, then confirms the final choice on the 48 held-out questions. Write prompt versions on{' '}
          <a className="underline" href={hashOf('Prompt')}>Prompt</a> before sweeping them; <a className="underline" href={hashOf('Ops')}>Ops</a> watches spend and failures.</p>
      </div>
    </section>
  )
}

function Needs() {
  return (
    <section aria-label="Which page do I need?" className="min-w-0 overflow-x-auto card p-5">
      <table className="w-full text-left text-sm">
        <caption className="mb-2 text-left text-lg font-semibold">Which page do I need?</caption>
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr><th className="py-1 pr-3">I want to</th><th className="pr-3">Page</th><th>Cost</th></tr>
        </thead>
        <tbody>
          {NEEDS.map((need) => (
            <tr key={need.page} className="border-t border-line">
              <td className="py-1.5 pr-3">{need.want}</td>
              <td className="pr-3"><a className="font-medium text-accent-text underline" href={hashOf(need.page)}>{need.page}</a></td>
              <td className="text-muted">{need.cost}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">Costs are typical, measured at the baseline set-up. Every paid page shows its exact estimate and waits for you to confirm.</p>
    </section>
  )
}

/** Where to begin (D31 Q2): what the app is, the usual path, which page does what, and the budget and latest run. */
export default function Home() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">RAG Playground</h1>
        <p className="max-w-3xl text-muted">
          Two complete RAG systems answer questions about the 48 documents of an invented consulting firm: Stack A on
          OpenAI's hosted vector store, Stack B on Qdrant with an open embedding model. Each finds the passages that match
          a question, then a language model answers from them. Both are measured on the same 240 test questions, graded
          by a separate judge model, to learn which techniques really improve the answers.
        </p>
      </div>
      <Status />
      <Path />
      <Needs />
    </div>
  )
}
