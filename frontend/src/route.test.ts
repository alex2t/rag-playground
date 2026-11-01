import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hashOf, linkedTest, pageFor, PAGES } from './route.ts'

test('every page is reached from its own hash', () => {
  for (const page of PAGES) assert.equal(pageFor(hashOf(page)), page)
})

test('a page keeps its address, so a saved link still works', () => {
  assert.equal(hashOf('Story'), '#/story')
  assert.equal(hashOf('Prompt'), '#/prompt')
  assert.equal(hashOf('Ask'), '#/ask')
})

test('the menu lists the built pages in order', () => {
  assert.deepEqual(PAGES, ['Story', 'Ask', 'Evaluate', 'Prompt'])
  assert.equal(pageFor('#/evaluate'), 'Evaluate')
  assert.equal(pageFor('#/ask'), 'Ask')
})

test('a link to Ask opens Ask and names its test question', () => {
  assert.equal(pageFor('#/ask?test=q%2F1'), 'Ask')
  assert.equal(linkedTest('#/ask?test=q%2F1'), 'q/1')
  assert.equal(linkedTest('#/ask'), '')
})

test('an empty or unknown hash opens Story', () => {
  assert.equal(pageFor(''), 'Story')
  assert.equal(pageFor('#/nowhere'), 'Story')
})
