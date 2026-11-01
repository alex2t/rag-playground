import assert from 'node:assert/strict'
import { test } from 'node:test'
import { refusal } from './client.ts'

test("the API's reason is shown as it is worded", () => {
  assert.equal(refusal(404, '{"detail":"Not found: x is not indexed on Stack A"}'), 'Not found: x is not indexed on Stack A')
})

test('a validation list has no one reason, so the status is shown', () => {
  assert.equal(refusal(422, '{"detail":[{"msg":"bad"}]}'), 'Request refused (422)')
})

test('a plain-text crash is reported as a failure, not a parse error', () => {
  assert.equal(refusal(500, 'Internal Server Error'), 'The server failed (500).')
  assert.equal(refusal(500, ''), 'The server failed (500).')
})
