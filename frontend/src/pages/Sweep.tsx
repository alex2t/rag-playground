import { useEffect, useState } from 'react'
import { useReadOnly } from '../readOnly.ts'
import { getLatestSweep, planSweep, startSweep } from '../api/client.ts'
import type { PanelOptions, SweepPlan, SweepValue } from '../api/types.ts'
import { useBuilds } from '../api/useBuilds.ts'
import { usePanel } from '../api/usePanel.ts'
import type { LegendLine } from '../chartImage.ts'
import Guide from '../components/Guide.tsx'
import { InfoLabel } from '../components/Info.tsx'
import { HELP } from '../help.ts'
import PageTitle from '../components/PageTitle.tsx'
import LadderChart from '../components/LadderChart.tsx'
import SettingsPanel from '../components/SettingsPanel.tsx'
import { chunksProblem } from '../chunks.ts'
import { panelProblem, saveValues, stacksOf, type PanelValues } from '../panel.ts'
import { hashOf, pageLink } from '../route.ts'
import {
  bodyFor, chartRows, choicesFor, fromKey, isWorking, overBudget, parseNumbers, planKey, planLine, plansFor, pollKey, toRun, valueText,
  sweepJobLine, variableOf, variablesFor, type Latest, type Planned,
} from '../sweep.ts'

const BOX = 'mt-1 field'
const POLL_MS = 2000
const NOTE = 'Exploratory: dev questions only. Bars show the 95% interval. + or - marks a real change against the base value. Many values tested at once can show a real-looking difference by luck.'
const IMAGE_LEGEND: LegendLine[] = [
  { text: 'Stack A (filled)', swatch: '--color-stack-a' },
  { text: 'Stack B (hollow)', swatch: '--color-stack-b' },
  { text: 'Exploratory: dev questions only. Bars: 95% interval.' },
  { text: '+ or -: real change against the base value.' },
]

const STEPS = [
  'Set the base set-up in the Settings box: every value is compared with it.',
  'Choose the one setting to vary, and its values: at most 6, the base set-up\'s own value included.',
  'Press Estimate: each value shows its stored run, or its cost if it still has to run. Values with a run already cost nothing.',
  'Press Confirm to run the missing values on the 192 dev questions. You can leave the page and come back.',
  'Read the charts: each value\'s accuracy and MRR with its 95% interval; + or - marks a real change against the base value. Open any value\'s run on Evaluate.',
]

const PAGES_COMPARED = [
  ['Evaluate', 'One set-up you choose', 'You read its report'],
  ['Sweep', 'Several values of one setting, the rest of your set-up fixed', 'Nobody: exploratory, no winner'],
  ['Story', 'The study\'s fixed ladder of steps, S0 to S7', 'A rule set in advance (T08)'],
]

function PagesCompared() {
  return (
    <div className="mt-3 min-w-0 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="mb-1 text-left font-semibold">Sweep, Evaluate or Story?</caption>
        <thead className="text-xs uppercase tracking-wide text-muted">
          <tr><th className="py-1 pr-3">Page</th><th className="pr-3">What it measures</th><th>Who picks the winner</th></tr>
        </thead>
        <tbody>
          {PAGES_COMPARED.map(([page, measures, picks]) => (
            <tr key={page} className="border-t border-line"><td className="py-1 pr-3 font-medium">{page}</td><td className="pr-3">{measures}</td><td>{picks}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Picks({ choices, picked, onChange }: { choices: SweepValue[]; picked: SweepValue[]; onChange: (picked: SweepValue[]) => void }) {
  return (
    <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
      <legend className="mb-1">Values</legend>
      {choices.map((choice) => (
        <label key={String(choice)} className="flex items-center gap-1">
          <input type="checkbox" checked={picked.includes(choice)}
            onChange={(e) => onChange(e.target.checked ? choices.filter((c) => c === choice || picked.includes(c)) : picked.filter((c) => c !== choice))} />
          {valueText(choice)}
        </label>
      ))}
    </fieldset>
  )
}

function PlanTable({ plan }: { plan: SweepPlan }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-left text-sm tabular-nums">
        <caption className="mb-1 text-left font-medium">Stack {plan.stack}</caption>
        <thead className="text-muted">
          <tr><th className="pr-3 font-normal">Value</th><th className="pr-3 font-normal">Run</th><th className="pr-3 font-normal">Accuracy</th><th className="pr-3 font-normal">MRR</th><th className="font-normal">Against the base</th></tr>
        </thead>
        <tbody>
          {plan.items.map((item) => (
            <tr key={String(item.value)} className="border-t border-line">
              <td className="pr-3 [overflow-wrap:anywhere]">{valueText(item.value)}{item.base && ' (base)'}</td>
              <td className="pr-3 whitespace-nowrap">{item.run ? <a className="text-accent-text underline" href={pageLink('Evaluate', { run: String(item.run.run_id) })}>run {item.run.run_id}</a> : `to run, $${item.estimate_usd!.toFixed(4)}${item.built ? '' : ', chunks to build'}`}</td>
              <td className="pr-3">{item.run ? `${item.run.accuracy.toFixed(3)} (${item.run.accuracy_ci[0].toFixed(2)} to ${item.run.accuracy_ci[1].toFixed(2)})` : ''}</td>
              <td className="pr-3">{item.run ? `${item.run.mrr.toFixed(3)} (${item.run.mrr_ci[0].toFixed(2)} to ${item.run.mrr_ci[1].toFixed(2)})` : ''}</td>
              <td>{item.run?.change ? `accuracy ${item.run.change.accuracy.verdict}, MRR ${item.run.change.mrr.verdict}` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Results({ plans, variable }: { plans: SweepPlan[]; variable: string }) {
  const about = variableOf(variable)
  const anyRun = plans.some((plan) => plan.items.some((item) => item.run))
  return (
    <div className="space-y-4">
      {anyRun && (
        <div className="grid gap-4 xl:grid-cols-2">
          <LadderChart title={`Accuracy by ${about.label.toLowerCase()} (1 to 5, 192 dev questions)`} rows={chartRows(plans, about, 'accuracy')}
            domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} note={NOTE} imageLegend={IMAGE_LEGEND} connect={about.ordered} />
          <LadderChart title={`MRR by ${about.label.toLowerCase()} (0 to 1, answerable dev questions)`} rows={chartRows(plans, about, 'mrr')}
            domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} note={NOTE} imageLegend={IMAGE_LEGEND} connect={about.ordered} />
        </div>
      )}
      <section aria-label="Sweep values" className="min-w-0 space-y-3 card p-4">
        {plans.map((plan) => <PlanTable key={plan.stack} plan={plan} />)}
        <p className="text-xs text-muted">Exploratory: dev questions only, and no value is picked as the winner. Only one setting changes, so how settings interact is not shown.</p>
        <p className="text-sm"><strong>Next step:</strong> test the most promising value against your base on{' '}
          <a className="text-accent-text underline" href={hashOf('Compare')}>Compare</a>. If the gain is real, choose that value in the
          Settings box: it becomes your new base for the next setting.</p>
      </section>
    </div>
  )
}

type ValuesProps = { variable: string; options: PanelOptions; promptNames: string[]; typed: string; picked: SweepValue[]; onType: (text: string) => void; onPick: (picked: SweepValue[]) => void }

function ValuesInput({ variable, options, promptNames, typed, picked, onType, onPick }: ValuesProps) {
  const about = variableOf(variable)
  if (about.kind === 'pick') return <Picks choices={choicesFor(variable, options, promptNames)} picked={picked} onChange={onPick} />
  return (
    <label className="block text-sm">
      Values, separated by commas
      <input className={BOX} value={typed} placeholder={about.kind === 'int' ? '200, 400, 800' : '0, 0.5, 2'} onChange={(e) => onType(e.target.value)} />
    </label>
  )
}

/** One setting over several values on the dev questions (T58): Estimate, then Confirm, then follow it below. */
export default function Sweep() {
  const readOnly = useReadOnly()
  const { options, promptNames, values, setValues, error: panelError } = usePanel()
  const { builds } = useBuilds()
  const [variable, setVariable] = useState('chunk_size')
  const [typed, setTyped] = useState('')
  const [picked, setPicked] = useState<SweepValue[]>([])
  const [planned, setPlanned] = useState<Planned | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [latest, setLatest] = useState<Latest>({})

  const offered = values ? variablesFor(values.stacks) : []
  const current = offered.some((v) => v.key === variable) ? variable : 'chunk_size'
  const parsed = variableOf(current).kind === 'pick' ? { values: picked } : parseNumbers(variableOf(current).kind, typed)
  const list = 'values' in parsed ? parsed.values : null
  const key = values && list ? planKey(values, current, list) : ''
  const plans = plansFor(planned, key)
  const replan = pollKey(planned, key)
  const working = isWorking(latest)
  const stackChoice = values?.stacks

  useEffect(() => {
    if (!stackChoice) return
    Promise.all(stacksOf(stackChoice).map(async (stack) => [stack, await getLatestSweep(stack)] as const))
      .then((found) => setLatest(Object.fromEntries(found)))
      .catch((e: Error) => setError(e.message))
  }, [stackChoice])

  useEffect(() => {
    if (!working || !stackChoice) return
    const timer = setInterval(async () => {
      try {
        const found = await Promise.all(stacksOf(stackChoice).map(async (stack) => [stack, await getLatestSweep(stack)] as const))
        setLatest(Object.fromEntries(found))
        if (!replan) return
        const [panel, setting, chosen] = fromKey(replan)
        const fresh = await Promise.all(stacksOf(panel.stacks).map((stack) => planSweep(bodyFor(panel, stack, setting, chosen))))
        setPlanned((before) => (before?.key === replan ? { key: replan, plans: fresh } : before))
      } catch (e) {
        setError((e as Error).message)
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [working, replan, stackChoice])

  if (panelError) return <p role="alert" className="text-sm text-danger">{panelError}</p>
  if (options === null || values === null) return <p className="text-sm text-muted">Loading...</p>

  const panel: PanelValues = values
  const problem = panelProblem(panel, options) ?? chunksProblem(builds?.built ?? null, panel) ?? ('problem' in parsed ? parsed.problem : list!.length === 0 ? 'Tick at least one value.' : null)
  const stacks = stacksOf(panel.stacks)
  const runnable = plans ? toRun(plans) : []
  const over = plans !== null && overBudget(plans)

  async function estimate() {
    setBusy(true)
    setError(null)
    try {
      const fresh = await Promise.all(stacks.map((stack) => planSweep(bodyFor(panel, stack, current, list!))))
      setPlanned({ key, plans: fresh })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    setBusy(true)
    setError(null)
    saveValues(panel)
    const refused: string[] = []
    for (const stack of runnable) {
      try {
        await startSweep(bodyFor(panel, stack, current, list!))
      } catch (e) {
        refused.push(`Stack ${stack}: ${(e as Error).message}`)
      }
    }
    setError(refused.length ? refused.join(' ') : null)
    setLatest(Object.fromEntries(await Promise.all(stacks.map(async (stack) => [stack, await getLatestSweep(stack)] as const))))
    await estimate()
  }

  const jobs = stacks.flatMap((stack) => (latest[stack] ? [{ stack, job: latest[stack] }] : []))
  return (
    <div className="space-y-5">
      <PageTitle title="Sweep" about="See how one setting changes the scores, with everything else fixed." />
      <Guide page="Sweep" steps={STEPS}
        purpose="For example top-K = 2, 4, 6 and 8 with the rest of your set-up unchanged: one run per value on the 192 dev questions, side by side on one chart."
        note="Exploratory: a sweep picks no winner and uses dev questions only. To decide between two set-ups, use Compare.">
        <PagesCompared />
      </Guide>
      <div className="grid gap-5 md:grid-cols-[22rem_minmax(0,1fr)]">
        <SettingsPanel values={panel} options={options} promptNames={promptNames} built={builds?.built ?? null} onChange={setValues} />
        <div className="min-w-0 space-y-5">
        <section aria-label="Sweep" className="min-w-0 space-y-3 card p-5">
          <h2 className="font-semibold">What to vary</h2>
          <p className="text-sm text-muted">The Settings box is the base set-up. Only the setting chosen here changes.</p>
          <div>
            <InfoLabel label="Setting to vary" info={HELP.sweepVariable} htmlFor="sweep-variable" />
            <select id="sweep-variable" className={BOX} value={current} onChange={(e) => { setVariable(e.target.value); setPicked([]); setTyped('') }}>
              {offered.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
            </select>
          </div>
          <ValuesInput variable={current} options={options} promptNames={promptNames} typed={typed} picked={picked} onType={setTyped} onPick={setPicked} />
          <p className="text-xs text-muted">At most 6 values, the base configuration's own value included: it is what the others are compared with.</p>
          <div className="flex gap-2">
            <button type="button" className="btn text-sm" disabled={busy || problem !== null || readOnly}
              onClick={() => void estimate()}>1. Estimate</button>
            <button type="button" className="btn-primary text-sm"
              disabled={busy || plans === null || runnable.length === 0 || over || working || readOnly} onClick={() => void confirm()}>2. Confirm</button>
          </div>
          {problem && <p className="text-sm text-muted">{problem}</p>}
          {plans && <p className="text-sm">{planLine(plans)}</p>}
          {over && <p role="alert" className="text-sm text-danger">Only ${plans[0].budget_left_usd.toFixed(4)} of the budget is left.</p>}
          {!plans && !problem && <p className="text-sm text-muted">Confirm turns on once you press Estimate, which shows each value's run or cost.</p>}
          {plans && runnable.length === 0 && !working && <p className="text-sm text-muted">Nothing to pay: the results are below.</p>}
          {jobs.map(({ stack, job }) => (
            <p key={stack} role={job.status === 'failed' ? 'alert' : undefined}
              className={`text-sm [overflow-wrap:anywhere] ${job.status === 'failed' ? 'text-danger' : 'text-muted'}`}>
              {sweepJobLine(stack, job)}
            </p>
          ))}
          {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
        </section>
        {plans && <Results plans={plans} variable={current} />}
        </div>
      </div>

    </div>
  )
}
