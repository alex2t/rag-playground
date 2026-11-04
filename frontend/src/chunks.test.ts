import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { BuiltSet } from './api/types.ts'
import { byMethod, choiceLabel, chunkChoices, chunkKey, chunksProblem, fromKey, missingLine } from './chunks.ts'

function built(stack: 'A' | 'B', chunk_size: number, overlap: number, chunking_method: BuiltSet['chunking_method'] = 'fixed'): BuiltSet {
  return { stack, chunking_method, chunk_size, overlap, chunk_set_id: `${chunking_method}__c${chunk_size}__o${overlap}`, chunk_count: 1, created_at: '2026-11-04' }
}

test('one choice per chunk set, listing every stack it is built on', () => {
  const choices = chunkChoices([built('B', 400, 78), built('A', 400, 78), built('B', 600, 60)])
  assert.deepEqual(choices.map(({ chunk_size, overlap, stacks }) => [chunk_size, overlap, stacks]), [[400, 78, ['A', 'B']], [600, 60, ['B']]])
})

test('sets differing only in overlap or method stay separate', () => {
  const choices = chunkChoices([built('A', 800, 0), built('A', 800, 156), built('A', 800, 0, 'llm_enriched')])
  assert.equal(choices.length, 3)
})

test('choices sort by method, then size as a number, then overlap', () => {
  const choices = chunkChoices([built('A', 1600, 312), built('A', 200, 39, 'llm_enriched'), built('A', 800, 200), built('A', 800, 0), built('A', 100, 20)])
  assert.deepEqual(choices.map(chunkKey), ['fixed|100|20', 'fixed|800|0', 'fixed|800|200', 'fixed|1600|312', 'llm_enriched|200|39'])
})

test('nothing built gives no choice', () => {
  assert.deepEqual(chunkChoices([]), [])
})

test('the same set built twice on a stack lists that stack once', () => {
  assert.deepEqual(chunkChoices([built('B', 400, 0), built('B', 400, 0)])[0].stacks, ['B'])
})

test('groups follow the method order and leave out a method with nothing built', () => {
  const groups = byMethod(chunkChoices([built('A', 200, 39, 'llm_enriched'), built('A', 100, 20)]))
  assert.deepEqual(groups.map(([method, items]) => [method, items.length]), [['fixed', 1], ['llm_enriched', 1]])
  assert.deepEqual(byMethod(chunkChoices([built('A', 100, 20)])).map(([method]) => method), ['fixed'])
})

test('a key reads back as the same settings', () => {
  assert.deepEqual(fromKey(chunkKey({ chunking_method: 'llm_enriched', chunk_size: 400, overlap: 78 })), { chunking_method: 'llm_enriched', chunk_size: 400, overlap: 78 })
})

test('the label says which stacks hold the set', () => {
  assert.equal(choiceLabel({ chunking_method: 'fixed', chunk_size: 400, overlap: 78, stacks: ['A', 'B'] }), '400 / 78 tokens, on A and B')
  assert.equal(choiceLabel({ chunking_method: 'fixed', chunk_size: 600, overlap: 60, stacks: ['B'] }), '600 / 60 tokens, on B only')
})

test('a page is held until the built sets are read, and while a chosen stack lacks the chosen set', () => {
  const values = { chunking_method: 'fixed' as const, chunk_size: 600, overlap: 60, stacks: 'both' as const }
  assert.equal(chunksProblem(null, values), 'Reading which chunk sets are built...')
  assert.equal(chunksProblem([built('B', 600, 60)], values), 'Pick chunks built on Stack A, or change the stack.')
  assert.equal(chunksProblem([], values), 'Pick chunks built on Stack A and Stack B, or change the stack.')
  assert.equal(chunksProblem([built('B', 600, 60)], { ...values, stacks: 'B' }), null)
  assert.equal(chunksProblem([built('B', 600, 60), built('A', 600, 60)], values), null)
})

test('the missing line names each stack lacking the set, and is null when none does', () => {
  assert.equal(missingLine([]), null)
  assert.match(missingLine(['A'])!, /^These chunks are not built on Stack A\./)
  assert.match(missingLine(['A', 'B'])!, /^These chunks are not built on Stack A and Stack B\./)
})
