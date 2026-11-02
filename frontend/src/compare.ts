/** Pure logic of the Compare page (T57). */

import type { Comparison, PairedChange, RunReport, RunScores, RunSummary } from './api/types.ts'
import { HEADLINE, OTHER, questionsLine, TRUST, type Metric } from './evaluate.ts'
import { settingsLine } from './panel.ts'

type Side = Pick<RunSummary, 'stack' | 'settings'>
export type ScoreRow = { label: string; before: number; after: number }
export type TableRow = ScoreRow & { digits: number; lowerIsBetter: boolean }

const JUDGE_SCALE = new Set<keyof RunScores>(['accuracy', 'completeness', 'relevance', 'faithfulness'])
const ALL_METRICS: Metric[] = [...HEADLINE, ...OTHER, ...TRUST]

/** Compare takes finished runs that asked their whole question set: the API refuses the others. */
export function comparable(runs: RunSummary[]): RunSummary[] {
  return runs.filter((run) => run.status === 'done' && run.full)
}

/** The runs a first choice can be compared with: the same question set, and not itself. */
export function partners(runs: RunSummary[], before: number | null): RunSummary[] {
  const first = comparable(runs).find((run) => run.id === before)
  return first ? comparable(runs).filter((run) => run.split === first.split && run.id !== first.id) : []
}

export function runChoice(run: RunSummary): string {
  const { chunk_size, overlap, top_k } = run.settings
  return `Run ${run.id}, Stack ${run.stack}, ${questionsLine(run)}, ${chunk_size} tokens, overlap ${overlap}, K=${top_k}, ${run.created_at.slice(0, 10)}`
}

/** A run's stored settings in one line; each stack states its own search settings (T12, T40). */
export function runLine({ stack, settings }: Side): string {
  const { chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, openai_ranking, hybrid } = settings
  const search = stack === 'A' ? { openai_ranking: openai_ranking! } : { hybrid }
  return settingsLine({ stack, chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, ...search })
}

/** What a run states wherever its scores go (T12, T14). */
export function runStatement(name: string, report: RunReport): string {
  const label = report.settings.temperature_controlled ? '' : ' Temperature not controlled.'
  return `${name}: run ${report.id}, ${runLine(report)}.${label}`
}

function rows(comparison: Comparison, metrics: Metric[]): ScoreRow[] {
  return metrics.map(({ key, label }) => ({ label, before: comparison.before.scores[key], after: comparison.after.scores[key] }))
}

/** Scores on the judge's 1 to 5 scale. Two scales never share an axis. */
export function judgeRows(comparison: Comparison): ScoreRow[] {
  return rows(comparison, ALL_METRICS.filter(({ key }) => JUDGE_SCALE.has(key)))
}

/** Search scores and refusal rates, which run from 0 to 1. */
export function rateRows(comparison: Comparison): ScoreRow[] {
  return rows(comparison, ALL_METRICS.filter(({ key }) => !JUDGE_SCALE.has(key)))
}

/** Every number side by side, the table twin of the charts. */
export function tableRows(comparison: Comparison): TableRow[] {
  const { before, after } = comparison
  const scores = rows(comparison, ALL_METRICS).map((row, index) =>
    ({ ...row, digits: 3, lowerIsBetter: ALL_METRICS[index].key === 'false_refusal_rate' }))
  return [...scores,
    { label: 'Cost per question ($)', before: before.cost_per_question, after: after.cost_per_question, digits: 4, lowerIsBetter: true },
    { label: 'Seconds per answer', before: before.latency_s, after: after.latency_s, digits: 1, lowerIsBetter: true }]
}

/** A change with its sign; one that rounds to nothing has none, either way. */
export function signed(value: number, digits: number): string {
  const rounded = Number(value.toFixed(digits))
  const text = rounded.toFixed(digits)
  return rounded > 0 ? `+${text}` : text
}

/** The paired change as read on the page: the mean change, with its interval. */
export function changeLine(before: number, after: number, change: PairedChange): string {
  return `${before.toFixed(3)} to ${after.toFixed(3)}, ${signed(after - before, 3)} (95% interval ${signed(change.low, 3)} to ${signed(change.high, 3)})`
}

/** Search scores count K results, so a different K changes what they measure. */
export function depthNote(comparison: Comparison): string | null {
  const [low, high] = [comparison.before.settings.top_k, comparison.after.settings.top_k]
  return low === high ? null : `The runs read different numbers of results (K=${low} and K=${high}), so their search scores are not measured at the same depth.`
}

/** Where the picture of the chart goes, it says what it compares. */
export function chartLegend(comparison: Comparison) {
  return [
    { text: runStatement('Before', comparison.before), swatch: '--color-before' },
    { text: runStatement('After', comparison.after), swatch: '--color-after' },
  ]
}
