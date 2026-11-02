/** Pure logic of the Sweep page (T58). */

import type { SweepBody } from './api/client.ts'
import type { Job, PanelOptions, StackId, SweepPlan, SweepValue } from './api/types.ts'
import { requestFor, type PanelValues, type StackChoice } from './panel.ts'
import { changeMark, type ChartRow, type Metric } from './story.ts'

type Kind = 'int' | 'float' | 'pick'
export type Variable = { key: string; label: string; kind: Kind; stack?: StackId; ordered: boolean }

export const VARIABLES: Variable[] = [
  { key: 'chunk_size', label: 'Chunk size', kind: 'int', ordered: true },
  { key: 'overlap', label: 'Overlap (tokens)', kind: 'int', ordered: true },
  { key: 'top_k', label: 'Top-K', kind: 'int', ordered: true },
  { key: 'chunking_method', label: 'Chunking method', kind: 'pick', ordered: false },
  { key: 'rerank', label: 'Reranking', kind: 'pick', ordered: false },
  { key: 'answer_model', label: 'Answer model', kind: 'pick', ordered: false },
  { key: 'prompt_name', label: 'System prompt version', kind: 'pick', ordered: false },
  { key: 'hybrid', label: 'Stack B hybrid search', kind: 'pick', stack: 'B', ordered: false },
  { key: 'ranker', label: 'Stack A ranker', kind: 'pick', stack: 'A', ordered: false },
  { key: 'embedding_weight', label: 'Stack A semantic weight', kind: 'float', stack: 'A', ordered: true },
  { key: 'text_weight', label: 'Stack A keyword weight', kind: 'float', stack: 'A', ordered: true },
  { key: 'score_threshold', label: 'Stack A score threshold', kind: 'float', stack: 'A', ordered: true },
]

/** A stack's own setting is swept on that stack alone (T40), so with both stacks only shared settings are offered. */
export function variablesFor(stacks: StackChoice): Variable[] {
  return VARIABLES.filter((variable) => !variable.stack || stacks === variable.stack)
}

export function variableOf(key: string): Variable {
  return VARIABLES.find((variable) => variable.key === key)!
}

/** The values a setting with a known list can take, to tick. */
export function choicesFor(key: string, options: PanelOptions, promptNames: string[]): SweepValue[] {
  const lists: Record<string, SweepValue[]> = {
    chunking_method: ['fixed', 'llm_enriched'], rerank: [false, true], hybrid: [false, true], ranker: ['none', 'auto'],
    answer_model: options.answer_models, prompt_name: promptNames,
  }
  return lists[key]
}

/** Typed numbers, split at commas: whole numbers for sizes, overlap and K. The API checks each value's range. */
export function parseNumbers(kind: Kind, text: string): { values: number[] } | { problem: string } {
  const parts = text.split(',').map((part) => part.trim()).filter(Boolean)
  if (!parts.length) return { problem: 'Type at least one value, separated by commas.' }
  const values = parts.map(Number)
  const bad = parts.find((part, i) => part === '' || !Number.isFinite(values[i]) || (kind === 'int' && !Number.isInteger(values[i])))
  return bad === undefined ? { values } : { problem: `"${bad}" is not ${kind === 'int' ? 'a whole number' : 'a number'}.` }
}

export function valueText(value: SweepValue): string {
  return typeof value === 'boolean' ? (value ? 'on' : 'off') : String(value)
}

export function bodyFor(values: PanelValues, stack: StackId, variable: string, list: SweepValue[]): SweepBody {
  return { base: requestFor(values, stack), variable, values: list }
}

export type Planned = { key: string; plans: SweepPlan[] }

/** What a plan was made for: the panel, the setting and its values. A plan counts only for exactly that. */
export function planKey(values: PanelValues, variable: string, list: SweepValue[]): string {
  return JSON.stringify([values, variable, list])
}

export function plansFor(planned: Planned | null, key: string): SweepPlan[] | null {
  return planned?.key === key ? planned.plans : null
}

/** The values, setting and list a plan key was made from, so polling depends on the key alone. */
export function fromKey(key: string): [PanelValues, string, SweepValue[]] {
  return JSON.parse(key)
}

/** How a stack's latest sweep stands. A queued sweep waits for whatever job is ahead of it. */
export function sweepJobLine(stack: StackId, job: Job): string {
  if (job.status === 'queued') return `Sweep on Stack ${stack}: waiting for the job before it`
  if (job.status === 'running') return `${job.message} (${Math.round(job.progress * 100)}%)`
  return job.status === 'done' ? `The last sweep on Stack ${stack} finished.` : `The last sweep on Stack ${stack} failed: ${job.error}`
}

export type Latest = Partial<Record<StackId, Job | null>>

/** A sweep still waits or runs on one of the stacks. */
export function isWorking(latest: Latest): boolean {
  return Object.values(latest).some((job) => job && (job.status === 'queued' || job.status === 'running'))
}

export function totalCost(plans: SweepPlan[]): number {
  return plans.reduce((sum, plan) => sum + plan.estimate_usd, 0)
}

/** Sweeps queue one after another, and every value is paid from the same budget, so the totals add up. A sweep with
 * nothing to pay is never over the budget, even when spend has passed it. */
export function overBudget(plans: SweepPlan[]): boolean {
  const total = totalCost(plans)
  return total > 0 && total > plans[0].budget_left_usd
}

/** The stacks that still have values to run. */
export function toRun(plans: SweepPlan[]): StackId[] {
  return plans.filter((plan) => plan.runs_to_do > 0).map((plan) => plan.stack)
}

export function planLine(plans: SweepPlan[]): string {
  const parts = plans.map((plan) => plan.runs_to_do
    ? `Stack ${plan.stack}: ${plan.runs_to_do} of ${plan.items.length} values to run, about $${plan.estimate_usd.toFixed(4)}`
    : `Stack ${plan.stack}: every value has a run`)
  const total = totalCost(plans)
  return `${parts.join('; ')}.${total > 0 ? ` Total about $${total.toFixed(4)}.` : ''}`
}

/** The x axis: every value once, numbers in increasing order, other values in the order given, the base marked. A
 * model loses its provider on the axis ("gpt-4.1-nano"), so long names fit; the table shows them whole. */
export function axisValues(plans: SweepPlan[], variable: Variable): { value: SweepValue; label: string }[] {
  const items = plans.flatMap((plan) => plan.items)
  const unique = items.filter((item, i) => items.findIndex((other) => other.value === item.value) === i)
  const sorted = variable.ordered ? [...unique].sort((a, b) => Number(a.value) - Number(b.value)) : unique
  const short = (value: SweepValue) => valueText(value).split('/').at(-1)!
  return sorted.map((item) => ({ value: item.value, label: item.base ? `${short(item.value)} (base)` : short(item.value) }))
}

/** One row per value, as the ladder chart reads them: each stack's score, its interval as distances, and + or - for a
 * real change against the base value (T09). A value not run yet is null, so no point is drawn. */
export function chartRows(plans: SweepPlan[], variable: Variable, metric: Metric): ChartRow[] {
  return axisValues(plans, variable).map(({ value, label }) => {
    const row: ChartRow = { step: label, A: null, B: null, A_bar: null, B_bar: null, A_mark: '', B_mark: '' }
    for (const plan of plans) {
      const run = plan.items.find((item) => item.value === value)?.run
      if (!run) continue
      const [low, high] = run[`${metric}_ci`]
      row[plan.stack] = run[metric]
      row[`${plan.stack}_bar`] = [run[metric] - low, high - run[metric]]
      row[`${plan.stack}_mark`] = changeMark(run.change?.[metric])
    }
    return row
  })
}
