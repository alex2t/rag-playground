import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RunReport, RunScores, RunSettings, RunSummary } from './api/types.ts'
import { askLink, bandOf, estimateFor, estimateLine, hasAnswers, isWorking, overBudget, questionsLine, reportCsv, statusLine, valuesOfRun } from './evaluate.ts'
import type { PanelValues } from './panel.ts'

const SETTINGS: RunSettings = {
  chunking_method: 'llm_enriched', chunk_size: 800, overlap: 200, chunk_set_id: 'x', top_k: 4, hybrid: true,
  openai_ranking: null, rerank: true, answer_model: 'openai/sol', prompt_name: 'mine', temperature_controlled: true,
}
const RUN: RunSummary = {
  id: 7, created_at: '2026-11-01 10:00:00', status: 'done', error: null, stack: 'B', split: 'dev', questions: 192, full: true,
  done: 192, job_id: null, job_status: null, settings: SETTINGS,
}
const BASE: PanelValues = {
  stacks: 'both', chunking_method: 'fixed', chunk_size: 1024, overlap: 100, top_k: 2, rerank: false, answer_model: 'openai/nano',
  prompt_name: 'default', hybrid: false, openai_ranking: { ranker: 'auto', embedding_weight: 1, text_weight: 1, score_threshold: 0 },
}
const SCORES: RunScores = {
  mrr: 0.9, recall: 0.8, ndcg: 0.7, hit: 0.95, keyword_recall: 0.6, accuracy: 4.25, completeness: 4, relevance: 4.5,
  faithfulness: 3.5, correct_refusal_rate: 1, false_refusal_rate: 0.1,
}
const REPORT: RunReport = {
  ...RUN, scores: SCORES, failed_gates: [], cost_per_question: 0.001, latency_s: 2, categories: [
    { category: 'numerical', questions: 3, accuracy: 4, completeness: 4, relevance: 4, faithfulness: 4 }],
}
const ESTIMATE = { questions: 192, estimate_usd: 0.25, seconds: 120, budget_left_usd: 1 }

test('bands follow plan.md 4.9 at their exact limits', () => {
  assert.equal(bandOf('mrr', 0.9), 'good')
  assert.equal(bandOf('mrr', 0.899), 'fair')
  assert.equal(bandOf('recall', 0.75), 'fair')
  assert.equal(bandOf('recall', 0.749), 'poor')
  assert.equal(bandOf('accuracy', 4.5), 'good')
  assert.equal(bandOf('faithfulness', 4), 'fair')
  assert.equal(bandOf('faithfulness', 3.99), 'poor')
  assert.equal(bandOf('correct_refusal_rate', 0.9), 'good')
})

test('every score has its band limits exactly, on both sides', () => {
  for (const metric of ['mrr', 'recall', 'ndcg', 'hit', 'correct_refusal_rate'] as const) {
    assert.deepEqual([0.9, 0.8999, 0.75, 0.7499].map((value) => bandOf(metric, value)), ['good', 'fair', 'fair', 'poor'], metric)
  }
  for (const metric of ['accuracy', 'completeness', 'relevance', 'faithfulness'] as const) {
    assert.deepEqual([4.5, 4.4999, 4, 3.9999].map((value) => bandOf(metric, value)), ['good', 'fair', 'fair', 'poor'], metric)
  }
})

test('a score with no band in the plan gets none, whatever its value', () => {
  assert.equal(bandOf('false_refusal_rate', 0.01), null)
  assert.equal(bandOf('keyword_recall', 1), null)
})

test('a sample is never read as a full run', () => {
  assert.equal(questionsLine(RUN), 'dev, 192 questions')
  assert.equal(questionsLine({ ...RUN, full: false, questions: 20 }), 'dev sample, 20 questions')
  assert.equal(questionsLine({ ...RUN, split: 'heldout', questions: 48 }), 'held-out, 48 questions')
})

test('a run waiting behind another says queued, a running one its progress', () => {
  assert.equal(statusLine({ ...RUN, status: 'running', job_id: 1, job_status: 'queued', done: 0 }), 'queued')
  assert.equal(statusLine({ ...RUN, status: 'running', job_id: 1, job_status: 'running', done: 12 }), '12 of 192 questions')
  assert.equal(statusLine({ ...RUN, status: 'failed' }), 'failed')
  assert.equal(statusLine(RUN), 'done')
})

test('the list is polled only while a job works on a run', () => {
  assert.equal(isWorking([RUN]), false)
  assert.equal(isWorking([RUN, { ...RUN, job_id: 3 }]), true)
  assert.equal(isWorking([]), false)
})

test('held-out answers and a running run are never opened', () => {
  assert.equal(hasAnswers(RUN), true)
  assert.equal(hasAnswers({ ...RUN, status: 'failed' }), true)
  assert.equal(hasAnswers({ ...RUN, split: 'heldout' }), false)
  assert.equal(hasAnswers({ ...RUN, status: 'running' }), false)
})

test('opening a Stack B run loads its settings and keeps the panel\'s Stack A ones', () => {
  const values = valuesOfRun(RUN, BASE)
  assert.deepEqual(values, { ...BASE, stacks: 'B', chunking_method: 'llm_enriched', chunk_size: 800, overlap: 200, top_k: 4, rerank: true,
    answer_model: 'openai/sol', prompt_name: 'mine', hybrid: true })
})

test('opening a Stack A run loads its ranking; its derived hybrid flag leaves the Stack B switch alone', () => {
  const ranking = { ranker: 'none' as const, embedding_weight: 1, text_weight: 0, score_threshold: 0.2 }
  const values = valuesOfRun({ stack: 'A', settings: { ...SETTINGS, openai_ranking: ranking, hybrid: true } }, BASE)
  assert.equal(values.stacks, 'A')
  assert.deepEqual(values.openai_ranking, ranking)
  assert.equal(values.hybrid, false)
})

test('a link to Ask survives a test id with odd characters', () => {
  assert.equal(askLink('q 1/2'), '#/ask?test=q%201%2F2')
})

test('both stacks add up, since runs go one at a time', () => {
  assert.equal(estimateLine([{ ...ESTIMATE, stack: 'A' }, { ...ESTIMATE, stack: 'B', estimate_usd: 0.5, seconds: 240 }]),
    'Stack A: 192 questions, $0.2500; Stack B: 192 questions, $0.5000. Total about $0.7500 and about 6 min.')
  assert.match(estimateLine([{ ...ESTIMATE, stack: 'B', seconds: 30 }]), /about 30 s\.$/)
})

test('the budget is checked against both runs together, at its exact limit', () => {
  const both = (a: number, b: number) => [{ ...ESTIMATE, stack: 'A' as const, estimate_usd: a }, { ...ESTIMATE, stack: 'B' as const, estimate_usd: b }]
  assert.equal(overBudget(both(0.6, 0.6)), true)
  assert.equal(overBudget(both(0.5, 0.5)), false)
})

test('an estimate counts only for the settings and question set it was made for', () => {
  const items = [{ ...ESTIMATE, stack: 'B' as const }]
  const estimated = { values: BASE, questions: 'dev' as const, items }
  assert.deepEqual(estimateFor(estimated, { ...BASE }, 'dev'), items)
  assert.equal(estimateFor(null, BASE, 'dev'), null)
  assert.equal(estimateFor(estimated, BASE, 'heldout'), null)
  assert.equal(estimateFor(estimated, { ...BASE, top_k: 4 }, 'dev'), null)
  assert.equal(estimateFor(estimated, { ...BASE, prompt_name: 'mine' }, 'dev'), null)
  assert.equal(estimateFor(estimated, { ...BASE, stacks: 'A' }, 'dev'), null)
  assert.equal(estimateFor(estimated, { ...BASE, openai_ranking: { ...BASE.openai_ranking, ranker: 'none' } }, 'dev'), null)
})

test('the CSV has overall and category rows at full precision', () => {
  const rows = reportCsv({ ...REPORT, scores: { ...SCORES, accuracy: 4.123456789 } }).split('\r\n')
  assert.equal(rows[0], '﻿scope,metric,value')
  assert.ok(rows.includes('overall,accuracy,4.123456789'))
  assert.ok(rows.includes('overall,cost_per_question,0.001'))
  assert.ok(rows.includes('numerical,accuracy,4'))
  assert.ok(rows.includes('numerical,questions,3'))
})

test('a held-out CSV has overall rows only', () => {
  const rows = reportCsv({ ...REPORT, split: 'heldout', categories: null }).split('\r\n')
  assert.ok(rows.slice(1).filter(Boolean).every((row) => row.startsWith('overall,')))
})
