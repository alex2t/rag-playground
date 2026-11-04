import assert from 'node:assert/strict'
import { test } from 'node:test'
import { HEADLINE, OTHER, TRUST } from './evaluate.ts'
import { CATEGORY_HELP, METRIC_HELP } from './help.ts'

test('every score shown in a run report has an explanation', () => {
  for (const metric of [...HEADLINE, ...OTHER, ...TRUST]) assert.ok(METRIC_HELP[metric.key], metric.key)
})

test('every question category of the dataset has an explanation, and no other', () => {
  const categories = ['direct_fact', 'numerical', 'temporal', 'exact_term', 'multi_doc', 'comparative', 'unanswerable']
  assert.deepEqual(Object.keys(CATEGORY_HELP).sort(), [...categories].sort())
  for (const category of categories) assert.ok(CATEGORY_HELP[category], category)
})
