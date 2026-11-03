import { useState } from 'react'
import { estimateBuild, startBuild } from '../api/client.ts'
import type { PanelOptions } from '../api/types.ts'
import { useBuilds } from '../api/useBuilds.ts'
import { buildValuesOf, estimateFor, estimateLine, jobLine, jobTone, missingStacks, notBuilding, offerJobs, overBudget, settingsOf, toBuild, type Estimated, type Tone } from '../build.ts'
import { chunkProblem, type PanelValues } from '../panel.ts'

const TONE_TEXT: Record<Tone, string> = { good: 'text-good', bad: 'text-danger', working: 'text-muted' }

/** The panel's offer (D29): when the chosen stacks lack these chunks, show what building them costs, and build them
 * only after a click. It lists the builds it started, and any build of these chunks still waiting or running. */
export default function BuildOffer({ values, options }: { values: PanelValues; options: PanelOptions }) {
  const { builds, reload } = useBuilds()
  const [estimated, setEstimated] = useState<Estimated | null>(null)
  const [started, setStarted] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (builds === null || chunkProblem(values, options)) return null
  const wanted = buildValuesOf(values)
  const missing = missingStacks(builds.built, wanted)
  const mine = offerJobs(builds.jobs, wanted, started)
  if (missing.length === 0 && mine.length === 0) return null

  const estimate = estimateFor(estimated, wanted)
  const stacks = estimate ? notBuilding(toBuild(estimate, wanted.stacks), mine) : []

  async function runEstimate() {
    setBusy(true)
    setError(null)
    try {
      setEstimated({ values: wanted, estimate: await estimateBuild(settingsOf(wanted)) })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function build() {
    setBusy(true)
    setError(null)
    const refused: string[] = []
    const ids: number[] = []
    for (const stack of stacks) {
      try {
        ids.push(await startBuild(settingsOf(wanted), stack))
      } catch (e) {
        refused.push(`Stack ${stack}: ${(e as Error).message}`)
      }
    }
    setStarted((before) => [...before, ...ids])
    setError(refused.length ? refused.join(' ') : null)
    setEstimated(null)
    setBusy(false)
    await reload()
  }

  return (
    <div role="region" aria-label="Build these chunks" className="space-y-2 border-t border-line pt-3 text-sm">
      {missing.length > 0 && <p>These chunks are not built on {missing.map((stack) => `Stack ${stack}`).join(' and ')} yet, so the {missing.length > 1 ? 'stacks' : 'stack'} cannot answer.</p>}
      {missing.length > 0 && (
        <div className="flex gap-2">
          <button type="button" className="btn" disabled={busy} onClick={() => void runEstimate()}>Estimate the build</button>
          <button type="button" className="btn-primary"
            disabled={busy || stacks.length === 0 || (estimate !== null && overBudget(estimate))} onClick={() => void build()}>Build them</button>
        </div>
      )}
      {estimate && <p className="[overflow-wrap:anywhere]">{estimateLine(estimate, wanted, stacks)}</p>}
      {estimate && overBudget(estimate) && <p role="alert" className="text-danger">Only ${estimate.budget_left_usd.toFixed(4)} of the budget is left.</p>}
      {mine.map((job) => (
        <p key={job.id} role={job.status === 'failed' ? 'alert' : undefined} className={`[overflow-wrap:anywhere] ${TONE_TEXT[jobTone(job)]}`}>{jobLine(job)}</p>
      ))}
      {error && <p role="alert" className="text-danger [overflow-wrap:anywhere]">{error}</p>}
    </div>
  )
}
