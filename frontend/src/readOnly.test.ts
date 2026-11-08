import assert from 'node:assert/strict'
import { test } from 'node:test'
import { noticeOf, offersSignIn, READ_ONLY_NOTICE, readOnlyOf, SIGNED_IN_NOTICE, signInProblem } from './readOnly.ts'

test('buttons are off until the server has answered', () => {
  assert.equal(readOnlyOf(null, false), true)
})

test('the server decides once it has answered', () => {
  assert.equal(readOnlyOf({ read_only: true }, false), true)
  assert.equal(readOnlyOf({ read_only: false }, false), false)
})

test('the admin signing in turns the buttons on in a read-only demo', () => {
  assert.equal(readOnlyOf({ read_only: true }, true), false)
})

test('signing in cannot turn the buttons on before the server has answered', () => {
  assert.equal(readOnlyOf(null, true), true)
})

test('sign-in is offered only in a read-only demo, until done', () => {
  assert.equal(offersSignIn({ read_only: true }, false), true)
  assert.equal(offersSignIn({ read_only: true }, true), false)
  assert.equal(offersSignIn({ read_only: false }, false), false)
  assert.equal(offersSignIn(null, false), false)
})

test('the notice says read-only, then signed in, and is absent on a site that is not read-only', () => {
  assert.equal(noticeOf({ read_only: true }, false), READ_ONLY_NOTICE)
  assert.equal(noticeOf({ read_only: true }, true), SIGNED_IN_NOTICE)
  assert.equal(noticeOf({ read_only: false }, false), null)
  assert.equal(noticeOf(null, false), null)
})

test('a refused password reads as cancelled or wrong, anything else shows its status', () => {
  assert.equal(signInProblem(401), 'Sign-in cancelled or wrong password.')
  assert.equal(signInProblem(502), 'Sign-in failed (502).')
})
