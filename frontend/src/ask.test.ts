import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AskChunk, AskResult } from './api/types.ts'
import { byCategory, chunkLine, missedSources, money, questionBody, warnings } from './ask.ts'

const CHUNK: AskChunk = { rank: 1, source: 'a.md', score: 0.12345, text: 'Text.', gold: false }
const RESULT: AskResult = {
  answer: 'Yes.', stack: 'A', latency_s: 1, cost_usd: 0.003, temperature_controlled: true, rerank_repaired: false,
  chunks: [CHUNK], reference_answer: null, gold_sources: [], judgement: null,
}

test('questions group by category, keeping their order', () => {
  const q = (id: string, category: string) => ({ id, category, question: id })
  const groups = byCategory([q('1', 'x'), q('2', 'y'), q('3', 'x')])
  assert.deepEqual(groups.map(([category, items]) => [category, items.map((item) => item.id)]), [['x', ['1', '3']], ['y', ['2']]])
})

test('a picked test question wins over typed text, since only one may be sent', () => {
  assert.deepEqual(questionBody('typed', 't1'), { test_id: 't1' })
  assert.deepEqual(questionBody('typed', ''), { question: 'typed' })
})

test('a blank box is nothing to ask', () => {
  assert.equal(questionBody('', ''), null)
  assert.equal(questionBody('  \n', ''), null)
})

test('money shows the fractions of a cent a question costs', () => {
  assert.equal(money(0.00023), '$0.0002')
  assert.equal(money(0.0027), '$0.0027')
})

test('a chunk shows rank, document and score, and says when it holds the answer', () => {
  assert.equal(chunkLine(CHUNK), '1. a.md, score 0.123')
  assert.equal(chunkLine({ ...CHUNK, gold: true }), '1. a.md, score 0.123, holds the answer')
})

test('only gold documents not retrieved count as missed', () => {
  assert.deepEqual(missedSources({ ...RESULT, gold_sources: ['a.md', 'b.md'] }), ['b.md'])
  assert.deepEqual(missedSources({ ...RESULT, gold_sources: ['a.md'] }), [])
  assert.deepEqual(missedSources({ ...RESULT, chunks: [], gold_sources: ['a.md'] }), ['a.md'])
})

test('uncontrolled temperature and a repaired ranking are labelled', () => {
  assert.deepEqual(warnings(RESULT), [])
  assert.deepEqual(warnings({ ...RESULT, temperature_controlled: false }), ['Temperature not controlled.'])
  assert.equal(warnings({ ...RESULT, rerank_repaired: true }).length, 1)
})
