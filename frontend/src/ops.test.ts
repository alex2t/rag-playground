import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { OpsSummary } from './api/types.ts'
import { apartLine, budgetLine, budgetTone, failureLine, leftLine, rateText, rateTone, seconds, splitLine } from './ops.ts'

const SUMMARY: OpsSummary = {
  window_days: 7,
  budget: { budget_usd: 60, spent_usd: 12.5, left_usd: 47.5, in_runs_usd: 12, outside_runs_usd: 0.5 },
  jobs: { finished: 4, active: 1, faults: 1, budget_stops: 1, restarts: 1, error_rate: 0.25, failed: [] },
  latency: [], version: 'abc1234', qdrant: 'ok',
}
const over = { ...SUMMARY, budget: { ...SUMMARY.budget, budget_usd: 5, spent_usd: 6.9633, left_usd: -1.9633 } }

test('spend reads against the budget, and what is left', () => {
  assert.equal(budgetLine(SUMMARY), '$12.50 spent of $60.00')
  assert.equal(leftLine(SUMMARY), '$47.50 left')
  assert.equal(splitLine(SUMMARY), 'Runs $12.00, outside runs (Ask, enrichment) $0.5000')
})

test('spend past the budget says so plainly instead of a negative amount', () => {
  assert.equal(budgetLine(over), '$6.96 spent of $5.00')
  assert.equal(leftLine(over), '$1.96 over the budget: paid work is refused until BUDGET_USD is raised')
  assert.equal(leftLine({ ...SUMMARY, budget: { ...SUMMARY.budget, left_usd: 0 } }), '$0.0000 left')
})

test('the budget turns amber under a tenth left and red past it, at the exact edges', () => {
  const left = (left_usd: number) => budgetTone({ ...SUMMARY, budget: { ...SUMMARY.budget, left_usd } })
  assert.deepEqual([left(6), left(5.99), left(0), left(-0.01)], ['good', 'warn', 'warn', 'bad'])
})

test('the error rate counts faults over finished jobs, or says none finished', () => {
  assert.equal(rateText(SUMMARY), '25% (1 of 4 jobs)')
  assert.equal(rateTone(SUMMARY), 'bad')
  const none = { ...SUMMARY, jobs: { ...SUMMARY.jobs, finished: 0, faults: 0, error_rate: null } }
  assert.equal(rateText(none), 'No job finished in 7 days')
  assert.equal(rateTone(none), 'good')
  assert.equal(rateTone({ ...SUMMARY, jobs: { ...SUMMARY.jobs, faults: 0, error_rate: 0 } }), 'good')
  assert.equal(rateText({ ...SUMMARY, jobs: { ...SUMMARY.jobs, faults: 0, error_rate: 0 } }), '0% (0 of 4 jobs)')
})

test('stops on purpose are listed apart', () => {
  assert.equal(apartLine({ ...SUMMARY, jobs: { ...SUMMARY.jobs, budget_stops: 2, restarts: 3, active: 4 } }), 'Budget stops 2, cut off by a restart 3, waiting or running 4')
})

test('a failure says when, which job, what kind, why, and the message', () => {
  const base = { id: 9, created_at: '2026-11-02 10:05:33', kind: 'build', stack: 'B' as const, status: 'failed' as const, error: 'RuntimeError: Qdrant is down', cause: 'fault' as const }
  assert.equal(failureLine(base), '2026-11-02 10:05 UTC, job 9, build on Stack B, fault: RuntimeError: Qdrant is down')
  assert.equal(failureLine({ ...base, kind: 'evaluate', stack: null, cause: 'budget', error: 'BudgetExceeded: x' }), '2026-11-02 10:05 UTC, job 9, evaluate, budget stop: BudgetExceeded: x')
  assert.match(failureLine({ ...base, cause: 'restart' }), /, app restart: /)
})

test('times read in seconds with one decimal', () => {
  assert.deepEqual([seconds(2.584), seconds(5.35)], ['2.6 s', '5.3 s'])
})
