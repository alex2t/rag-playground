import { useState } from 'react'
import type { RunSummary } from '../api/types.ts'
import { useComparison } from '../api/useComparison.ts'
import { usePanel } from '../api/usePanel.ts'
import { useRuns } from '../api/useRuns.ts'
import CompareResult from '../components/CompareResult.tsx'
import Guide from '../components/Guide.tsx'
import PageTitle from '../components/PageTitle.tsx'
import { comparable, runLine, settingDiffs } from '../compare.ts'
import { askLink, valuesOfRun } from '../evaluate.ts'
import { saveValues } from '../panel.ts'
import { afterPool, LABELS, oneApart, options, pickedRun, settle, valuesOf, type Picks } from '../runPicker.ts'

const STEPS = [
  'Choose the Before set-up, top to bottom: usually the baseline, or the set-up you use now. Each list offers only values a finished run has, and a list with one value fills itself in.',
  'Choose the After set-up the same way, or pick it from "Runs that differ in one setting only", which fills it in for you.',
  'Check "What changes between them": ideally one setting, so you know what made the difference.',
  'Read "What this means" at the top of the result: whether After is really better, and which set-up to keep.',
  'Below it: every score side by side, the cost, and the questions one run got right and the other wrong. Open any of them in Ask.',
]

type PickerProps = { title: string; runs: RunSummary[]; picks: Picks; onChange: (picks: Picks) => void }

function SetupPicker({ title, runs, picks, onChange }: PickerProps) {
  const settled = settle(runs, picks)
  const picked = pickedRun(runs, settled)
  return (
    <fieldset className="min-w-0 space-y-2">
      <legend className="mb-2 text-sm font-semibold">{title}</legend>
      {LABELS.map((label, index) => {
        const open = LABELS.slice(0, index).every((above) => settled[above] !== undefined)
        return (
          <label key={label} className="grid grid-cols-[8.5rem_minmax(0,1fr)] items-center gap-2 text-sm">
            {label}
            <select className="field" disabled={!open} value={settled[label] ?? ''}
              onChange={(e) => onChange({ ...settled, [label]: e.target.value })}>
              <option value="">{open ? 'Choose' : ''}</option>
              {open && options(runs, settled, label).map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        )
      })}
      {picked && picked.count > 1 && <p className="text-xs text-muted">{picked.count} runs have these settings: the oldest is used.</p>}
    </fieldset>
  )
}

type OneApartProps = { runs: RunSummary[]; chosen: RunSummary; after: RunSummary | undefined; onPick: (run: RunSummary) => void }

function OneApartPicker({ runs, chosen, after, onPick }: OneApartProps) {
  const near = oneApart(runs, chosen)
  if (near.length === 0) return <p className="text-sm text-muted">No finished run differs from Before in one setting only. To measure one setting, start a run with only that setting changed on Evaluate or Sweep.</p>
  const value = near.some(({ run }) => run.id === after?.id) ? String(after!.id) : ''
  return (
    <label className="block min-w-0 text-sm font-medium">
      Runs that differ in one setting only
      <select className="mt-1 field font-normal" value={value}
        onChange={(e) => { const found = near.find(({ run }) => String(run.id) === e.target.value); if (found) onPick(found.run) }}>
        <option value="">Choose one to fill in After</option>
        {near.map(({ run, label }) => <option key={run.id} value={run.id}>{label} differs: {runLine(run)}</option>)}
      </select>
    </label>
  )
}

function Changes({ before, after }: { before: RunSummary; after: RunSummary }) {
  if (before.id === after.id) return <p className="text-sm text-warn">Before and After are the same run: change at least one setting.</p>
  const diffs = settingDiffs(before, after)
  if (diffs.length === 0) return <p className="text-sm">The two runs share every setting: any difference comes from the models' own variation.</p>
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="mb-1 text-left font-semibold">What changes between them</caption>
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr><th className="py-1 pr-3">Setting</th><th className="pr-3">Before</th><th>After</th></tr>
        </thead>
        <tbody>
          {diffs.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <td className="py-1 pr-3 font-medium">{row.label}</td><td className="pr-3">{row.before}</td><td>{row.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {diffs.length > 1 && <p className="mt-2 text-sm text-warn">{diffs.length} settings differ. Compare still tells you which set-up is better, which is what you need to pick the best one, but not which of these settings made the difference. To measure one setting, compare two runs that differ in that setting only.</p>}
    </div>
  )
}

/** Two finished runs of one question set side by side (T57): is the difference real, what changed, and which to keep? */
export default function Compare() {
  const { runs, error: runsError } = useRuns()
  const { values } = usePanel()
  const [beforePicks, setBeforePicks] = useState<Picks>({})
  const [afterPicks, setAfterPicks] = useState<Picks>({})
  const offered = comparable(runs ?? [])
  const beforeRun = pickedRun(offered, settle(offered, beforePicks))?.run
  const afterRuns = afterPool(offered, beforeRun)
  const afterRun = pickedRun(afterRuns, settle(afterRuns, afterPicks))?.run
  const pair = beforeRun && afterRun && beforeRun.id !== afterRun.id
  const { comparison, error } = useComparison(pair ? beforeRun.id : null, pair ? afterRun.id : null)

  if (runs === null) return <p className="text-sm text-muted">{runsError ?? 'Loading...'}</p>

  const waiting = pair && !comparison && !error
  const openInAsk = values && afterRun
    ? (testId: string) => { saveValues(valuesOfRun(afterRun, values)); location.hash = askLink(testId) }
    : null
  return (
    <div className="space-y-5">
      <PageTitle title="Compare" about="Is one set-up really better than another, or is the gap just chance?" />
      <Guide page="Compare" steps={STEPS}
        purpose="Two runs rarely score the same, even with one set-up, because the models vary. Compare tests whether a gap is bigger than that variation, on the very same questions, with the paired test Story uses. Free: it reads finished runs."
        note="Smoke tests and samples are not offered: 20 questions are too few to tell a real difference from chance. Start full runs on Evaluate." />
      <section aria-label="Choose two set-ups" className="min-w-0 space-y-4 card p-5">
        {offered.length < 2 && <p className="text-sm text-muted">Compare needs two finished runs of a whole question set. Start them on Evaluate.</p>}
        <div className="grid gap-6 md:grid-cols-2">
          <div className="min-w-0 space-y-4">
            <SetupPicker title="1. Before" runs={offered} picks={beforePicks} onChange={setBeforePicks} />
            {beforeRun && <OneApartPicker runs={offered} chosen={beforeRun} after={afterRun}
              onPick={(run) => setAfterPicks(valuesOf(run))} />}
          </div>
          <SetupPicker title="2. After" runs={afterRuns} picks={afterPicks} onChange={setAfterPicks} />
        </div>
        {beforeRun && afterRun && <Changes before={beforeRun} after={afterRun} />}
        {runsError && <p role="alert" className="text-sm text-danger">{runsError}</p>}
        {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
        {waiting && <p className="text-sm text-muted">Comparing...</p>}
      </section>
      {comparison && <CompareResult comparison={comparison} onOpen={openInAsk} />}
    </div>
  )
}
