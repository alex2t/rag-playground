import { useState } from 'react'
import { estimateRun, startRun } from '../api/client.ts'
import type { QuestionSet, RunSummary } from '../api/types.ts'
import { usePanel } from '../api/usePanel.ts'
import { useRuns } from '../api/useRuns.ts'
import RunsPanel from '../components/RunsPanel.tsx'
import SettingsPanel from '../components/SettingsPanel.tsx'
import { askLink, estimateFor, estimateLine, overBudget, valuesOfRun, type Estimated } from '../evaluate.ts'
import { panelProblem, requestFor, saveValues, stacksOf } from '../panel.ts'

const QUESTION_SETS: { value: QuestionSet; label: string }[] = [
  { value: 'dev', label: 'Dev (192 questions)' },
  { value: 'smoke', label: 'Smoke test (20 questions)' },
  { value: 'heldout', label: 'Held-out (48 questions)' },
]

/** Scores one configuration on many questions (T56): Estimate, then Evaluate, then read the run below. */
export default function Evaluate() {
  const { options, promptNames, values, setValues, error: panelError } = usePanel()
  const { runs, error: runsError, reload } = useRuns()
  const [questions, setQuestions] = useState<QuestionSet>('dev')
  const [estimated, setEstimated] = useState<Estimated | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)

  if (panelError) return <p role="alert" className="text-sm text-danger">{panelError}</p>
  if (options === null || values === null || runs === null) return <p className="text-sm text-muted">{runsError ?? 'Loading...'}</p>

  const current = values
  const problem = panelProblem(current, options)
  const estimates = estimateFor(estimated, current, questions)

  async function estimate() {
    setBusy(true)
    setError(null)
    try {
      const items = await Promise.all(stacksOf(current.stacks).map(async (stack) => ({ stack, ...await estimateRun(requestFor(current, stack), questions) })))
      setEstimated({ values: current, questions, items })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function evaluate() {
    setBusy(true)
    setError(null)
    saveValues(current)
    try {
      for (const stack of stacksOf(current.stacks)) await startRun(requestFor(current, stack), questions)
    } catch (e) {
      setError((e as Error).message)
    }
    setEstimated(null)
    setBusy(false)
    await reload()
  }

  function openQuestion(run: RunSummary, testId: string) {
    saveValues(valuesOfRun(run, current))
    location.hash = askLink(testId)
  }

  const over = estimates !== null && overBudget(estimates)
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[22rem_minmax(0,1fr)]">
        <SettingsPanel values={current} options={options} promptNames={promptNames} onChange={setValues} />
        <section aria-label="Evaluate" className="min-w-0 space-y-3 self-start card p-4">
          <label className="block text-sm">
            Question set
            <select className="mt-1 field" value={questions}
              onChange={(e) => setQuestions(e.target.value as QuestionSet)}>
              {QUESTION_SETS.map((set) => <option key={set.value} value={set.value}>{set.label}</option>)}
            </select>
          </label>
          {questions === 'heldout' && <p className="text-sm text-muted">Held-out questions confirm a final choice. Do not use them to tune.</p>}
          <div className="flex gap-2">
            <button type="button" className="btn text-sm" disabled={busy || problem !== null}
              onClick={() => void estimate()}>Estimate</button>
            <button type="button" className="btn-primary text-sm" disabled={busy || estimates === null || over}
              onClick={() => void evaluate()}>Evaluate</button>
          </div>
          {problem && <p className="text-sm text-muted">{problem}</p>}
          {estimates && <p className="text-sm">{estimateLine(estimates)}</p>}
          {over && <p role="alert" className="text-sm text-danger">Only ${estimates[0].budget_left_usd.toFixed(4)} of the budget is left.</p>}
          {!estimates && !problem && <p className="text-sm text-muted">Press Estimate to see the cost and the time.</p>}
          {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
        </section>
      </div>
      {runsError && <p role="alert" className="text-sm text-danger">{runsError}</p>}
      <RunsPanel runs={runs} base={current} openId={openId} onOpen={setOpenId} onOpenQuestion={openQuestion} />
    </div>
  )
}
