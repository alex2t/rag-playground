import type { Comparison, MovedQuestion, PairedChange, RunReport } from '../api/types.ts'
import { changeLine, depthNote, recommendation, runLine, signed, tableRows } from '../compare.ts'
import CompareCharts from './CompareCharts.tsx'

const VERDICT_TEXT: Record<PairedChange['verdict'], string> = { better: 'text-good', worse: 'text-danger', 'no real difference': 'text-muted' }

function Verdict({ name, line, change }: { name: string; line: string; change: PairedChange }) {
  return (
    <div className="rounded border border-line p-3">
      <p className="text-sm text-muted">{name}</p>
      <p className={`text-xl font-semibold ${VERDICT_TEXT[change.verdict]}`}>{change.verdict}</p>
      <p className="mt-1 text-sm [overflow-wrap:anywhere]">{line}</p>
    </div>
  )
}

function RunCard({ name, report }: { name: string; report: RunReport }) {
  return (
    <div className="min-w-0 rounded border border-line p-3 text-sm">
      <h3 className="font-semibold">{name}: run {report.id}</h3>
      <p className="text-muted [overflow-wrap:anywhere]">{runLine(report)}</p>
      {!report.settings.temperature_controlled && <p className="font-medium">Temperature not controlled.</p>}
      <p>{report.failed_gates.length ? `Fails the gates: ${report.failed_gates.join(', ')}.` : 'Passes every gate.'}</p>
    </div>
  )
}

function ScoresTable({ comparison }: { comparison: Comparison }) {
  return (
    <section className="min-w-0 overflow-x-auto card p-4">
      <table className="w-full text-left text-sm tabular-nums">
        <caption className="mb-1 text-left font-medium">All scores</caption>
        <thead className="text-muted">
          <tr><th className="pr-3 font-normal">Score</th><th className="pr-3 font-normal">Before</th><th className="pr-3 font-normal">After</th><th className="font-normal">Change</th></tr>
        </thead>
        <tbody>
          {tableRows(comparison).map(({ label, before, after, digits, lowerIsBetter }) => (
            <tr key={label} className="border-t border-line">
              <td className="pr-3">{label}{lowerIsBetter && <span className="text-muted"> (lower is better)</span>}</td>
              <td className="pr-3">{before.toFixed(digits)}</td><td className="pr-3">{after.toFixed(digits)}</td>
              <td>{signed(after - before, digits)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">Only accuracy and MRR are tested for a real difference. A change in another row may be noise.</p>
    </section>
  )
}

type OnOpen = ((testId: string) => void) | null

function MovedList({ title, moved, onOpen }: { title: string; moved: MovedQuestion[]; onOpen: OnOpen }) {
  return (
    <div className="min-w-0">
      <h3 className="font-semibold">{title} ({moved.length})</h3>
      {moved.length === 0 && <p className="text-sm text-muted">None.</p>}
      <ul className="max-h-96 space-y-2 overflow-y-auto text-sm">
        {moved.map((item) => (
          <li key={item.test_id} className="border-t border-line pt-2">
            <p className="[overflow-wrap:anywhere]">{item.question}</p>
            <p className="text-muted">{item.category}, accuracy {item.before} to {item.after}</p>
            {onOpen && <button type="button" className="text-sm text-accent-text underline" onClick={() => onOpen(item.test_id)}>Open in Ask with After's settings</button>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Questions({ comparison, onOpen }: { comparison: Comparison; onOpen: OnOpen }) {
  const moved = comparison.questions
  if (moved === null) return <p className="text-sm text-muted">Held-out runs compare overall only: those questions stay out of tuning.</p>
  return (
    <section aria-label="Questions that changed" className="min-w-0 space-y-3 card p-4">
      <p className="text-sm">
        A question is fixed or broken when its accuracy crosses the pass mark of 4.
        {' '}{moved.both_pass} passed in both runs, {moved.both_fail} failed in both.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <MovedList title="Fixed" moved={moved.fixed} onOpen={onOpen} />
        <MovedList title="Broken" moved={moved.broken} onOpen={onOpen} />
      </div>
    </section>
  )
}

/** Whether After really differs from Before, what each run was, and the scores and questions behind it. */
export default function CompareResult({ comparison, onOpen }: { comparison: Comparison; onOpen: OnOpen }) {
  const { before, after, change } = comparison
  const depth = depthNote(comparison)
  return (
    <div className="space-y-5">
      <section aria-label="Advice" className="card border-accent bg-accent-soft/40 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-accent-text">What this means</h2>
        <p className="mt-1 text-lg font-medium">{recommendation(comparison)}</p>
        <p className="mt-2 text-sm text-muted">"Really" means the paired test on the same questions puts the whole 95% interval of the accuracy change on one side of zero, the rule Story uses to keep a step. As on Story, only a run that passes every gate (minimum MRR, Recall@K, faithfulness and correct refusal rate) can be kept.</p>
      </section>
      <section aria-label="Result" className="min-w-0 space-y-3 card p-4">
        <div className="grid gap-2 md:grid-cols-2">
          <Verdict name="Accuracy" line={changeLine(before.scores.accuracy, after.scores.accuracy, change.accuracy)} change={change.accuracy} />
          <Verdict name="MRR" line={changeLine(before.scores.mrr, after.scores.mrr, change.mrr)} change={change.mrr} />
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <RunCard name="Before" report={before} />
          <RunCard name="After" report={after} />
        </div>
        {depth && <p className="text-sm font-medium">{depth}</p>}
        <p className="text-xs text-muted">Comparing many pairs will find a real-looking difference by luck: no correction is made for that.</p>
      </section>
      <CompareCharts comparison={comparison} />
      <ScoresTable comparison={comparison} />
      <Questions comparison={comparison} onOpen={onOpen} />
    </div>
  )
}
