import assert from 'node:assert/strict'
import { test } from 'node:test'
import { pngName, resolveVariables, wrapText } from './chartImage.ts'

test('every CSS variable becomes its value, each its own', () => {
  const values: Record<string, string> = { '--color-line': ' #ddd', '--color-stack-a': '#2a78d6 ' }
  const markup = '<line stroke="var(--color-line)"/><path fill="var(--color-stack-a)" stroke="var(--color-line)"/>'
  assert.equal(resolveVariables(markup, (name) => values[name]),
    '<line stroke="#ddd"/><path fill="#2a78d6" stroke="#ddd"/>')
})

test('text breaks at spaces into rows that fit, losing no word', () => {
  assert.deepEqual(wrapText('one two three four', (row) => row.length <= 9), ['one two', 'three', 'four'])
  assert.deepEqual(wrapText('short line', () => true), ['short line'])
})

test('a word too long for any row stands alone rather than disappearing', () => {
  assert.deepEqual(wrapText('a verylongword b', (row) => row.length <= 3), ['a', 'verylongword', 'b'])
  assert.deepEqual(wrapText('verylongword b', (row) => row.length <= 3), ['verylongword', 'b'])
})

test('markup without variables is left alone', () => {
  assert.equal(resolveVariables('<text fill="#123">5</text>', () => 'x'), '<text fill="#123">5</text>')
})

test('a chart file is named after its title, without the range in brackets', () => {
  assert.equal(pngName('Accuracy per step (1 to 5, 192 dev questions)'), 'accuracy-per-step.png')
  assert.equal(pngName('MRR per step (0 to 1, answerable dev questions)'), 'mrr-per-step.png')
})
