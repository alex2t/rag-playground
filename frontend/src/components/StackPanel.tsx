import { useState } from 'react'
import { getLadder, startHeldout, startStep } from '../api/client.ts'
import type { StackId } from '../api/types.ts'
import type { useLadder } from '../api/useLadder.ts'
import { choosingPrompts, describe, estimateIsStale, finalStep, jobLine, money, promptList } from '../story.ts'
import HeldoutPanel from './HeldoutPanel.tsx'
import StepsTable from './StepsTable.tsx'

const SEARCH: Record<StackId, string> = {
  A: 'OpenAI default search (ranker auto)',
  B: 'plain vector search',
}

/** One stack: its next step with the estimate, the running job, its results and its held-out panel. */
export default function StackPanel({ stack, ladder }: { stack: StackId; ladder: ReturnType<typeof useLadder> }) {
  const { state, job, running, error, setError, follow, setState } = ladder
  const [prompts, setPrompts] = useState('')
  const [estimated, setEstimated] = useState('')
  const [starting, setStarting] = useState(false)
  const busy = running || starting

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
  return (
    <section aria-label={`Stack ${stack}`} className="min-w-0 rounded-lg border border-line bg-panel p-4">
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
                  <label className="mb-2 block">
                    Prompt versions for S6, separated by commas (at most 4; empty skips S6)
                    <span className="mt-1 flex gap-2">
                      <input className="w-full rounded border border-line bg-transparent px-2 py-1" value={prompts}
                        onChange={(e) => setPrompts(e.target.value)} />
                      <button type="button" className="rounded border border-line px-3 py-1" onClick={() => void preview()}>Estimate</button>
                    </span>
                  </label>
                )}
                <button type="button" className="rounded bg-accent px-3 py-1 font-medium text-white disabled:opacity-50"
                  disabled={busy || estimateIsStale(state, prompts, estimated)} onClick={runStep}>
                  {state.missing.length === 0
                    ? 'Skip S6'
                    : `Run ${state.next_step} (${state.missing.length} ${state.missing.length === 1 ? 'run' : 'runs'}, about ${money(state.estimate_usd)})`}
                </button>
                <p className="mt-1 text-muted">
                  {state.enrichment_usd > 0 && `Includes ${money(state.enrichment_usd)} of enrichment. `}
                  {money(state.budget_left_usd)} of the budget left. OpenRouter costs only; OpenAI's are not counted.
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
          {final && (
            <p className="mt-3 rounded border-2 border-accent p-2 text-sm">
              <span className="font-medium">Best eligible configuration:</span> {describe(final.kept)}
            </p>
          )}
          {state.steps.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm">Every option tried</summary>
              <div className="mt-2 overflow-x-auto"><StepsTable steps={state.steps} /></div>
            </details>
          )}
          <div className="mt-3">
            <HeldoutPanel heldout={state.heldout} busy={busy} onRun={() => void start(() => startHeldout(stack))} />
          </div>
        </>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
    </section>
  )
}
