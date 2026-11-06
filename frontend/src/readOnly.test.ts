import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readOnlyOf } from './readOnly.ts'

test('buttons are off until the server has answered', () => {
  assert.equal(readOnlyOf(null), true)
})

test('the server decides once it has answered', () => {
  assert.equal(readOnlyOf({ read_only: true }), true)
  assert.equal(readOnlyOf({ read_only: false }), false)
})
