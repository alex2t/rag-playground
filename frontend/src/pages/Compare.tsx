import { useState } from 'react'
import type { RunSummary } from '../api/types.ts'
import { useComparison } from '../api/useComparison.ts'
import { useRuns } from '../api/useRuns.ts'
import CompareResult from '../components/CompareResult.tsx'
import { comparable, partners, runChoice } from '../compare.ts'

type PickerProps = { label: string; runs: RunSummary[]; value: number | null; onChange: (id: number | null) => void }

function RunPicker({ label, runs, value, onChange }: PickerProps) {
  return (
    <label className="block min-w-0 text-sm">
      {label}
      <select className="mt-1 w-full rounded border border-line bg-transparent px-2 py-1" value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Choose a run</option>
        {runs.map((run) => <option key={run.id} value={run.id}>{runChoice(run)}</option>)}
      </select>
    </label>
  )
}

/** Two finished runs of one question set side by side (T57): is the difference real, and what did it change? */
export default function Compare() {
  const { runs, error: runsError } = useRuns()
  const [before, setBefore] = useState<number | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const choices = partners(runs ?? [], before)
  const after = choices.some((run) => run.id === picked) ? picked : null
  const { comparison, error } = useComparison(before, after)

  if (runs === null) return <p className="text-sm text-muted">{runsError ?? 'Loading...'}</p>

  const offered = comparable(runs)
  const waiting = before !== null && after !== null && !comparison && !error
  return (
    <div className="space-y-4">
      <section aria-label="Choose two runs" className="min-w-0 space-y-3 rounded-lg border border-line bg-panel p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <RunPicker label="Before" runs={offered} value={before} onChange={setBefore} />
          <RunPicker label="After" runs={choices} value={after} onChange={setPicked} />
        </div>
        {offered.length < 2 && <p className="text-sm text-muted">Compare needs two finished runs of a whole question set. Start them on Evaluate.</p>}
        {offered.length >= 2 && before !== null && choices.length === 0 && <p className="text-sm text-muted">No other finished run asked the same questions.</p>}
        {offered.length >= 2 && (before === null || after === null) && <p className="text-sm text-muted">Samples and smoke tests are not offered: they ask too few questions to compare.</p>}
        {runsError && <p role="alert" className="text-sm text-danger">{runsError}</p>}
        {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
        {waiting && <p className="text-sm text-muted">Comparing...</p>}
      </section>
      {comparison && <CompareResult comparison={comparison} />}
    </div>
  )
}
