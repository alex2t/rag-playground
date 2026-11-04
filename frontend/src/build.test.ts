import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { BuildEstimate, BuildJob, BuiltSet, PanelOptions } from './api/types.ts'
import { missingStacks, buildProblem, estimateFor, estimateLine, isWorking, jobLine, jobTone, overBudget, settingsOf, startValues, toBuild, type BuildValues } from './build.ts'

const OPTIONS: PanelOptions = {
  min_chunk_size: 64, max_chunk_size: 2048, max_overlap_share: 0.5, max_top_k: 8, answer_models: ['m'],
  start: { chunking_method: 'fixed', chunk_size: 1024, overlap: 200, top_k: 2, rerank: false, answer_model: 'm',
    openai_ranking: { ranker: 'auto', embedding_weight: 1, text_weight: 1, score_threshold: 0 }, hybrid: false },
}
const VALUES: BuildValues = { chunking_method: 'fixed', chunk_size: 800, overlap: 100, stacks: 'both' }
const ESTIMATE: BuildEstimate = { chunk_set_id: 'fixed__c800__o100', chunks: 84, enrichment_usd: 0, built: [], budget_left_usd: 1 }
const JOB: BuildJob = { chunking_method: 'fixed', chunk_size: 800, overlap: 100, id: 3, created_at: '2026-11-02 10:00:00', status: 'done', stack: 'B', chunk_set_id: 'fixed__c800__o100', error: null }

test('the page opens on S0 chunking for both stacks', () => {
  assert.deepEqual(startValues(OPTIONS), { chunking_method: 'fixed', chunk_size: 1024, overlap: 200, stacks: 'both' })
})

test('size and overlap follow the panel ranges at their exact edges', () => {
  assert.equal(buildProblem({ ...VALUES, chunk_size: 64, overlap: 32 }, OPTIONS), null)
  assert.equal(buildProblem({ ...VALUES, chunk_size: 2048, overlap: 1024 }, OPTIONS), null)
  assert.match(buildProblem({ ...VALUES, chunk_size: 63 }, OPTIONS)!, /from 64 to 2048/)
  assert.match(buildProblem({ ...VALUES, chunk_size: 2049, overlap: 0 }, OPTIONS)!, /from 64 to 2048/)
  assert.match(buildProblem({ ...VALUES, overlap: 401 }, OPTIONS)!, /from 0 to 400/)
  assert.match(buildProblem({ ...VALUES, chunk_size: Number.NaN }, OPTIONS)!, /Chunk size/)
  assert.match(buildProblem({ ...VALUES, overlap: 10.5 }, OPTIONS)!, /Overlap/)
})

test('a request carries the chunk set only, never the stack choice', () => {
  assert.deepEqual(settingsOf(VALUES), { chunking_method: 'fixed', chunk_size: 800, overlap: 100 })
})

test('an estimate counts only for the exact values it was made for, stacks included', () => {
  const estimated = { values: VALUES, estimate: ESTIMATE }
  assert.equal(estimateFor(estimated, { ...VALUES }), ESTIMATE)
  assert.equal(estimateFor(estimated, { ...VALUES, overlap: 101 }), null)
  assert.equal(estimateFor(estimated, { ...VALUES, stacks: 'A' }), null)
  assert.equal(estimateFor(estimated, { ...VALUES, chunking_method: 'llm_enriched' }), null)
  assert.equal(estimateFor(null, VALUES), null)
})

test('only the chosen stacks still missing the set are built', () => {
  assert.deepEqual(toBuild(ESTIMATE, 'both'), ['A', 'B'])
  assert.deepEqual(toBuild({ ...ESTIMATE, built: ['B'] }, 'both'), ['A'])
  assert.deepEqual(toBuild({ ...ESTIMATE, built: ['B'] }, 'B'), [])
  assert.deepEqual(toBuild({ ...ESTIMATE, built: ['A'] }, 'B'), ['B'])
})

test('only enrichment still to pay can be over the budget, even with spend past it', () => {
  assert.equal(overBudget({ ...ESTIMATE, enrichment_usd: 0.06, budget_left_usd: 0.05 }), true)
  assert.equal(overBudget({ ...ESTIMATE, enrichment_usd: 0.05, budget_left_usd: 0.05 }), false)
  assert.equal(overBudget({ ...ESTIMATE, enrichment_usd: 0, budget_left_usd: -1.96 }), false)
})

test('the estimate says the set, its chunks, where it goes and what it costs', () => {
  assert.equal(estimateLine(ESTIMATE, VALUES), 'fixed__c800__o100: 84 chunks. To build on Stack A and Stack B. No paid call.')
  const enriched = { ...VALUES, chunking_method: 'llm_enriched' as const }
  assert.equal(estimateLine({ ...ESTIMATE, chunk_set_id: 'llm_enriched__c800__o100', enrichment_usd: 0.054, built: ['B'] }, enriched),
    'llm_enriched__c800__o100: 84 chunks. Already built on Stack B. To build on Stack A. Enrichment about $0.0540, paid once for both stacks.')
  assert.match(estimateLine({ ...ESTIMATE, enrichment_usd: 0 }, enriched), /Already enriched: nothing to pay\.$/)
})

test('a set built on every chosen stack has nothing to build', () => {
  assert.equal(estimateLine({ ...ESTIMATE, built: ['A', 'B'] }, VALUES), 'fixed__c800__o100: 84 chunks. Already built on Stack A and Stack B. Nothing to build.')
  assert.equal(estimateLine({ ...ESTIMATE, built: ['A'] }, { ...VALUES, stacks: 'A' }), 'fixed__c800__o100: 84 chunks. Already built on Stack A. Nothing to build.')
})

test('a job says how it stands, and a failure says why in red', () => {
  assert.equal(jobLine(JOB), 'fixed__c800__o100 on Stack B: built')
  assert.equal(jobTone(JOB), 'good')
  const failed = { ...JOB, status: 'failed' as const, error: 'ResponseHandlingException: connection refused' }
  assert.equal(jobLine(failed), 'fixed__c800__o100 on Stack B: failed. ResponseHandlingException: connection refused')
  assert.equal(jobTone(failed), 'bad')
  assert.equal(jobLine({ ...JOB, status: 'queued' }), 'fixed__c800__o100 on Stack B: waiting for the job before it')
  assert.equal(jobTone({ ...JOB, status: 'running' }), 'working')
})

test('the page follows jobs only while one waits or runs', () => {
  assert.equal(isWorking([JOB, { ...JOB, status: 'failed' }]), false)
  assert.equal(isWorking([JOB, { ...JOB, status: 'queued' }]), true)
  assert.equal(isWorking([{ ...JOB, status: 'running' }]), true)
  assert.equal(isWorking([]), false)
})

const BUILT: BuiltSet = { stack: 'B', chunk_set_id: 'fixed__c800__o100', chunking_method: 'fixed', chunk_size: 800, overlap: 100, chunk_count: 84, created_at: '2026-11-02' }

test('a stack is missing the chunks unless a set of the same method, size and overlap is built on it', () => {
  assert.deepEqual(missingStacks([BUILT], VALUES), ['A'])
  assert.deepEqual(missingStacks([BUILT], { ...VALUES, stacks: 'B' }), [])
  assert.deepEqual(missingStacks([BUILT, { ...BUILT, stack: 'A' }], VALUES), [])
  assert.deepEqual(missingStacks([], VALUES), ['A', 'B'])
})

test('a set differing in method, size or overlap does not count', () => {
  assert.deepEqual(missingStacks([BUILT], { ...VALUES, stacks: 'B', chunking_method: 'llm_enriched' }), ['B'])
  assert.deepEqual(missingStacks([BUILT], { ...VALUES, stacks: 'B', chunk_size: 801 }), ['B'])
  assert.deepEqual(missingStacks([BUILT], { ...VALUES, stacks: 'B', overlap: 99 }), ['B'])
})

