import { useEffect, useState, type ReactNode } from 'react'
import { estimateBuild, getPanel, startBuild } from '../api/client.ts'
import type { BuildJob, BuiltSet, PanelOptions } from '../api/types.ts'
import { useBuilds } from '../api/useBuilds.ts'
import { buildProblem, estimateFor, estimateLine, jobLine, jobTone, overBudget, settingsOf, startValues, toBuild, type BuildValues, type Estimated, type Tone } from '../build.ts'
import Guide from '../components/Guide.tsx'
import PageTitle from '../components/PageTitle.tsx'
import type { StackChoice } from '../panel.ts'

const BOX = 'mt-1 field'
const STEPS = [
  'Choose the stacks, the chunking method, the chunk size and the overlap.',
  'Press Estimate: it shows the chunk set, its number of chunks, the stacks that already have it, and the cost.',
  'Press Embed to build it on the stacks that do not have it yet. Each build is listed below: green once stored, red with the reason if it failed.',
]
const TONE_TEXT: Record<Tone, string> = { good: 'text-good', bad: 'text-danger', working: 'text-muted' }

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-sm">{label}{children}</label>
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <Field label={label}>
      <input type="number" className={BOX} value={Number.isNaN(value) ? '' : value} onChange={(e) => onChange(e.target.valueAsNumber)} />
    </Field>
  )
}

function Jobs({ jobs }: { jobs: BuildJob[] }) {
  return (
    <section aria-label="Builds" className="min-w-0 space-y-2 card p-4">
      <h2 className="font-semibold">Builds</h2>
      {jobs.length === 0 && <p className="text-sm text-muted">No build from this page yet.</p>}
      <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">
        {jobs.map((job) => (
          <li key={job.id} role={job.status === 'failed' ? 'alert' : undefined} className={`[overflow-wrap:anywhere] ${TONE_TEXT[jobTone(job)]}`}>
            {job.created_at.slice(0, 16)} UTC, {jobLine(job)}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Built({ built }: { built: BuiltSet[] }) {
  return (
    <section className="min-w-0 overflow-x-auto card p-4">
      <table className="w-full text-left text-sm tabular-nums">
        <caption className="mb-1 text-left font-semibold">Built chunk sets</caption>
        <thead className="text-muted">
          <tr><th className="pr-3 font-normal">Stack</th><th className="pr-3 font-normal">Method</th><th className="pr-3 font-normal">Size</th><th className="pr-3 font-normal">Overlap</th><th className="pr-3 font-normal">Chunks</th><th className="font-normal">Built on</th></tr>
        </thead>
        <tbody>
          {built.map((row) => (
            <tr key={`${row.stack}-${row.chunk_set_id}`} className="border-t border-line">
              <td className="pr-3">{row.stack}</td><td className="pr-3">{row.chunking_method}</td><td className="pr-3">{row.chunk_size}</td>
              <td className="pr-3">{row.overlap}</td><td className="pr-3">{row.chunk_count}</td><td className="whitespace-nowrap">{row.created_at.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {built.length === 0 && <p className="text-sm text-muted">Nothing built yet.</p>}
    </section>
  )
}

/** Prepares chunks on a stack (D29): Estimate, then Embed, then follow the build below. */
export default function Build() {
  const [options, setOptions] = useState<PanelOptions | null>(null)
  const [values, setValues] = useState<BuildValues | null>(null)
  const [estimated, setEstimated] = useState<Estimated | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { builds, error: buildsError, reload } = useBuilds()

  useEffect(() => {
    getPanel().then((panel) => { setOptions(panel); setValues(startValues(panel)) }).catch((e: Error) => setError(e.message))
  }, [])

  if (options === null || values === null || builds === null) return <p className="text-sm text-muted">{error ?? buildsError ?? 'Loading...'}</p>

  const current = values
  const change = (part: Partial<BuildValues>) => setValues({ ...current, ...part })
  const problem = buildProblem(current, options)
  const estimate = estimateFor(estimated, current)
  const missing = estimate ? toBuild(estimate, current.stacks) : []
  const over = estimate !== null && overBudget(estimate)

  async function runEstimate() {
    setBusy(true)
    setError(null)
    try {
      setEstimated({ values: current, estimate: await estimateBuild(settingsOf(current)) })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function embed() {
    setBusy(true)
    setError(null)
    const refused: string[] = []
    for (const stack of missing) {
      try {
        await startBuild(settingsOf(current), stack)
      } catch (e) {
        refused.push(`Stack ${stack}: ${(e as Error).message}`)
      }
    }
    setError(refused.length ? refused.join(' ') : null)
    setEstimated(null)
    setBusy(false)
    await reload()
  }

  return (
    <div className="space-y-5">
      <PageTitle title="Build" about="Cut the documents into chunks and store them on a stack." />
      <Guide page="Build" steps={STEPS}
        purpose="Before a set-up can be asked or evaluated, its chunks must exist on the stack: the 48 documents cut into passages of the chosen size, turned into vectors and stored."
        note="Fixed chunks are free. LLM-enriched chunks pay once for a headline and summary of every chunk, shared by both stacks. Stack B builds on this computer and needs Qdrant running. The settings box on Ask, Evaluate and Sweep also offers to build missing chunks." />
      <section aria-label="Build" className="min-w-0 space-y-3 card p-4 md:max-w-xl">
        <h2 className="font-semibold">Prepare chunks</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Stack">
            <select className={BOX} value={current.stacks} onChange={(e) => change({ stacks: e.target.value as StackChoice })}>
              <option value="both">Both</option>
              <option value="A">Stack A</option>
              <option value="B">Stack B</option>
            </select>
          </Field>
          <Field label="Chunking method">
            <select className={BOX} value={current.chunking_method} onChange={(e) => change({ chunking_method: e.target.value as BuildValues['chunking_method'] })}>
              <option value="fixed">fixed</option>
              <option value="llm_enriched">llm_enriched</option>
            </select>
          </Field>
          <NumberField label={`Chunk size (${options.min_chunk_size} to ${options.max_chunk_size})`} value={current.chunk_size} onChange={(chunk_size) => change({ chunk_size })} />
          <NumberField label="Overlap (tokens)" value={current.overlap} onChange={(overlap) => change({ overlap })} />
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn text-sm" disabled={busy || problem !== null}
            onClick={() => void runEstimate()}>Estimate</button>
          <button type="button" className="btn-primary text-sm"
            disabled={busy || missing.length === 0 || over} onClick={() => void embed()}>Embed</button>
        </div>
        {problem && <p className="text-sm text-muted">{problem}</p>}
        {estimate && <p className="text-sm [overflow-wrap:anywhere]">{estimateLine(estimate, current)}</p>}
        {over && <p role="alert" className="text-sm text-danger">Only ${estimate.budget_left_usd.toFixed(4)} of the budget is left.</p>}
        {!estimate && !problem && <p className="text-sm text-muted">Press Estimate to see the chunks and the cost.</p>}
        {current.stacks !== 'B' && <p className="text-xs text-muted">Stack A uploads each chunk to OpenAI; its storage fee is not counted in the budget.</p>}
        {error && <p role="alert" className="text-sm text-danger [overflow-wrap:anywhere]">{error}</p>}
      </section>
      {buildsError && <p role="alert" className="text-sm text-danger">{buildsError}</p>}
      <Jobs jobs={builds.jobs} />
      <Built built={builds.built} />
    </div>
  )
}
