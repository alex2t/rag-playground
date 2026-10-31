/** Pure logic of the Story page: what the charts and tables show from the API's ladder state. */

import type { Change, Config, Heldout, Job, LadderState, Option, Step } from './api/types.ts'

export type Metric = 'accuracy' | 'mrr'
type Bar = [number, number] | null
export type ChartRow = { step: string; A: number | null; B: number | null; A_bar: Bar; B_bar: Bar; A_mark: string; B_mark: string }

export const STEPS = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']

/** What a job is doing now. One job runs at a time, so a queued one is waiting, not preparing. */
export function jobLine(job: Job): string {
  if (job.status === 'queued') return 'Waiting for the step already running to finish'
  return `${job.message} (${Math.round(job.progress * 100)}%)`
}

export function keptOption(step: Step): Option | undefined {
  return step.tried.find((option) => option.kept)
}

/** '+' for a real rise from the step before, '-' for a real fall, nothing when the interval contains 0 (T52). */
export function changeMark(change: Change | undefined): string {
  if (!change) return ''
  if (change.low > 0) return '+'
  return change.high < 0 ? '-' : ''
}

function pointAt(state: LadderState | null, name: string, metric: Metric) {
  const step = state?.steps.find((s) => s.step === name)
  const option = step && keptOption(step)
  if (!option) return { score: null, bar: null, mark: '' }
  const [low, high] = option[`${metric}_ci`]
  const score = option[metric]
  return { score, bar: [score - low, high - score] as Bar, mark: changeMark(step.change?.[metric]) }
}

/** One row per ladder step, with each stack's kept score, the distance to its interval's ends for the error bar, and
 * its change mark; a step not reached yet is null, so the line stops there. */
export function chartRows(a: LadderState | null, b: LadderState | null, metric: Metric): ChartRow[] {
  return STEPS.map((step) => {
    const [pa, pb] = [pointAt(a, step, metric), pointAt(b, step, metric)]
    return { step, A: pa.score, B: pb.score, A_bar: pa.bar, B_bar: pb.bar, A_mark: pa.mark, B_mark: pb.mark }
  })
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

/** The configuration the ladder holds now: what the latest step kept, with its scores. */
export function bestSoFar(state: LadderState): { step: string; option: Option } | null {
  const step = state.steps.at(-1)
  const option = step && keptOption(step)
  return step && option ? { step: step.step, option } : null
}

function csvCell(value: string | number | boolean): string {
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

const CSV_HEADER = ['stack', 'step', 'chunk_size', 'overlap', 'top_k', 'method', 'rerank', 'answer_model', 'prompt', 'run',
  'accuracy', 'accuracy_low', 'accuracy_high', 'mrr', 'mrr_low', 'mrr_high', 'cost_per_question', 'kept', 'failed_gates']

/** Every option tried, one row each, as the table shows it but with full precision. The byte order mark tells Excel
 * the file is UTF-8, so a prompt name with accents stays readable. */
export function stepsCsv(state: LadderState): string {
  const rows = state.steps.flatMap((step) => step.tried.map(({ config, ...option }) => [state.stack, step.step, config.chunk_size,
    config.overlap, config.top_k, config.method, config.rerank, config.answer_model, config.prompt_name, option.run_id,
    option.accuracy, ...option.accuracy_ci, option.mrr, ...option.mrr_ci, option.cost_per_question, option.kept, option.failed_gates.join(' ')]))
  return '\uFEFF' + [CSV_HEADER, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n'
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
