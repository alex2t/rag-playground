import { useEffect, useState } from 'react'
import { getReport } from '../api/client.ts'
import type { RunReport, RunSummary } from '../api/types.ts'
import { hasAnswers, questionsLine, questionsShort, settingsShort, statusLine, statusTone, valuesOfRun, type Tone } from '../evaluate.ts'
import { requestFor, settingsLine, type PanelValues } from '../panel.ts'
import AnswersPanel from './AnswersPanel.tsx'
import RunReportView from './RunReportView.tsx'

/** The chosen run: progress while it runs, then its report and answers. */
export function ShownRun({ run, base, onOpenQuestion }: { run: RunSummary; base: PanelValues; onOpenQuestion: (run: RunSummary, testId: string) => void }) {
  const [report, setReport] = useState<RunReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const finished = run.status === 'done'

  useEffect(() => {
    if (finished) getReport(run.id).then(setReport).catch((e: Error) => setError(e.message))
  }, [run.id, finished])

  const line = settingsLine(requestFor(valuesOfRun(run, base), run.stack))
  return (
    <section aria-label={`Run ${run.id}`} className="min-w-0 space-y-3 card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">Run {run.id}: Stack {run.stack}, {questionsLine(run)}</h2>
        <Badge run={run} />
      </div>
      {run.status === 'running' && <Progress run={run} />}
      {run.status === 'running' && <p className="text-sm text-muted [overflow-wrap:anywhere]">{line}</p>}
      {run.error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{run.error}</p>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {report && <RunReportView report={report} line={line} />}
      {hasAnswers(run) && <AnswersPanel runId={run.id} onOpen={(testId) => onOpenQuestion(run, testId)} />}
    </section>
  )
}

const TONE: Record<Tone, string> = {
  queued: 'bg-line text-ink',
  running: 'bg-accent-soft text-accent-text',
  done: 'bg-good/15 text-good',
  failed: 'bg-danger/15 text-danger',
}

function Badge({ run }: { run: RunSummary }) {
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[statusTone(run)]}`}>{statusLine(run)}</span>
}

function Progress({ run }: { run: RunSummary }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={run.questions} aria-valuenow={run.done}>
      <div className="h-full bg-accent" style={{ width: `${(100 * run.done) / run.questions}%` }} />
    </div>
  )
}

type Props = { runs: RunSummary[]; openId: number | null; onOpen: (id: number) => void }

/** Every stored run, newest first, as a table; Open shows a run's report below it. */
export default function RunsPanel({ runs, openId, onOpen }: Props) {
  return (
    <section aria-label="Runs" className="min-w-0 space-y-3 card p-5">
      <h2 className="font-semibold">All runs</h2>
      {runs.length === 0 && <p className="text-sm text-muted">No run yet. Start one above.</p>}
      {runs.length > 0 && (
        <div className="max-h-56 overflow-auto">
          <table className="w-full text-left text-sm tabular-nums">
            <thead className="sticky top-0 bg-panel text-xs uppercase tracking-wide text-muted">
              <tr><th className="py-2 pr-3">Run</th><th className="pr-3">Stack</th><th className="pr-3">Questions</th><th className="pr-3">Settings</th><th className="pr-3">Status</th><th className="pr-3">Date</th><th><span className="sr-only">Open</span></th></tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} aria-current={run.id === openId ? 'true' : undefined} className={`border-t border-line ${run.id === openId ? 'bg-accent-soft/50' : ''}`}>
                  <td className="py-1.5 pr-3 font-medium">{run.id}</td>
                  <td className="pr-3">{run.stack}</td>
                  <td className="pr-3 whitespace-nowrap">{questionsShort(run)}</td>
                  <td className="pr-3 text-muted">{settingsShort(run.settings)}</td>
                  <td className="pr-3"><Badge run={run} /></td>
                  <td className="pr-3 whitespace-nowrap">{run.created_at.slice(0, 10)}</td>
                  <td className="text-right">
                    <button type="button" className="btn px-2 py-0.5 text-xs" disabled={run.id === openId} onClick={() => onOpen(run.id)}>
                      {run.id === openId ? 'Shown' : 'Open'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
