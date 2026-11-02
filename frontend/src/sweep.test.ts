import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PanelOptions, SweepItem, SweepPlan, SweepRun } from './api/types.ts'
import type { PanelValues } from './panel.ts'
import {
  axisValues, bodyFor, chartRows, choicesFor, fromKey, isWorking, sweepJobLine, overBudget, parseNumbers, planKey, planLine, plansFor, toRun,
  totalCost, valueText, variableOf, variablesFor,
} from './sweep.ts'

const OPTIONS: PanelOptions = {
  min_chunk_size: 64, max_chunk_size: 2048, max_overlap_share: 0.5, max_top_k: 8, answer_models: ['openai/nano', 'openai/sol'],
  start: { chunking_method: 'fixed', chunk_size: 1024, overlap: 200, top_k: 2, rerank: false, answer_model: 'openai/nano',
    openai_ranking: { ranker: 'auto', embedding_weight: 1, text_weight: 1, score_threshold: 0 }, hybrid: false },
}
const VALUES: PanelValues = { ...OPTIONS.start, stacks: 'both', prompt_name: 'default' }
const NONE = { low: -0.1, high: 0.1, real: false, verdict: 'no real difference' as const }
const BETTER = { low: 0.05, high: 0.3, real: true, verdict: 'better' as const }
const WORSE = { low: -0.3, high: -0.01, real: false, verdict: 'worse' as const }

function run(run_id: number, accuracy: number, change: SweepRun['change'] = null): SweepRun {
  return { run_id, accuracy, accuracy_ci: [accuracy - 0.2, accuracy + 0.1], mrr: 0.9, mrr_ci: [0.85, 0.95], cost_per_question: 0.001, failed_gates: [], change }
}

function item(value: SweepItem['value'], found: SweepRun | null, base = false): SweepItem {
  return { value, base, chunk_set_id: 'fixed__c1024__o200', built: true, run: found, estimate_usd: found ? null : 0.25 }
}

function plan(stack: 'A' | 'B', items: SweepItem[], extra: Partial<SweepPlan> = {}): SweepPlan {
  const runs = items.filter((i) => !i.run).length
  return { stack, variable: 'top_k', items, runs_to_do: runs, estimate_usd: runs * 0.25, budget_left_usd: 1, ...extra }
}

test('with both stacks only shared settings can be swept; each stack adds its own', () => {
  const keys = (stacks: 'A' | 'B' | 'both') => variablesFor(stacks).map(({ key }) => key)
  assert.deepEqual(keys('both'), ['chunk_size', 'overlap', 'top_k', 'chunking_method', 'rerank', 'answer_model', 'prompt_name'])
  assert.deepEqual(keys('B'), [...keys('both'), 'hybrid'])
  assert.deepEqual(keys('A'), [...keys('both'), 'ranker', 'embedding_weight', 'text_weight', 'score_threshold'])
})

test('settings with a known list are ticked from it', () => {
  assert.deepEqual(choicesFor('rerank', OPTIONS, []), [false, true])
  assert.deepEqual(choicesFor('answer_model', OPTIONS, []), ['openai/nano', 'openai/sol'])
  assert.deepEqual(choicesFor('prompt_name', OPTIONS, ['default', 'mine']), ['default', 'mine'])
  assert.deepEqual(choicesFor('chunking_method', OPTIONS, []), ['fixed', 'llm_enriched'])
  assert.deepEqual(choicesFor('ranker', OPTIONS, []), ['none', 'auto'])
})

test('typed numbers are split at commas, whole numbers where the setting needs them', () => {
  assert.deepEqual(parseNumbers('int', ' 200, 400 ,800 '), { values: [200, 400, 800] })
  assert.deepEqual(parseNumbers('float', '0.5, 2'), { values: [0.5, 2] })
  assert.deepEqual(parseNumbers('int', '200, 4.5'), { problem: '"4.5" is not a whole number.' })
  assert.deepEqual(parseNumbers('float', '1, abc'), { problem: '"abc" is not a number.' })
  assert.deepEqual(parseNumbers('int', ' , '), { problem: 'Type at least one value, separated by commas.' })
  assert.deepEqual(parseNumbers('int', '200,,400'), { values: [200, 400] })
})

test('a request carries one stack and that stack\'s own search settings', () => {
  const body = bodyFor(VALUES, 'B', 'top_k', [4, 6])
  assert.deepEqual(body, { base: { stack: 'B', chunking_method: 'fixed', chunk_size: 1024, overlap: 200, top_k: 2, rerank: false,
    answer_model: 'openai/nano', prompt_name: 'default', hybrid: false }, variable: 'top_k', values: [4, 6] })
  assert.equal('hybrid' in bodyFor(VALUES, 'A', 'top_k', [4]).base, false)
})

test('a plan counts only for the panel, setting and values it was made for', () => {
  const key = planKey(VALUES, 'top_k', [4, 6])
  const planned = { key, plans: [plan('B', [])] }
  assert.equal(plansFor(planned, planKey({ ...VALUES }, 'top_k', [4, 6])), planned.plans)
  assert.equal(plansFor(planned, planKey(VALUES, 'top_k', [4, 8])), null)
  assert.equal(plansFor(planned, planKey(VALUES, 'overlap', [4, 6])), null)
  assert.equal(plansFor(planned, planKey({ ...VALUES, rerank: true }, 'top_k', [4, 6])), null)
  assert.equal(plansFor(null, key), null)
})

test('the page follows a sweep only while one waits or runs on a stack', () => {
  const job = (status: 'queued' | 'running' | 'done' | 'failed') => ({ id: 1, kind: 'sweep', status, run_id: null, progress: 0, message: '', error: null })
  assert.equal(isWorking({ A: null, B: job('done') }), false)
  assert.equal(isWorking({ A: job('failed') }), false)
  assert.equal(isWorking({ A: null, B: job('running') }), true)
  assert.equal(isWorking({ A: job('queued'), B: job('done') }), true)
  assert.equal(isWorking({}), false)
})

test('costs add up over stacks, and the total must fit what is left', () => {
  const plans = [plan('A', [item(2, run(1, 4)), item(4, null)]), plan('B', [item(2, null), item(4, null)])]
  assert.equal(totalCost(plans), 0.75)
  assert.equal(overBudget(plans), false)
  assert.equal(overBudget(plans.map((p) => ({ ...p, budget_left_usd: 0.74 }))), true)
  assert.equal(overBudget(plans.map((p) => ({ ...p, budget_left_usd: 0.75 }))), false)
  assert.equal(overBudget([]), false)
  assert.equal(overBudget([plan('B', [item(2, run(1, 4))], { budget_left_usd: -1.96 })]), false)
  assert.deepEqual(toRun([plan('A', [item(2, run(1, 4))]), plan('B', [item(2, null)])]), ['B'])
})

test('the plan line says what each stack still runs and the total', () => {
  assert.equal(planLine([plan('A', [item(2, run(1, 4)), item(4, null)]), plan('B', [item(2, run(2, 4))])]),
    'Stack A: 1 of 2 values to run, about $0.2500; Stack B: every value has a run. Total about $0.2500.')
  assert.equal(planLine([plan('B', [item(2, run(2, 4))])]), 'Stack B: every value has a run.')
})

test('numbers are drawn in increasing order, other values in the order given, the base marked', () => {
  const sizes = [plan('B', [item(800, null, true), item(200, null), item(400, null)])]
  assert.deepEqual(axisValues(sizes, variableOf('chunk_size')).map(({ label }) => label), ['200', '400', '800 (base)'])
  const models = [plan('B', [item('openai/sol', null), item('openai/nano', null, true)])]
  assert.deepEqual(axisValues(models, variableOf('answer_model')).map(({ label }) => label), ['sol', 'nano (base)'])
  assert.deepEqual(axisValues([plan('B', [item(false, null, true), item(true, null)])], variableOf('rerank')).map(({ label }) => label), ['off (base)', 'on'])
  assert.deepEqual(axisValues([plan('B', [item(true, null, true), item(false, null)])], variableOf('rerank')).map(({ label }) => label), ['on (base)', 'off'])
})

test('a value appears once on the axis when both stacks sweep it', () => {
  const plans = [plan('A', [item(2, null, true), item(4, null)]), plan('B', [item(2, null, true), item(4, null)])]
  assert.deepEqual(axisValues(plans, variableOf('top_k')).map(({ value }) => value), [2, 4])
})

test('each stack\'s point, interval and mark come from its own run; a value not run has no point', () => {
  const plans = [
    plan('A', [item(2, run(1, 4), true), item(4, run(2, 4.5, { accuracy: BETTER, mrr: NONE })), item(6, null)]),
    plan('B', [item(2, run(3, 4.2), true), item(4, run(4, 3.8, { accuracy: WORSE, mrr: NONE })), item(6, run(5, 4.2, { accuracy: NONE, mrr: NONE }))]),
  ]
  const rows = chartRows(plans, variableOf('top_k'), 'accuracy')
  assert.deepEqual(rows.map((row) => [row.step, row.A, row.B, row.A_mark, row.B_mark]), [
    ['2 (base)', 4, 4.2, '', ''], ['4', 4.5, 3.8, '+', '-'], ['6', null, 4.2, '', '']])
  const [aBar] = [rows[1].A_bar!]
  assert.deepEqual(aBar.map((n) => Number(n.toFixed(6))), [0.2, 0.1])
  assert.equal(rows[2].A_bar, null)
})

test('the MRR chart reads MRR, its interval and its own mark', () => {
  const plans = [plan('B', [item(2, run(3, 4.2), true), item(4, run(4, 3.8, { accuracy: WORSE, mrr: BETTER }))])]
  const rows = chartRows(plans, variableOf('top_k'), 'mrr')
  assert.deepEqual([rows[1].B, rows[1].B_mark, rows[1].B_bar!.map((n) => Number(n.toFixed(6)))], [0.9, '+', [0.05, 0.05]])
})

test('on and off read as words', () => {
  assert.deepEqual([valueText(true), valueText(false), valueText(4), valueText('auto')], ['on', 'off', '4', 'auto'])
})

test('a plan key gives back exactly what it was made from', () => {
  assert.deepEqual(fromKey(planKey(VALUES, 'rerank', [true])), [VALUES, 'rerank', [true]])
})

test('a sweep says it waits, how far it is, that it finished, or why it failed', () => {
  const job = { id: 1, kind: 'sweep', run_id: 3, progress: 0.25, message: 'Sweep on Stack B: run 1 of 2, 96 of 192 questions', error: null }
  assert.equal(sweepJobLine('B', { ...job, status: 'queued' }), 'Sweep on Stack B: waiting for the job before it')
  assert.equal(sweepJobLine('B', { ...job, status: 'running' }), 'Sweep on Stack B: run 1 of 2, 96 of 192 questions (25%)')
  assert.equal(sweepJobLine('A', { ...job, status: 'done' }), 'The last sweep on Stack A finished.')
  assert.equal(sweepJobLine('A', { ...job, status: 'failed', error: 'Budget reached' }), 'The last sweep on Stack A failed: Budget reached')
})
