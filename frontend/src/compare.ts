/** Pure logic of the Compare page (T57). */

import type { Comparison, PairedChange, PanelRequest, RunReport, RunScores, RunSummary } from './api/types.ts'
import { HEADLINE, OTHER, TRUST, type Metric } from './evaluate.ts'
import { searchLine, settingsLine } from './panel.ts'

type Side = Pick<RunSummary, 'stack' | 'settings'>
export type ScoreRow = { label: string; before: number; after: number }
export type TableRow = ScoreRow & { key: string; digits: number; lowerIsBetter: boolean }

const JUDGE_SCALE = new Set<keyof RunScores>(['accuracy', 'completeness', 'relevance', 'faithfulness'])
const ALL_METRICS: Metric[] = [...HEADLINE, ...OTHER, ...TRUST]

/** Compare takes finished runs that asked their whole question set: the API refuses the others. */
export function comparable(runs: RunSummary[]): RunSummary[] {
  return runs.filter((run) => run.status === 'done' && run.full)
}

/** A run's stored settings as the request that would repeat it; each stack keeps its own search settings (T40). */
function requestOf({ stack, settings }: Side): PanelRequest {
  const { chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, openai_ranking, hybrid } = settings
  const search = stack === 'A' ? { openai_ranking: openai_ranking! } : { hybrid }
  return { stack, chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, ...search }
}

/** A run's stored settings in one line; each stack states its own search settings (T12, T40). */
export function runLine(side: Side): string {
  return settingsLine(requestOf(side))
}

export type SettingDiff = { label: string; before: string; after: string }

/** Every setting of a run as label and value, in the order the page lists them. */
export function settingFields(side: Side): [string, string][] {
  const request = requestOf(side)
  return [['Stack', request.stack], ['Chunking method', request.chunking_method], ['Chunk size', String(request.chunk_size)],
    ['Overlap', String(request.overlap)], ['Top-K', String(request.top_k)], ['Search', searchLine(request)],
    ['Reranking', request.rerank ? 'on' : 'off'], ['Answer model', request.answer_model], ['Prompt', request.prompt_name]]
}

/** The settings two runs do not share, so the page can say what changed between them. */
export function settingDiffs(before: Side, after: Side): SettingDiff[] {
  const after_ = settingFields(after)
  return settingFields(before)
    .map(([label, value], index) => ({ label, before: value, after: after_[index][1] }))
    .filter((row) => row.before !== row.after)
}

/** How After's cost per question compares with Before's, in whole percent. */
export function costChange(before: number, after: number): string {
  const percent = Math.round((100 * (after - before)) / before)
  if (percent === 0) return 'costs the same per question'
  return `costs ${Math.abs(percent)}% ${percent > 0 ? 'more' : 'less'} per question`
}

function count(questions: number): string {
  return questions === 1 ? '1 question' : `${questions} questions`
}

/** The gates a run fails, by the names the page shows. */
function gateNames(report: RunReport): string {
  return report.failed_gates.map((key) => ALL_METRICS.find((metric) => metric.key === key)?.label ?? key).join(', ')
}

/** Which run to keep under T08: only a run passing every gate is eligible; between two eligible runs, the one the
accuracy verdict favours, else the cheaper (null when both cost the same). */
function keepAdvice(comparison: Comparison, favoured: RunReport | null, reason: string): string {
  const { before, after } = comparison
  const fails = (report: RunReport) => report.failed_gates.length > 0
  if (fails(before) && fails(after)) {
    return `Neither run is eligible as the best set-up: run ${before.id} fails ${gateNames(before)}, run ${after.id} fails ${gateNames(after)}.`
  }
  if (favoured && fails(favoured)) {
    const other = favoured === after ? before : after
    return `But run ${favoured.id} fails ${gateNames(favoured)}, so it is not eligible: keep run ${other.id}'s set-up.`
  }
  if (favoured) return `Keep run ${favoured.id}'s set-up${reason}.`
  const eligible = fails(before) ? after : fails(after) ? before : null
  return eligible ? `Keep run ${eligible.id}'s set-up: the other fails ${gateNames(eligible === after ? before : after)}.` : 'Both cost the same per question, so either set-up will do.'
}

/** The plain-words advice on top of a comparison (D31 Q3): "better" only when the paired test says the accuracy
difference is real; otherwise the cheaper set-up. Either way, only a run passing every gate is kept (T08). */
export function recommendation(comparison: Comparison): string {
  const { before, after, change, questions } = comparison
  const gap = `${signed(after.scores.accuracy - before.scores.accuracy, 2)} on the 1 to 5 scale`
  const cost = costChange(before.cost_per_question, after.cost_per_question)
  const moved = questions ? ` Run ${after.id} fixed ${count(questions.fixed.length)} and broke ${questions.broken.length}.` : ''
  if (change.accuracy.verdict === 'better') return `Run ${after.id} is really better on accuracy (${gap}) and ${cost}. ${keepAdvice(comparison, after, '')}${moved}`
  if (change.accuracy.verdict === 'worse') return `Run ${after.id} is really worse on accuracy (${gap}) and ${cost}. ${keepAdvice(comparison, before, '')}${moved}`
  const [cheap, dear] = after.cost_per_question < before.cost_per_question ? [after, before] : [before, after]
  const saving = Math.round((100 * (dear.cost_per_question - cheap.cost_per_question)) / dear.cost_per_question)
  const advice = saving === 0 ? keepAdvice(comparison, null, '') : keepAdvice(comparison, cheap, `, the cheaper one: it costs ${saving}% less per question`)
  return `No real difference in accuracy (${gap}): a gap this small can come from chance. ${advice}${moved}`
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
    ({ ...row, key: ALL_METRICS[index].key, digits: 3, lowerIsBetter: ALL_METRICS[index].key === 'false_refusal_rate' }))
  return [...scores,
    { key: 'cost_per_question', label: 'Cost per question ($)', before: before.cost_per_question, after: after.cost_per_question, digits: 4, lowerIsBetter: true },
    { key: 'latency_s', label: 'Seconds per answer', before: before.latency_s, after: after.latency_s, digits: 1, lowerIsBetter: true }]
}

/** A change with its sign; one that rounds to nothing has none, either way. */
export function signed(value: number, digits: number): string {
  const rounded = Number(value.toFixed(digits))
  const text = rounded.toFixed(digits)
  return rounded > 0 ? `+${text}` : text
}

/** The paired change as read on the page: the mean change, with its interval. */
export function changeLine(before: number, after: number, change: PairedChange): string {
  return `Before ${before.toFixed(3)}, After ${after.toFixed(3)}: ${signed(after - before, 3)} (95% interval ${signed(change.low, 3)} to ${signed(change.high, 3)})`
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
