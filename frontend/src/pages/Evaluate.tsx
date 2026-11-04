import { useState } from 'react'
import { estimateRun, startRun } from '../api/client.ts'
import type { QuestionSet, RunSummary } from '../api/types.ts'
import { useBuilds } from '../api/useBuilds.ts'
import { usePanel } from '../api/usePanel.ts'
import { useRuns } from '../api/useRuns.ts'
import Guide from '../components/Guide.tsx'
import PageTitle from '../components/PageTitle.tsx'
import RunsPanel, { ShownRun } from '../components/RunsPanel.tsx'
import SettingsPanel from '../components/SettingsPanel.tsx'
import { askLink, estimateFor, estimateLine, linkedRunId, overBudget, questionSetOf, runOfJobs, shownRun, valuesOfRun, type Estimated } from '../evaluate.ts'
import { chunksProblem } from '../chunks.ts'
import { panelProblem, requestFor, saveValues, stacksOf } from '../panel.ts'
import { linkedParam } from '../route.ts'

const QUESTION_SETS: { value: QuestionSet; label: string }[] = [
  { value: 'dev', label: 'Dev (192 questions)' },
  { value: 'smoke', label: 'Smoke test (20 questions)' },
  { value: 'heldout', label: 'Held-out (48 questions)' },
]

const STEPS = [
  'Choose the settings in the Settings box: the stack, how the documents are cut into chunks, how many chunks to search (top-K), the answer model and the prompt.',
  'Choose the question set: the smoke test (20 questions) checks that a set-up works; dev (192) measures it.',
  'Press Estimate to see the cost and the time. Nothing is spent yet.',
  'Press Evaluate to start. The new run opens below the table of runs, with its progress, then its report and every answer.',
  'To read an older run, press Open on its row in the table.',
]

/** Scores one configuration on many questions (T56): Estimate, then Evaluate; the run opens at once and shows its report when done.
A link can choose the prompt version, the question set and the run to show. */
export default function Evaluate() {
  const { options, promptNames, values, setValues, error: panelError } = usePanel(linkedParam(location.hash, 'prompt'))
  const { builds } = useBuilds()
  const { runs, error: runsError, reload } = useRuns()
  const [questions, setQuestions] = useState<QuestionSet>(() => questionSetOf(linkedParam(location.hash, 'questions')))
  const [estimated, setEstimated] = useState<Estimated | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<number | null>(() => linkedRunId(linkedParam(location.hash, 'run')))

  if (panelError) return <p role="alert" className="text-sm text-danger">{panelError}</p>
  if (options === null || values === null || runs === null) return <p className="text-sm text-muted">{runsError ?? 'Loading...'}</p>

  const current = values
  const problem = panelProblem(current, options) ?? chunksProblem(builds?.built ?? null, current)
  const estimates = estimateFor(estimated, current, questions)
  const shownId = shownRun(runs, openId)
  const shown = runs.find((run) => run.id === shownId)

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
    const jobIds: number[] = []
    try {
      for (const stack of stacksOf(current.stacks)) jobIds.push(await startRun(requestFor(current, stack), questions))
    } catch (e) {
      setError((e as Error).message)
    }
    setEstimated(null)
    setBusy(false)
    const fresh = await reload()
    if (fresh) setOpenId(runOfJobs(fresh, jobIds) ?? openId)
  }

  function openQuestion(run: RunSummary, testId: string) {
    saveValues(valuesOfRun(run, current))
    location.hash = askLink(testId)
  }

  const over = estimates !== null && overBudget(estimates)
  return (
    <div className="space-y-5">
      <PageTitle title="Evaluate" about="Score one set-up on many test questions, with a report you can trust." />
      <Guide page="Evaluate" steps={STEPS}
        purpose="Each test question is searched, answered by the answer model and graded by a separate judge model against its reference answer."
        note="Held-out questions are kept for confirming a final choice: do not use them to tune settings." />
      <div className="grid gap-5 md:grid-cols-[22rem_minmax(0,1fr)]">
        <SettingsPanel values={current} options={options} promptNames={promptNames} built={builds?.built ?? null} onChange={setValues} />
        <div className="min-w-0 space-y-5">
          <section aria-label="Start a run" className="space-y-3 card p-5">
            <h2 className="font-semibold">Start a run</h2>
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
                onClick={() => void estimate()}>1. Estimate</button>
              <button type="button" className="btn-primary text-sm" disabled={busy || estimates === null || over}
                onClick={() => void evaluate()}>2. Evaluate</button>
            </div>
            {problem && <p className="text-sm text-muted">{problem}</p>}
            {estimates && <p className="text-sm">{estimateLine(estimates)}</p>}
            {over && <p role="alert" className="text-sm text-danger">Only ${estimates[0].budget_left_usd.toFixed(4)} of the budget is left.</p>}
            {!estimates && !problem && <p className="text-sm text-muted">Evaluate turns on once you press Estimate, which shows the cost and the time.</p>}
            {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
          </section>
          {runsError && <p role="alert" className="text-sm text-danger">{runsError}</p>}
          <RunsPanel runs={runs} openId={shownId} onOpen={setOpenId} />
          {shown && <ShownRun key={shown.id} run={shown} base={current} onOpenQuestion={openQuestion} />}
        </div>
      </div>
    </div>
  )
}
