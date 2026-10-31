/** Pure logic of the Story page: what the charts and tables show from the API's ladder state. */

import type { Config, Heldout, Job, LadderState, Option, Step } from './api/types.ts'

export type Metric = 'accuracy' | 'mrr'
export type ChartRow = { step: string; A: number | null; B: number | null }

export const STEPS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']

/** What a job is doing now. One job runs at a time, so a queued one is waiting, not preparing. */
export function jobLine(job: Job): string {
  if (job.status === 'queued') return 'Waiting for the step already running to finish'
  return `${job.message} (${Math.round(job.progress * 100)}%)`
}

export function keptOption(step: Step): Option | undefined {
  return step.tried.find((option) => option.kept)
}

function scoreAt(state: LadderState | null, name: string, metric: Metric): number | null {
  const step = state?.steps.find((s) => s.step === name)
  const option = step && keptOption(step)
  return option ? option[metric] : null
}

/** One row per ladder step, with each stack's kept score; a step not reached yet is null, so the line stops there. */
export function chartRows(a: LadderState | null, b: LadderState | null, metric: Metric): ChartRow[] {
  return STEPS.map((step) => ({ step, A: scoreAt(a, step, metric), B: scoreAt(b, step, metric) }))
}

/** S7 is only reported (T50): the stronger model against the configuration kept, as a cost trade-off. */
export function tradeOff(step: Step): { accuracy: number; costTimes: number } | null {
  const [kept, stronger] = step.tried
  if (step.step !== 'S7' || !stronger) return null
  return { accuracy: stronger.accuracy - kept.accuracy, costTimes: stronger.cost_per_question / kept.cost_per_question }
}

/** The last step, which holds the stack's final choice, once the ladder is finished. */
export function finalStep(state: LadderState): Step | undefined {
  return state.next_step === null ? state.steps.at(-1) : undefined
}

export function describe(config: Config): string {
  return [`${config.chunk_size} tokens`, `overlap ${config.overlap}`, `K=${config.top_k}`, config.method,
    config.rerank ? 'reranked' : 'no rerank', config.answer_model, `prompt ${config.prompt_name}`].join(', ')
}

/** S6 still waits for its final choice of prompt versions. */
export function choosingPrompts(state: LadderState): boolean {
  return state.next_step === 'S6' && state.saved_prompts === null
}

/** While choosing, what is typed differs from what the shown estimate covers: Run must wait for Estimate. */
export function estimateIsStale(state: LadderState, typed: string, estimated: string): boolean {
  return choosingPrompts(state) && promptList(typed).join() !== promptList(estimated).join()
}

/** A held-out run's name. If the ladder kept S0's settings, the one run is both. */
export function heldoutLabel(run: Option, heldout: Heldout): string {
  if (!run.kept) return 'S0'
  return heldout.runs.length === 1 && heldout.missing.length === 0 ? 'S0 and final' : 'Final'
}

export function money(usd: number): string {
  return `$${usd.toFixed(usd < 1 ? 4 : 2)}`
}

export function promptList(text: string): string[] {
  return text.split(',').map((name) => name.trim()).filter(Boolean)
}
