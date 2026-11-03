import { useState } from 'react'
import type { RunSummary } from '../api/types.ts'
import { useComparison } from '../api/useComparison.ts'
import { usePanel } from '../api/usePanel.ts'
import { useRuns } from '../api/useRuns.ts'
import CompareResult from '../components/CompareResult.tsx'
import Guide from '../components/Guide.tsx'
import PageTitle from '../components/PageTitle.tsx'
import { comparable, partners, runChoice, settingDiffs } from '../compare.ts'
import { askLink, valuesOfRun } from '../evaluate.ts'
import { saveValues } from '../panel.ts'

const STEPS = [
  'Pick the Before run: usually the baseline, or the set-up you use now.',
  'Pick the After run: the set-up with a change. Only runs of the same question set are offered.',
  'Check "What changes between them": ideally one setting, so you know what made the difference.',
  'Read "What this means" at the top of the result: whether After is really better, and which set-up to keep.',
  'Below it: every score side by side, the cost, and the questions one run got right and the other wrong. Open any of them in Ask.',
]

type PickerProps = { label: string; runs: RunSummary[]; value: number | null; onChange: (id: number | null) => void }

function RunPicker({ label, runs, value, onChange }: PickerProps) {
  return (
    <label className="block min-w-0 text-sm font-medium">
      {label}
      <select className="mt-1 field font-normal" value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Choose a run</option>
        {runs.map((run) => <option key={run.id} value={run.id}>{runChoice(run)}</option>)}
      </select>
    </label>
  )
}

function Changes({ before, after }: { before: RunSummary; after: RunSummary }) {
  const diffs = settingDiffs(before, after)
  if (diffs.length === 0) return <p className="text-sm">The two runs share every setting: any difference comes from the models' own variation.</p>
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="mb-1 text-left font-semibold">What changes between them</caption>
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr><th className="py-1 pr-3">Setting</th><th className="pr-3">Before (run {before.id})</th><th>After (run {after.id})</th></tr>
        </thead>
        <tbody>
          {diffs.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <td className="py-1 pr-3 font-medium">{row.label}</td><td className="pr-3">{row.before}</td><td>{row.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {diffs.length > 1 && <p className="mt-2 text-sm text-warn">{diffs.length} settings differ: a difference cannot be put down to any one of them.</p>}
    </div>
  )
}

/** Two finished runs of one question set side by side (T57): is the difference real, what changed, and which to keep? */
export default function Compare() {
  const { runs, error: runsError } = useRuns()
  const { values } = usePanel()
  const [before, setBefore] = useState<number | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const choices = partners(runs ?? [], before)
  const after = choices.some((run) => run.id === picked) ? picked : null
  const { comparison, error } = useComparison(before, after)

  if (runs === null) return <p className="text-sm text-muted">{runsError ?? 'Loading...'}</p>

  const offered = comparable(runs)
  const beforeRun = runs.find((run) => run.id === before)
  const afterRun = runs.find((run) => run.id === after)
  const waiting = before !== null && after !== null && !comparison && !error
  const openInAsk = values && afterRun
    ? (testId: string) => { saveValues(valuesOfRun(afterRun, values)); location.hash = askLink(testId) }
    : null
  return (
    <div className="space-y-5">
      <PageTitle title="Compare" about="Is one set-up really better than another, or is the gap just chance?" />
      <Guide page="Compare" steps={STEPS}
        purpose="Two runs rarely score the same, even with one set-up, because the models vary. Compare tests whether a gap is bigger than that variation, on the very same questions, with the paired test Story uses. Free: it reads finished runs."
        note="Smoke tests and samples are not offered: 20 questions are too few to tell a real difference from chance. Start full runs on Evaluate." />
      <section aria-label="Choose two runs" className="min-w-0 space-y-4 card p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <RunPicker label="1. Before" runs={offered} value={before} onChange={setBefore} />
          <RunPicker label="2. After" runs={choices} value={after} onChange={setPicked} />
        </div>
        {offered.length < 2 && <p className="text-sm text-muted">Compare needs two finished runs of a whole question set. Start them on Evaluate.</p>}
        {offered.length >= 2 && before === null && <p className="text-sm text-muted">Start with the Before run.</p>}
        {offered.length >= 2 && before !== null && choices.length === 0 && <p className="text-sm text-muted">No other finished run asked the same questions.</p>}
        {beforeRun && afterRun && <Changes before={beforeRun} after={afterRun} />}
        {runsError && <p role="alert" className="text-sm text-danger">{runsError}</p>}
        {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
        {waiting && <p className="text-sm text-muted">Comparing...</p>}
      </section>
      {comparison && <CompareResult comparison={comparison} onOpen={openInAsk} />}
    </div>
  )
}
