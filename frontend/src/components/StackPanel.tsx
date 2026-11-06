import { useEffect, useState } from 'react'
import { useReadOnly } from '../readOnly.ts'
import { getLadder, getPrompts, startHeldout, startStep } from '../api/client.ts'
import type { StackId } from '../api/types.ts'
import type { useLadder } from '../api/useLadder.ts'
import { hashOf } from '../route.ts'
import { bestSoFar, choosingPrompts, describe, estimateIsStale, finalStep, jobLine, MAX_S6_PROMPTS, money, promptList, s6Choices, stepsCsv, togglePrompt } from '../story.ts'
import HeldoutPanel from './HeldoutPanel.tsx'
import StepsTable from './StepsTable.tsx'

const SEARCH: Record<StackId, string> = {
  A: 'OpenAI default search (ranker auto)',
  B: 'plain vector search',
}

function downloadCsv(stack: StackId, text: string) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  link.download = `stack-${stack}-options.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

/** S6's choice: tick at most 4 saved prompt versions besides default; none ticked skips S6. */
function PromptPicks({ saved, picked, onChange }: { saved: string[]; picked: string[]; onChange: (picked: string[]) => void }) {
  return (
    <fieldset className="mb-2 space-y-1">
      <legend className="mb-1">Prompt versions to try at S6, besides default (at most {MAX_S6_PROMPTS}; none skips S6)</legend>
      {saved.length === 0 && <p className="text-muted">No version saved yet besides default. Write some on <a className="text-accent-text underline" href={hashOf('Prompt')}>Prompt</a> first, or skip S6.</p>}
      {saved.map((name) => (
        <label key={name} className="flex items-center gap-2">
          <input type="checkbox" checked={picked.includes(name)} disabled={!picked.includes(name) && picked.length >= MAX_S6_PROMPTS}
            onChange={() => onChange(togglePrompt(picked, name, saved))} />{name}
        </label>
      ))}
    </fieldset>
  )
}

/** One stack: its next step with the estimate, the running job, its results and its held-out panel. */
export default function StackPanel({ stack, ladder }: { stack: StackId; ladder: ReturnType<typeof useLadder> }) {
  const readOnly = useReadOnly()
  const { state, job, running, error, setError, follow, setState } = ladder
  const [picked, setPicked] = useState<string[]>([])
  const [saved, setSaved] = useState<string[]>([])
  const prompts = picked.join(',')
  const [estimated, setEstimated] = useState('')
  const [starting, setStarting] = useState(false)
  const busy = running || starting
  const choosing = state !== null && choosingPrompts(state)

  useEffect(() => {
    if (choosing) getPrompts().then((versions) => setSaved(s6Choices(versions.map((v) => v.name)))).catch((e: Error) => setError(e.message))
  }, [choosing, setError])

  async function start(run: () => Promise<number>) {
    setStarting(true)
    try {
      setError(null)
      follow(await run())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  async function preview() {
    try {
      setState(await getLadder(stack, promptList(prompts)))
      setEstimated(prompts)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function runStep() {
    if (!state) return
    const choosing = choosingPrompts(state)
    if (state.enrichment_usd > 0 && !confirm(`This step pays ${money(state.enrichment_usd)} to enrich chunks. Continue?`)) return
    if (choosing && !confirm('The prompt versions for S6 are final for this stack. Continue?')) return
    void start(() => startStep(stack, choosing ? promptList(prompts) : undefined))
  }

  const final = state && finalStep(state)
  const best = state && bestSoFar(state)
  return (
    <section aria-label={`Stack ${stack}`} className="min-w-0 card p-4">
      <h2 className="font-semibold">Stack {stack}</h2>
      <p className="mb-3 text-sm text-muted">{SEARCH[stack]}</p>
      {state === null && !error && <p className="text-sm text-muted">Loading...</p>}
      {state && (
        <>
          {state.next_step === null
            ? <p className="text-sm">Ladder finished.</p>
            : (
              <div className="text-sm">
                {choosingPrompts(state) && (
                  <>
                    <PromptPicks saved={saved} picked={picked} onChange={setPicked} />
                    <button type="button" className="btn mb-2" onClick={() => void preview()}>Estimate</button>
                  </>
                )}
                <button type="button" className="btn-primary"
                  disabled={busy || estimateIsStale(state, prompts, estimated) || readOnly} onClick={runStep}>
                  {state.missing.length === 0
                    ? 'Skip S6'
                    : `Run ${state.next_step} (${state.missing.length} ${state.missing.length === 1 ? 'run' : 'runs'}, about ${money(state.estimate_usd)})`}
                </button>
                <p className="mt-1 text-muted">
                  {state.enrichment_usd > 0 && `Includes ${money(state.enrichment_usd)} of enrichment. `}
                  {money(state.budget_left_usd)} of the budget left. Includes Stack A's search fee; OpenAI's index building is not counted.
                </p>
              </div>
            )}
          {running && (
            <div role="status" className="mt-2 text-sm">
              <p>{job ? jobLine(job) : 'Starting...'}</p>
              <progress className="mt-1 w-full accent-accent" aria-label="Step progress" max={1}
                value={job && job.status !== 'queued' && job.progress > 0 ? job.progress : undefined} />
            </div>
          )}
          {state.last_error && !running && <p role="alert" className="mt-2 text-sm text-danger">Last step failed: {state.last_error}</p>}
          {best && (
            <p className="mt-3 rounded border-2 border-accent p-2 text-sm">
              <span className="font-medium">{final ? 'Best eligible configuration:' : `Best so far (after ${best.step}):`}</span>{' '}
              {describe(best.option.config)}. Accuracy {best.option.accuracy.toFixed(3)}, MRR {best.option.mrr.toFixed(3)},
              {' '}${best.option.cost_per_question.toFixed(5)} per question, run {best.option.run_id}.
            </p>
          )}
          {state.steps.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm">Every option tried</summary>
              <button type="button" className="mt-2 btn text-sm"
                onClick={() => downloadCsv(stack, stepsCsv(state))}>Download CSV</button>
              <div className="mt-2 overflow-x-auto"><StepsTable steps={state.steps} /></div>
            </details>
          )}
          <div className="mt-3">
            <HeldoutPanel heldout={state.heldout} busy={busy || readOnly} onRun={() => void start(() => startHeldout(stack))} />
          </div>
        </>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </section>
  )
}
