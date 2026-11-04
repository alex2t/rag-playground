import { useState } from 'react'
import type { RunReport, RunScores } from '../api/types.ts'
import { bandOf, HEADLINE, OTHER, reportCsv, TRUST, type Band, type Metric } from '../evaluate.ts'
import { CATEGORY_HELP, HELP, METRIC_HELP } from '../help.ts'
import { InfoLabel } from './Info.tsx'

const BAND_TEXT: Record<Band, string> = { good: 'text-good', fair: 'text-warn', poor: 'text-danger' }

function downloadCsv(report: RunReport) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([reportCsv(report)], { type: 'text/csv' }))
  link.download = `run-${report.id}-report.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

function Tile({ metric, scores }: { metric: Metric; scores: RunScores }) {
  const value = scores[metric.key]
  const band = bandOf(metric.key, value)
  return (
    <div className="rounded border border-line p-2">
      <InfoLabel label={metric.label} info={METRIC_HELP[metric.key]} className="text-sm text-muted" />
      <p className={`text-xl font-semibold ${band ? BAND_TEXT[band] : ''}`}>{value.toFixed(3)}</p>
      {band && <p className={`text-xs ${BAND_TEXT[band]}`}>{band}</p>}
    </div>
  )
}

function Tiles({ metrics, scores }: { metrics: Metric[]; scores: RunScores }) {
  return <div className="grid grid-cols-2 items-start gap-2 md:grid-cols-4">{metrics.map((metric) => <Tile key={metric.key} metric={metric} scores={scores} />)}</div>
}

function Categories({ report }: { report: RunReport }) {
  if (report.categories === null) return <p className="text-sm text-muted">A held-out run shows its overall scores only: those questions stay out of tuning.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="mb-1 text-left font-medium">Scores by question category</caption>
        <thead className="text-muted">
          <tr><th className="pr-3 font-normal">Category</th><th className="pr-3 font-normal">Questions</th><th className="pr-3 font-normal">Accuracy</th><th className="pr-3 font-normal">Completeness</th><th className="pr-3 font-normal">Relevance</th><th className="font-normal">Faithfulness</th></tr>
        </thead>
        <tbody>
          {report.categories.map((row) => (
            <tr key={row.category} className="border-t border-line">
              <td className="max-w-64 py-1 pr-3 align-top">
                {CATEGORY_HELP[row.category] ? <InfoLabel label={row.category} info={CATEGORY_HELP[row.category]} /> : row.category}
              </td><td className="pr-3">{row.questions}</td>
              <td className="pr-3">{row.accuracy.toFixed(2)}</td><td className="pr-3">{row.completeness.toFixed(2)}</td>
              <td className="pr-3">{row.relevance.toFixed(2)}</td><td>{row.faithfulness.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A finished run: 4 headline tiles, the other scores on request, refusal rates, categories and export. */
export default function RunReportView({ report, line }: { report: RunReport; line: string }) {
  const [all, setAll] = useState(false)
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted [overflow-wrap:anywhere]">{line}</p>
      {!report.settings.temperature_controlled && <p className="text-sm font-medium">Temperature not controlled.</p>}
      <Tiles metrics={HEADLINE} scores={report.scores} />
      <button type="button" className="text-sm underline" aria-expanded={all} onClick={() => setAll(!all)}>{all ? 'Show fewer' : 'Show all'}</button>
      {all && <Tiles metrics={OTHER} scores={report.scores} />}
      <Tiles metrics={TRUST} scores={report.scores} />
      <InfoLabel label={report.failed_gates.length ? `Fails the gates: ${report.failed_gates.join(', ')}.` : 'Passes every gate.'}
        about="the gates" info={HELP.gates} />
      <p className="text-sm">${report.cost_per_question.toFixed(4)} per question, {report.latency_s.toFixed(1)} s per answer.</p>
      <Categories report={report} />
      <button type="button" className="btn text-sm" onClick={() => downloadCsv(report)}>Download CSV</button>
    </div>
  )
}
