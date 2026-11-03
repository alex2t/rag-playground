import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RunSummary } from './api/types.ts'
import { latestFinished, NEEDS, PATH } from './home.ts'
import { PAGES } from './route.ts'

const RUN = {
  id: 9, created_at: '2026-11-03 10:00:00', status: 'done', error: null, stack: 'B', split: 'dev', questions: 20, full: false,
  done: 20, job_id: null, job_status: null, settings: {} as RunSummary['settings'],
} satisfies RunSummary

test('the latest finished run is the newest one done, skipping running and failed ones', () => {
  const runs: RunSummary[] = [{ ...RUN, id: 12, status: 'running' }, { ...RUN, id: 11, status: 'failed' }, { ...RUN, id: 10 }, { ...RUN, id: 9 }]
  assert.equal(latestFinished(runs)?.id, 10)
  assert.equal(latestFinished([{ ...RUN, status: 'failed' }]), null)
  assert.equal(latestFinished([]), null)
})

test('"Which page do I need?" names every page but Home once, each with a cost', () => {
  assert.deepEqual(NEEDS.map((need) => need.page).toSorted(), PAGES.filter((page) => page !== 'Home').toSorted())
  for (const need of NEEDS) assert.ok(need.want && need.cost, need.page)
})

test('the usual path goes Build, Ask, Evaluate, Compare', () => {
  assert.deepEqual(PATH.map((step) => step.page), ['Build', 'Ask', 'Evaluate', 'Compare'])
})
