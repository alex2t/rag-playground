import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PanelOptions } from './api/types.ts'
import { panelProblem, requestFor, restoredValues, settingsLine, stacksOf, startValues, withPrompt } from './panel.ts'

const OPTIONS: PanelOptions = {
  min_chunk_size: 64,
  max_chunk_size: 2048,
  max_overlap_share: 0.5,
  max_top_k: 8,
  answer_models: ['openai/nano', 'openai/sol'],
  start: {
    chunking_method: 'fixed', chunk_size: 1024, overlap: 200, top_k: 2, rerank: false, answer_model: 'openai/nano',
    openai_ranking: { ranker: 'auto', embedding_weight: 1, text_weight: 1, score_threshold: 0 }, hybrid: false,
  },
}
const START = startValues(OPTIONS)

test('both stacks are asked in order, one stack alone', () => {
  assert.deepEqual(stacksOf('both'), ['A', 'B'])
  assert.deepEqual(stacksOf('B'), ['B'])
})

test('the starting values pass', () => assert.equal(panelProblem(START, OPTIONS), null))

test('the limits pass and one step past them does not', () => {
  const problem = (changes: object) => panelProblem({ ...START, ...changes }, OPTIONS)
  assert.equal(problem({ chunk_size: 64, overlap: 32 }), null)
  assert.equal(problem({ chunk_size: 2048, overlap: 1024 }), null)
  assert.equal(problem({ top_k: 8 }), null)
  assert.match(problem({ chunk_size: 63, overlap: 0 })!, /Chunk size.*64 to 2048/)
  assert.match(problem({ chunk_size: 2049 })!, /Chunk size/)
  assert.match(problem({ overlap: 513 })!, /Overlap.*0 to 512/)
  assert.match(problem({ overlap: -1 })!, /Overlap/)
  assert.match(problem({ top_k: 9 })!, /Top-K.*1 to 8/)
  assert.match(problem({ top_k: 0 })!, /Top-K/)
})

test('an odd chunk size rounds the overlap limit down, as the API refuses more', () => {
  assert.equal(panelProblem({ ...START, chunk_size: 101, overlap: 50 }, OPTIONS), null)
  assert.match(panelProblem({ ...START, chunk_size: 101, overlap: 51 }, OPTIONS)!, /0 to 50/)
})

test('an emptied or fractional box is a problem, never sent', () => {
  assert.match(panelProblem({ ...START, chunk_size: NaN }, OPTIONS)!, /Chunk size/)
  assert.match(panelProblem({ ...START, overlap: 1.5 }, OPTIONS)!, /Overlap/)
  assert.match(panelProblem({ ...START, top_k: NaN }, OPTIONS)!, /Top-K/)
})

test('Stack A settings are checked only when Stack A is asked', () => {
  const ranking = (changes: object) => ({ ...START, openai_ranking: { ...START.openai_ranking, ...changes } })
  assert.match(panelProblem(ranking({ embedding_weight: -1 }), OPTIONS)!, /weights/)
  assert.match(panelProblem(ranking({ text_weight: NaN }), OPTIONS)!, /weights/)
  assert.match(panelProblem(ranking({ score_threshold: 1.1 }), OPTIONS)!, /threshold/)
  assert.match(panelProblem(ranking({ score_threshold: NaN }), OPTIONS)!, /threshold/)
  assert.equal(panelProblem({ ...ranking({ score_threshold: 1.1 }), stacks: 'B' }, OPTIONS), null)
  assert.equal(panelProblem(ranking({ embedding_weight: 0, text_weight: 0, score_threshold: 1 }), OPTIONS), null)
})

test("each stack sends its own search settings and never the other's", () => {
  const a = requestFor(START, 'A')
  const b = requestFor(START, 'B')
  assert.deepEqual(a.openai_ranking, START.openai_ranking)
  assert.equal('hybrid' in a, false)
  assert.equal(b.hybrid, false)
  assert.equal('openai_ranking' in b, false)
  assert.equal('stacks' in a, false)
  assert.deepEqual([a.stack, b.stack], ['A', 'B'])
})

test('saved values come back, a dropped model or prompt falls back to the start', () => {
  const saved = (changes: object) => JSON.stringify({ ...START, ...changes })
  const kept = restoredValues(saved({ chunk_size: 800, answer_model: 'openai/sol', prompt_name: 'mine' }), OPTIONS, ['default', 'mine'])
  assert.deepEqual([kept.chunk_size, kept.answer_model, kept.prompt_name], [800, 'openai/sol', 'mine'])
  const gone = restoredValues(saved({ chunk_size: 800, answer_model: 'openai/old', prompt_name: 'gone' }), OPTIONS, ['default'])
  assert.deepEqual([gone.chunk_size, gone.answer_model, gone.prompt_name], [800, 'openai/nano', 'default'])
  assert.deepEqual(restoredValues(null, OPTIONS, ['default']), START)
})

test('a Stack A box left blank while asking Stack B alone does not come back as null', () => {
  const blank = { ...START, stacks: 'B' as const, chunk_size: 800, openai_ranking: { ...START.openai_ranking, score_threshold: NaN } }
  assert.equal(panelProblem(blank, OPTIONS), null)
  const back = restoredValues(JSON.stringify(blank), OPTIONS, ['default'])
  assert.deepEqual(back.openai_ranking, START.openai_ranking)
  assert.equal(back.chunk_size, 800)
  assert.equal(panelProblem({ ...back, stacks: 'A' }, OPTIONS), null)
})

test('a null weight or threshold is refused, not read as 0', () => {
  const ranking = (changes: object) => ({ ...START, openai_ranking: { ...START.openai_ranking, ...changes } })
  assert.match(panelProblem(ranking({ embedding_weight: null }), OPTIONS)!, /weights/)
  assert.match(panelProblem(ranking({ score_threshold: null }), OPTIONS)!, /threshold/)
})

test('unreadable or wrongly shaped storage opens the page with the start', () => {
  for (const saved of ['{broken', 'null', '5', '{"openai_ranking":null}', '{"openai_ranking":"x"}', '{"chunk_size":null}', '{"top_k":99}']) {
    assert.deepEqual(restoredValues(saved, OPTIONS, ['default']), START, saved)
  }
})

test('saved settings missing a newer field take it from the start', () => {
  const back = restoredValues('{"chunk_size":800,"openai_ranking":{"ranker":"none"}}', OPTIONS, ['default'])
  assert.equal(back.chunk_size, 800)
  assert.deepEqual(back.openai_ranking, { ...START.openai_ranking, ranker: 'none' })
})

test('a result states every setting, with the search settings of its own stack', () => {
  assert.equal(settingsLine(requestFor(START, 'A')),
    'Stack A, 1024 tokens, overlap 200, fixed, K=2, OpenAI ranker on, weights 1:1, threshold 0, no reranking, openai/nano, prompt default')
  assert.equal(settingsLine(requestFor({ ...START, hybrid: true, rerank: true }, 'B')),
    'Stack B, 1024 tokens, overlap 200, fixed, K=2, hybrid on, reranked, openai/nano, prompt default')
  const none = { ...START, openai_ranking: { ...START.openai_ranking, ranker: 'none' as const } }
  assert.match(settingsLine(requestFor(none, 'A')), /ranker none, weights 1:1/)
})

test('a linked prompt is chosen only if that version exists, and nothing else changes', () => {
  const values = { ...START, top_k: 4 }
  assert.deepEqual(withPrompt(values, 'strict', ['default', 'strict']), { ...values, prompt_name: 'strict' })
  assert.deepEqual(withPrompt(values, 'gone', ['default', 'strict']), values)
  assert.deepEqual(withPrompt(values, '', ['default', 'strict']), values)
})
