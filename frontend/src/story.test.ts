import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Config, LadderState, Option, Step } from './api/types.ts'
import { chartRows, choosingPrompts, estimateIsStale, finalStep, heldoutLabel, jobLine, keptOption, money, promptList, tradeOff } from './story.ts'

test('a queued job says it is waiting, a running one says how far it is', () => {
  const job = { id: 1, kind: 'ladder_step', run_id: null, error: null, message: 'S1 on Stack B: preparing', progress: 0 }
  assert.equal(jobLine({ ...job, status: 'queued' }), 'Waiting for the step already running to finish')
  assert.equal(jobLine({ ...job, status: 'running', message: 'S1: run 2 of 5', progress: 0.284 }), 'S1: run 2 of 5 (28%)')
})

const config: Config = { chunk_size: 1024, overlap: 200, top_k: 2, answer_model: 'm', prompt_name: 'default',
  method: 'fixed', rerank: false }

function option(accuracy: number, mrr: number, kept: boolean, cost = 0.001): Option {
  return { config, kept, run_id: 1, accuracy, mrr, cost_per_question: cost, failed_gates: [] }
}

function step(name: string, ...tried: Option[]): Step {
  return { step: name, kept: config, tried }
}

function ladder(steps: Step[], next: string | null = 'S2'): LadderState {
  return { stack: 'A', steps, next_step: next, needs_prompts: false, missing: [], estimate_usd: 0, enrichment_usd: 0,
    budget_left_usd: 1, job_id: null, last_error: null, saved_prompts: null, heldout: null }
}

test('each stack line follows its own kept option, and stops at the step not reached', () => {
  const a = ladder([step('S0', option(4, 0.9, true)), step('S1', option(3, 0.1, false), option(4.5, 0.8, true))])
  const b = ladder([step('S0', option(4.2, 0.95, true))], 'S1')
  const rows = chartRows(a, b, 'accuracy')
  assert.deepEqual(rows.slice(0, 3), [{ step: 'S0', A: 4, B: 4.2 }, { step: 'S1', A: 4.5, B: null },
    { step: 'S2', A: null, B: null }])
  assert.equal(rows.length, 8)
  assert.equal(chartRows(a, b, 'mrr')[1].A, 0.8)
})

test('a stack not loaded yet has no line', () => {
  assert.deepEqual(chartRows(null, null, 'mrr')[0], { step: 'S0', A: null, B: null })
})

test('the kept option is the marked one, not the first', () => {
  assert.equal(keptOption(step('S1', option(1, 1, false), option(2, 2, true)))?.accuracy, 2)
})

test('S7 reports the stronger model against the kept one', () => {
  const report = tradeOff(step('S7', option(4, 1, true, 0.001), option(4.5, 1, false, 0.004)))
  assert.deepEqual(report, { accuracy: 0.5, costTimes: 4 })
  assert.equal(tradeOff(step('S1', option(4, 1, true), option(4.5, 1, false))), null)
})

test('a final choice exists only on a finished ladder', () => {
  const steps = [step('S0', option(4, 1, true))]
  assert.equal(finalStep(ladder(steps, 'S1')), undefined)
  assert.equal(finalStep(ladder(steps, null))?.step, 'S0')
})

test('S6 cannot run on an estimate that does not cover the typed prompts', () => {
  const s6 = ladder([], 'S6')
  assert.equal(estimateIsStale(s6, 'v2', ''), true)
  assert.equal(estimateIsStale(s6, '', ''), false)
  assert.equal(estimateIsStale(s6, 'v2, v3', 'v2,v3'), false)
})

test('changing the prompts after Estimate needs a new estimate, also when emptying the box', () => {
  const previewed = { ...ladder([], 'S6'), missing: [config] }
  assert.equal(estimateIsStale(previewed, 'v2,v3,v4', 'v2'), true)
  assert.equal(estimateIsStale(previewed, '', 'v2'), true)
})

test('a saved S6 choice and other steps have nothing to estimate or choose', () => {
  const saved = { ...ladder([], 'S6'), saved_prompts: ['v2'], missing: [config] }
  assert.equal(choosingPrompts(saved), false)
  assert.equal(estimateIsStale(saved, 'v3', ''), false)
  assert.equal(choosingPrompts(ladder([], 'S6')), true)
  assert.equal(estimateIsStale(ladder([], 'S5'), 'v2', ''), false)
})

test('the held-out label says when one run is both S0 and final', () => {
  const s0 = option(4, 1, false)
  const final = option(4, 1, true)
  const panel = { runs: [s0, final], missing: [], estimate_usd: 0, gain: null }
  assert.equal(heldoutLabel(s0, panel), 'S0')
  assert.equal(heldoutLabel(final, panel), 'Final')
  assert.equal(heldoutLabel(final, { ...panel, runs: [final] }), 'S0 and final')
  assert.equal(heldoutLabel(final, { ...panel, runs: [final], missing: [config] }), 'Final')
})

test('money keeps small estimates readable', () => {
  assert.equal(money(0.27871), '$0.2787')
  assert.equal(money(12.5), '$12.50')
})

test('a prompt list ignores spaces and blanks, and an empty text means none', () => {
  assert.deepEqual(promptList(' v2, v3 ,, '), ['v2', 'v3'])
  assert.deepEqual(promptList('  '), [])
})
