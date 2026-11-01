/** Pure logic of the Evaluate page (T56). */

import type { Estimate, QuestionSet, RunReport, RunScores, RunSettings, RunSummary } from './api/types.ts'
import { csvCell } from './story.ts'
import { type PanelValues } from './panel.ts'

export type Metric = { key: keyof RunScores; label: string }
export type Band = 'good' | 'fair' | 'poor'

export const HEADLINE: Metric[] = [
  { key: 'mrr', label: 'MRR' }, { key: 'recall', label: 'Recall@K' },
  { key: 'accuracy', label: 'Accuracy' }, { key: 'faithfulness', label: 'Faithfulness' },
]
export const OTHER: Metric[] = [
  { key: 'ndcg', label: 'nDCG@K' }, { key: 'hit', label: 'Hit@K' }, { key: 'keyword_recall', label: 'Keyword recall' },
  { key: 'completeness', label: 'Completeness' }, { key: 'relevance', label: 'Relevance' },
]
export const TRUST: Metric[] = [
  { key: 'correct_refusal_rate', label: 'Correct refusal rate' }, { key: 'false_refusal_rate', label: 'False refusal rate' },
]

const BANDS: Partial<Record<keyof RunScores, [number, number]>> = {
  mrr: [0.9, 0.75], recall: [0.9, 0.75], ndcg: [0.9, 0.75], hit: [0.9, 0.75], correct_refusal_rate: [0.9, 0.75],
  accuracy: [4.5, 4], completeness: [4.5, 4], relevance: [4.5, 4], faithfulness: [4.5, 4],
}

/** The colour band of a score (plan.md 4.9). Keyword recall and the false refusal rate have none. */
export function bandOf(metric: keyof RunScores, value: number): Band | null {
  const limits = BANDS[metric]
  if (!limits) return null
  return value >= limits[0] ? 'good' : value >= limits[1] ? 'fair' : 'poor'
}

/** What a run asked, so a smoke test or a sample is never read as a full run. */
export function questionsLine(run: RunSummary): string {
  const set = run.split === 'heldout' ? 'held-out' : 'dev'
  return run.full ? `${set}, ${run.questions} questions` : `${set} sample, ${run.questions} questions`
}

export function statusLine(run: RunSummary): string {
  if (run.job_status === 'queued') return 'queued'
  if (run.status === 'running') return `${run.done} of ${run.questions} questions`
  return run.status
}

export function isWorking(runs: RunSummary[]): boolean {
  return runs.some((run) => run.job_id !== null)
}

export function hasAnswers(run: RunSummary): boolean {
  return run.split === 'dev' && run.status !== 'running'
}

/** The panel's values that repeat a run: settings it stored replace the panel's; the other stack's stay as they are. */
export function valuesOfRun(run: { stack: 'A' | 'B'; settings: RunSettings }, base: PanelValues): PanelValues {
  const { chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, openai_ranking, hybrid } = run.settings
  return {
    ...base, stacks: run.stack, chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name,
    openai_ranking: openai_ranking ?? base.openai_ranking,
    hybrid: run.stack === 'B' ? hybrid : base.hybrid,
  }
}

export function askLink(testId: string): string {
  return `#/ask?test=${encodeURIComponent(testId)}`
}

function duration(seconds: number): string {
  return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`
}

export type StackEstimate = Estimate & { stack: 'A' | 'B' }

/** Runs go one at a time, so both the cost and the time add up. */
export function estimateLine(estimates: StackEstimate[]): string {
  const cost = estimates.reduce((sum, item) => sum + item.estimate_usd, 0)
  const seconds = estimates.reduce((sum, item) => sum + item.seconds, 0)
  const parts = estimates.map((item) => `Stack ${item.stack}: ${item.questions} questions, $${item.estimate_usd.toFixed(4)}`)
  return `${parts.join('; ')}. Total about $${cost.toFixed(4)} and about ${duration(seconds)}.`
}

export type Estimated = { values: PanelValues; questions: QuestionSet; items: StackEstimate[] }

/** An estimate counts only for exactly what it was made for, so a slow reply cannot stand for settings changed meanwhile. */
export function estimateFor(estimated: Estimated | null, values: PanelValues, questions: QuestionSet): StackEstimate[] | null {
  const same = estimated?.questions === questions && JSON.stringify(estimated.values) === JSON.stringify(values)
  return same ? estimated.items : null
}

export function overBudget(estimates: StackEstimate[]): boolean {
  return estimates.reduce((sum, item) => sum + item.estimate_usd, 0) > estimates[0].budget_left_usd
}

const CSV_HEADER = ['scope', 'metric', 'value']

/** Overall scores, then each category's on a dev run, with full precision. */
export function reportCsv(report: RunReport): string {
  const overall = Object.entries({ ...report.scores, cost_per_question: report.cost_per_question, latency_s: report.latency_s })
    .map(([metric, value]) => ['overall', metric, value])
  const categories = (report.categories ?? []).flatMap(({ category, ...scores }) =>
    Object.entries(scores).map(([metric, value]) => [category, metric, value]))
  return '﻿' + [CSV_HEADER, ...overall, ...categories].map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n'
}
