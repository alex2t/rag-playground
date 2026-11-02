/** Pure logic of the Build page (D29). */

import type { BuildEstimate, BuildJob, BuildSettings, PanelOptions, StackId } from './api/types.ts'
import { chunkProblem, stacksOf, type StackChoice } from './panel.ts'

export type BuildValues = BuildSettings & { stacks: StackChoice }
export type Estimated = { values: BuildValues; estimate: BuildEstimate }
export type Tone = 'good' | 'bad' | 'working'

export function startValues(options: PanelOptions): BuildValues {
  const { chunking_method, chunk_size, overlap } = options.start
  return { chunking_method, chunk_size, overlap, stacks: 'both' }
}

export function buildProblem(values: BuildValues, options: PanelOptions): string | null {
  return chunkProblem(values, options)
}

export function settingsOf({ chunking_method, chunk_size, overlap }: BuildValues): BuildSettings {
  return { chunking_method, chunk_size, overlap }
}

/** An estimate counts only for exactly what it was made for, so a slow reply cannot stand for changed settings. */
export function estimateFor(estimated: Estimated | null, values: BuildValues): BuildEstimate | null {
  return estimated && JSON.stringify(estimated.values) === JSON.stringify(values) ? estimated.estimate : null
}

/** The chosen stacks that do not have the chunk set yet. */
export function toBuild(estimate: BuildEstimate, stacks: StackChoice): StackId[] {
  return stacksOf(stacks).filter((stack) => !estimate.built.includes(stack))
}

/** Enrichment that still costs something and does not fit in what is left. A free build is never over budget. */
export function overBudget(estimate: BuildEstimate): boolean {
  return estimate.enrichment_usd > 0 && estimate.enrichment_usd > estimate.budget_left_usd
}

function costLine(method: BuildSettings['chunking_method'], usd: number): string {
  if (method === 'fixed') return 'No paid call.'
  return usd > 0 ? `Enrichment about $${usd.toFixed(4)}, paid once for both stacks.` : 'Already enriched: nothing to pay.'
}

/** What pressing Embed would do: which set, how many chunks, which stacks, and what it costs. */
export function estimateLine(estimate: BuildEstimate, values: BuildValues): string {
  const missing = toBuild(estimate, values.stacks)
  const have = stacksOf(values.stacks).filter((stack) => estimate.built.includes(stack))
  const parts = [`${estimate.chunk_set_id}: ${estimate.chunks} chunks.`]
  if (have.length) parts.push(`Already built on ${have.map((stack) => `Stack ${stack}`).join(' and ')}.`)
  if (!missing.length) return [...parts, 'Nothing to build.'].join(' ')
  return [...parts, `To build on ${missing.map((stack) => `Stack ${stack}`).join(' and ')}.`, costLine(values.chunking_method, estimate.enrichment_usd)].join(' ')
}

const JOB_WORDS: Record<BuildJob['status'], string> = { queued: 'waiting for the job before it', running: 'building', done: 'built', failed: 'failed' }

export function jobLine(job: BuildJob): string {
  const line = `${job.chunk_set_id} on Stack ${job.stack}: ${JOB_WORDS[job.status]}`
  return job.error ? `${line}. ${job.error}` : line
}

export function jobTone(job: BuildJob): Tone {
  return job.status === 'done' ? 'good' : job.status === 'failed' ? 'bad' : 'working'
}

export function isWorking(jobs: BuildJob[]): boolean {
  return jobs.some((job) => job.status === 'queued' || job.status === 'running')
}
