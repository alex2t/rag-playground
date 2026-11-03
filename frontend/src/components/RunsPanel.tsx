import { useEffect, useState } from 'react'
import { getReport } from '../api/client.ts'
import type { RunReport, RunSummary } from '../api/types.ts'
import { hasAnswers, questionsLine, statusLine, valuesOfRun } from '../evaluate.ts'
import { requestFor, settingsLine, type PanelValues } from '../panel.ts'
import AnswersPanel from './AnswersPanel.tsx'
import RunReportView from './RunReportView.tsx'

function OpenRun({ run, base, onOpenQuestion }: { run: RunSummary; base: PanelValues; onOpenQuestion: (run: RunSummary, testId: string) => void }) {
  const [report, setReport] = useState<RunReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const finished = run.status === 'done'

  useEffect(() => {
    if (finished) getReport(run.id).then(setReport).catch((e: Error) => setError(e.message))
  }, [run.id, finished])

  const line = settingsLine(requestFor(valuesOfRun(run, base), run.stack))
  return (
    <section aria-label={`Run ${run.id}`} className="min-w-0 space-y-3 border-t border-line pt-3">
      <h3 className="font-semibold">Run {run.id}: {questionsLine(run)}</h3>
      {run.status === 'running' && <p className="text-sm text-muted [overflow-wrap:anywhere]">{line}</p>}
      {run.error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{run.error}</p>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {report && <RunReportView report={report} line={line} />}
      {hasAnswers(run) && <AnswersPanel runId={run.id} onOpen={(testId) => onOpenQuestion(run, testId)} />}
    </section>
  )
}

type Props = { runs: RunSummary[]; base: PanelValues; openId: number | null; onOpen: (id: number) => void; onOpenQuestion: (run: RunSummary, testId: string) => void }

/** Every stored run, newest first; a click opens its report and its questions. */
export default function RunsPanel({ runs, base, openId, onOpen, onOpenQuestion }: Props) {
  const open = runs.find((run) => run.id === openId)
  return (
    <section aria-label="Runs" className="min-w-0 space-y-3 card p-4">
      <h2 className="font-semibold">Runs</h2>
      {runs.length === 0 && <p className="text-sm text-muted">No run yet.</p>}
      <ul className="max-h-64 overflow-y-auto text-sm">
        {runs.map((run) => (
          <li key={run.id}>
            <button type="button" aria-current={run.id === openId} className={`w-full rounded px-2 py-1 text-left ${run.id === openId ? 'bg-page font-medium' : ''}`}
              onClick={() => onOpen(run.id)}>
              Run {run.id}, Stack {run.stack}, {questionsLine(run)}, {statusLine(run)}, {run.created_at.slice(0, 10)}
            </button>
          </li>
        ))}
      </ul>
      {open && <OpenRun key={open.id} run={open} base={base} onOpenQuestion={onOpenQuestion} />}
    </section>
  )
}
