import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { getOps } from '../api/client.ts'
import type { OpsSummary } from '../api/types.ts'
import Guide from '../components/Guide.tsx'
import { InfoLabel } from '../components/Info.tsx'
import { OPS_HELP } from '../help.ts'
import PageTitle from '../components/PageTitle.tsx'
import { apartLine, budgetLine, budgetTone, failureLine, leftLine, rateText, rateTone, seconds, splitLine, type Tone } from '../ops.ts'

const TONE_TEXT: Record<Tone, string> = { good: 'text-good', warn: 'text-warn', bad: 'text-danger' }
const STEPS = [
  'Spend: what has been spent, what is left, and how it splits between runs and the rest (Ask, enrichment). Past the budget, paid work is refused until BUDGET_USD is raised.',
  'Error rate: the share of background jobs finished in the last 7 days that failed through a fault. Budget stops and jobs cut off by an app restart are counted apart.',
  'Answer time per stack: the typical time (p50) and the slowest 5% (p95) to search and answer one question.',
  'Failed jobs, each with its message. Press Refresh to read the figures again.',
]

function Tile({ title, info, value, tone, children }: { title: string; info: string; value: string; tone?: Tone; children?: ReactNode }) {
  return (
    <section aria-label={title} className="min-w-0 card p-4">
      <InfoLabel label={title} info={info} className="text-sm text-muted" />
      <p className={`text-xl font-semibold [overflow-wrap:anywhere] ${tone ? TONE_TEXT[tone] : ''}`}>{value}</p>
      <div className="mt-1 space-y-0.5 text-sm text-muted">{children}</div>
    </section>
  )
}

function Latency({ summary }: { summary: OpsSummary }) {
  return (
    <section className="min-w-0 overflow-x-auto card p-4">
      <table className="w-full text-left text-sm tabular-nums">
        <caption className="mb-1 text-left font-semibold">
          <InfoLabel label={`Time to search and answer one question, last ${summary.window_days} days`} about="answer time" info={OPS_HELP.latency} className="text-left" />
        </caption>
        <thead className="text-muted">
          <tr><th className="pr-3 font-normal">Stack</th><th className="pr-3 font-normal">Median (p50)</th><th className="pr-3 font-normal">Slowest 5% (p95)</th><th className="font-normal">Questions</th></tr>
        </thead>
        <tbody>
          {summary.latency.map((row) => (
            <tr key={row.stack} className="border-t border-line">
              <td className="pr-3">{row.stack}</td><td className="pr-3">{seconds(row.p50_s)}</td><td className="pr-3">{seconds(row.p95_s)}</td><td>{row.questions}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {summary.latency.length === 0 && <p className="text-sm text-muted">No run started in {summary.window_days} days.</p>}
      <p className="mt-2 text-xs text-muted">Grading is not included. Questions asked on Ask are not stored, so they are not counted.</p>
    </section>
  )
}

/** Health and spend (D14, D30): budget, failed jobs, answer times, the app version and Qdrant. */
export default function Ops() {
  const [summary, setSummary] = useState<OpsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    getOps().then((found) => { setSummary(found); setError(null) }).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => { load() }, [load])

  const top = (
    <>
      <PageTitle title="Ops" about="Spend against the budget, and whether anything failed." />
      <Guide page="Ops" steps={STEPS} purpose="A health check of the app: free, it only reads what is stored." />
    </>
  )
  if (summary === null) {
    return (
      <div className="space-y-5">
        {top}
        <p className={`text-sm ${error ? 'text-danger' : 'text-muted'}`} role={error ? 'alert' : undefined}>{error ?? 'Loading... (checking Qdrant takes a few seconds)'}</p>
        {error && <button type="button" className="btn text-sm" onClick={load}>Try again</button>}
      </div>
    )
  }
  return (
    <div className="space-y-5">
      {top}
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">Failed jobs and answer times cover the last {summary.window_days} days; spend covers everything since the start.</p>
        <button type="button" className="shrink-0 btn text-sm" onClick={load}>Refresh</button>
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="grid items-start gap-4 md:grid-cols-3">
        <Tile title="Spend" info={OPS_HELP.spend} value={budgetLine(summary)} tone={budgetTone(summary)}>
          <p className={TONE_TEXT[budgetTone(summary)]}>{leftLine(summary)}</p>
          <p>{splitLine(summary)}</p>
        </Tile>
        <Tile title="Error rate" info={OPS_HELP.errorRate} value={rateText(summary)} tone={rateTone(summary)}>
          <p>{apartLine(summary)}</p>
        </Tile>
        <Tile title="App" info={OPS_HELP.app} value={`Version ${summary.version}`}>
          <p className={summary.qdrant === 'ok' ? 'text-good' : 'text-danger'}>Qdrant: {summary.qdrant === 'ok' ? 'answers' : summary.qdrant}</p>
        </Tile>
      </div>
      <Latency summary={summary} />
      <section aria-label="Failed jobs" className="min-w-0 space-y-2 card p-4">
        <InfoLabel label={`Failed jobs, last ${summary.window_days} days`} about="failed jobs" info={OPS_HELP.failed} className="font-semibold" />
        {summary.jobs.failed.length === 0 && <p className="text-sm text-muted">None.</p>}
        <ul className="max-h-80 space-y-1 overflow-y-auto text-sm">
          {summary.jobs.failed.map((job) => (
            <li key={job.id} className={`[overflow-wrap:anywhere] ${job.cause === 'fault' ? 'text-danger' : 'text-muted'}`}>{failureLine(job)}</li>
          ))}
        </ul>
      </section>
    </div>
  )
}
