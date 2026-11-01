import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PromptVersion } from './api/types.ts'
import { runCount, runLine, saveProblem } from './prompts.ts'

const run = { id: 5, stack: 'A' as const, split: 'dev', status: 'done', created_at: '2026-10-30 09:15:02' }
const versions: PromptVersion[] = [
  { name: 'default', text: 'Default text.', sha256: 'a', runs: [run] },
  { name: 'strict', text: 'Strict text.', sha256: 'b', runs: [] },
]

test('a new name with edited text can be saved', () => {
  assert.equal(saveProblem('short', 'New text.', versions), null)
  assert.equal(saveProblem('strict v2', 'Default text. More.', versions), null)
})

test('a missing name is asked for before anything else', () => {
  assert.equal(saveProblem('', '', versions), 'Give the new version a name.')
})

test('a name with an outer space or a comma is refused with its reason', () => {
  assert.match(saveProblem(' v1', 'New.', versions)!, /start or end with a space/)
  assert.match(saveProblem('v1 ', 'New.', versions)!, /start or end with a space/)
  assert.match(saveProblem('a,b', 'New.', versions)!, /comma/)
})

test('a taken name is refused, also for the text it already has', () => {
  assert.equal(saveProblem('strict', 'New.', versions), "A version named 'strict' already exists.")
  assert.equal(saveProblem('strict', 'Strict text.', versions), "A version named 'strict' already exists.")
})

test('a name differing only in case is a different version, as in the database', () => {
  assert.equal(saveProblem('Strict', 'New.', versions), null)
})

test('a blank text is refused', () => {
  assert.equal(saveProblem('v1', ' \n ', versions), 'The prompt text is empty.')
})

test('an unedited text is refused and names the version it copies', () => {
  assert.equal(saveProblem('v1', 'Strict text.', versions), "This is the same text as 'strict': edit it first.")
})

test('a change of spaces alone counts as an edit, since the model reads the text exactly', () => {
  assert.equal(saveProblem('v1', 'Strict text. ', versions), null)
})

test('a run line gives its id, stack, split, status and day', () => {
  assert.equal(runLine(run), 'Run 5, Stack A, dev, done, 2026-10-30')
})

test('a version counts its runs in words', () => {
  assert.equal(runCount(versions[0]), '1 run')
  assert.equal(runCount(versions[1]), '0 runs')
})
