import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RunSettings, RunSummary } from './api/types.ts'
import { afterPool, LABELS, oneApart, options, pickedRun, settle, valuesOf } from './runPicker.ts'

const SETTINGS: RunSettings = {
  chunking_method: 'fixed', chunk_size: 800, overlap: 156, chunk_set_id: 'x', top_k: 3, hybrid: false,
  openai_ranking: null, rerank: false, answer_model: 'openai/nano', prompt_name: 'default', temperature_controlled: true,
}
const RANKING = { ranker: 'auto' as const, embedding_weight: 1, text_weight: 1, score_threshold: 0 }
const run = (id: number, settings: Partial<RunSettings>, extra: Partial<RunSummary> = {}): RunSummary => ({
  id, created_at: '2026-11-05 10:00:00', status: 'done', error: null, stack: 'B', split: 'dev', questions: 192, full: true,
  done: 192, job_id: null, job_status: null, settings: { ...SETTINGS, ...settings }, ...extra,
})
const stackA = (id: number, settings: Partial<RunSettings>) =>
  run(id, { openai_ranking: RANKING, ...settings }, { stack: 'A' })

test('a run gives a value for every dropdown, in dropdown order', () => {
  const values = valuesOf(stackA(1, {}))
  assert.deepEqual(Object.keys(values), LABELS)
  assert.deepEqual(values, {
    Stack: 'A', 'Question set': 'dev (192 questions)', 'Chunking method': 'fixed', 'Chunk size': '800', Overlap: '156',
    'Top-K': '3', Search: 'OpenAI ranker on, weights 1:1, threshold 0', Reranking: 'off', 'Answer model': 'openai/nano',
    Prompt: 'default',
  })
  assert.equal(valuesOf(run(2, {}, { split: 'heldout', questions: 48 }))['Question set'], 'held-out (48 questions)')
})

test('a dropdown offers only values of runs matching the choices above it, numbers in numeric order', () => {
  const runs = [run(1, { chunk_size: 1600 }), run(2, { chunk_size: 400 }), run(3, { chunk_size: 100 }), stackA(4, { chunk_size: 200 })]
  assert.deepEqual(options(runs, {}, 'Stack'), ['A', 'B'])
  assert.deepEqual(options(runs, { Stack: 'B', 'Question set': 'dev (192 questions)', 'Chunking method': 'fixed' }, 'Chunk size'),
    ['100', '400', '1600'])
  assert.deepEqual(options(runs, { Stack: 'A', 'Question set': 'dev (192 questions)', 'Chunking method': 'fixed' }, 'Chunk size'),
    ['200'])
})

test('values that are not all whole numbers sort as text', () => {
  const runs = ['10', '2', 'v10', 'v2'].map((prompt_name, index) => run(index + 1, { prompt_name }))
  const above = settle(runs, {})
  assert.deepEqual(options(runs, above, 'Prompt'), ['10', '2', 'v10', 'v2'])
})

test('a choice below does not narrow the dropdowns above it', () => {
  const runs = [run(1, { prompt_name: 'default' }), stackA(2, { prompt_name: 'strict' })]
  assert.deepEqual(options(runs, { Prompt: 'strict' }, 'Stack'), ['A', 'B'])
})

test('settling fills lone values and stops at the first dropdown with a real choice', () => {
  const runs = [run(1, { top_k: 2 }), run(2, { top_k: 3 })]
  assert.deepEqual(settle(runs, {}), {
    Stack: 'B', 'Question set': 'dev (192 questions)', 'Chunking method': 'fixed', 'Chunk size': '800', Overlap: '156',
  })
  assert.deepEqual(settle(runs, { Prompt: 'default' })['Prompt'], undefined)
  const done = settle(runs, { 'Top-K': '3' })
  assert.equal(done['Top-K'], '3')
  assert.equal(done['Prompt'], 'default')
})

test('settling drops a choice no run has any more and keeps the ones that still hold', () => {
  const runs = [run(1, { top_k: 2, prompt_name: 'default' }), run(2, { top_k: 3, prompt_name: 'default' }),
    run(3, { top_k: 3, prompt_name: 'strict' })]
  const picks = { ...settle(runs, { 'Top-K': '3' }), Prompt: 'strict' }
  assert.equal(settle(runs, picks)['Prompt'], 'strict')
  const moved = settle(runs, { ...picks, 'Top-K': '2' })
  assert.equal(moved['Top-K'], '2')
  assert.equal(moved['Prompt'], 'default')
  assert.equal(settle(runs, { ...picks, 'Top-K': '9' })['Top-K'], undefined)
})

test('the picked run is the oldest of those sharing every setting, with their count', () => {
  const runs = [run(9, {}), run(4, {}), run(6, { top_k: 2 })]
  assert.deepEqual(pickedRun(runs, settle(runs, { 'Top-K': '3' })), { run: runs[1], count: 2 })
  assert.deepEqual(pickedRun(runs, settle(runs, { 'Top-K': '2' })), { run: runs[2], count: 1 })
})

test('no run is picked until every dropdown is chosen', () => {
  const runs = [run(1, { top_k: 2 }), run(2, { top_k: 3 })]
  assert.equal(pickedRun(runs, settle(runs, {})), null)
})

test('After offers only runs of the question set Before asked, and every run until Before is chosen', () => {
  const runs = [run(1, {}), run(2, {}), run(3, {}, { split: 'heldout', questions: 48 })]
  assert.deepEqual(afterPool(runs, runs[0]).map(({ id }) => id), [1, 2])
  assert.deepEqual(afterPool(runs, runs[2]).map(({ id }) => id), [3])
  assert.deepEqual(afterPool(runs, undefined).map(({ id }) => id), [1, 2, 3])
})

test('runs one setting apart: exactly one difference, same question set, oldest per set-up, in dropdown order', () => {
  const chosen = run(27, { prompt_name: 'strict' })
  const runs = [
    chosen,
    run(30, {}),                                      // prompt only
    run(28, {}),                                      // same set-up as 30, older
    run(12, { top_k: 2 }, { stack: 'B' }),             // K and prompt: two differences
    run(35, { top_k: 2, prompt_name: 'strict' }),      // K only, newer than the prompt run
    run(14, { prompt_name: 'strict' }, { split: 'heldout', questions: 48 }),
    run(15, { prompt_name: 'strict' }),                // no difference
  ]
  assert.deepEqual(oneApart(runs, chosen).map(({ run, label }) => [run.id, label]), [[35, 'Top-K'], [28, 'Prompt']])
})
