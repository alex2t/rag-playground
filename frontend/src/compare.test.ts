import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Comparison, RunReport, RunScores, RunSettings, RunSummary } from './api/types.ts'
import { METRIC_HELP } from './help.ts'
import { changeLine, chartLegend, comparable, costChange, depthNote, judgeRows, partners, rateRows, recommendation, runChoice, runLine, runStatement, settingDiffs, signed, tableRows } from './compare.ts'

const SETTINGS: RunSettings = {
  chunking_method: 'fixed', chunk_size: 800, overlap: 200, chunk_set_id: 'x', top_k: 2, hybrid: true,
  openai_ranking: null, rerank: false, answer_model: 'openai/nano', prompt_name: 'default', temperature_controlled: true,
}
const RANKING = { ranker: 'auto' as const, embedding_weight: 1, text_weight: 2, score_threshold: 0 }
const RUN: RunSummary = {
  id: 5, created_at: '2026-10-30 10:00:00', status: 'done', error: null, stack: 'B', split: 'dev', questions: 192, full: true,
  done: 192, job_id: null, job_status: null, settings: SETTINGS,
}
const SCORES: RunScores = {
  mrr: 0.8, recall: 0.7, ndcg: 0.6, hit: 0.9, keyword_recall: 0.5, accuracy: 4, completeness: 3.5, relevance: 4.5,
  faithfulness: 3, correct_refusal_rate: 1, false_refusal_rate: 0.1,
}
const REPORT: RunReport = { ...RUN, scores: SCORES, failed_gates: [], cost_per_question: 0.0012, latency_s: 2.25, categories: null }
const LATER: RunReport = {
  ...REPORT, id: 7, scores: { ...SCORES, accuracy: 4.25, false_refusal_rate: 0.05 }, cost_per_question: 0.002, latency_s: 3,
}
const CHANGE = { low: -0.1, high: 0.2, real: false, verdict: 'no real difference' as const }
const COMPARISON: Comparison = { before: REPORT, after: LATER, change: { accuracy: CHANGE, mrr: CHANGE }, questions: null }
const run = (id: number, extra: Partial<RunSummary>) => ({ ...RUN, id, ...extra })

test('only finished runs of a whole question set can be compared', () => {
  const runs = [run(1, {}), run(2, { full: false, questions: 10 }), run(3, { status: 'running' }), run(4, { status: 'failed' })]
  assert.deepEqual(comparable(runs).map(({ id }) => id), [1])
})

test('a run pairs with others of its question set, never with itself', () => {
  const runs = [run(1, {}), run(2, {}), run(3, { split: 'heldout', questions: 48 }), run(4, { split: 'heldout', questions: 48 })]
  assert.deepEqual(partners(runs, 1).map(({ id }) => id), [2])
  assert.deepEqual(partners(runs, 3).map(({ id }) => id), [4])
})

test('nothing pairs before a first run is chosen, or with a run that cannot be compared', () => {
  assert.deepEqual(partners([run(1, {})], null), [])
  assert.deepEqual(partners([run(1, { full: false }), run(2, {})], 1), [])
})

test('a choice names the run, its stack, its questions and what sets it apart', () => {
  assert.equal(runChoice(run(19, { stack: 'A' })), 'Run 19, Stack A, dev, 192 questions, 800 tokens, overlap 200, K=2, 2026-10-30')
})

test('a Stack A run states its OpenAI ranking, a Stack B run its hybrid setting', () => {
  assert.equal(runLine({ stack: 'A', settings: { ...SETTINGS, openai_ranking: RANKING } }),
    'Stack A, 800 tokens, overlap 200, fixed, K=2, OpenAI ranker on, weights 1:2, threshold 0, no reranking, openai/nano, prompt default')
  assert.equal(runLine({ stack: 'B', settings: { ...SETTINGS, hybrid: false } }),
    'Stack B, 800 tokens, overlap 200, fixed, K=2, hybrid off, no reranking, openai/nano, prompt default')
})

test('a run whose model ignores temperature says so; another does not', () => {
  assert.match(runStatement('After', { ...REPORT, settings: { ...SETTINGS, temperature_controlled: false } }), /^After: run 5, .*\. Temperature not controlled\.$/)
  assert.doesNotMatch(runStatement('After', REPORT), /Temperature/)
})

test('the two scales stay apart, with no score lost or repeated', () => {
  assert.deepEqual(judgeRows(COMPARISON).map(({ label }) => label), ['Accuracy', 'Faithfulness', 'Completeness', 'Relevance'])
  assert.deepEqual(rateRows(COMPARISON).map(({ label }) => label),
    ['MRR', 'Recall@K', 'nDCG@K', 'Hit@K', 'Keyword recall', 'Correct refusal rate', 'False refusal rate'])
  assert.equal(judgeRows(COMPARISON).length + rateRows(COMPARISON).length, Object.keys(SCORES).length)
})

test('each side of a row holds its own run', () => {
  assert.deepEqual(judgeRows(COMPARISON)[0], { label: 'Accuracy', before: 4, after: 4.25 })
  assert.deepEqual(rateRows(COMPARISON).at(-1), { label: 'False refusal rate', before: 0.1, after: 0.05 })
})

test('the table has every score, the cost and the time, and marks what should fall', () => {
  const rows = tableRows(COMPARISON)
  assert.equal(rows.length, Object.keys(SCORES).length + 2)
  assert.deepEqual(rows.filter((row) => row.lowerIsBetter).map(({ label }) => label),
    ['False refusal rate', 'Cost per question ($)', 'Seconds per answer'])
  assert.deepEqual(rows.at(-2), { key: 'cost_per_question', label: 'Cost per question ($)', before: 0.0012, after: 0.002, digits: 4, lowerIsBetter: true })
  assert.deepEqual(rows.at(-1), { key: 'latency_s', label: 'Seconds per answer', before: 2.25, after: 3, digits: 1, lowerIsBetter: true })
})

test('every row of the table has an explanation for its i button', () => {
  for (const row of tableRows(COMPARISON)) assert.ok(METRIC_HELP[row.key], row.key)
})

test('a change carries its sign, and a change that rounds to nothing has none', () => {
  assert.equal(signed(0.125, 2), '+0.13')
  assert.equal(signed(-0.5, 3), '-0.500')
  assert.equal(signed(0, 3), '0.000')
  assert.equal(signed(0.0001, 3), '0.000')
  assert.equal(signed(-0.0001, 3), '0.000')
})

test('a paired change reads as both means, the change and its interval', () => {
  assert.equal(changeLine(4, 4.25, CHANGE), 'Before 4.000, After 4.250: +0.250 (95% interval -0.100 to +0.200)')
})

test('runs at different K carry a warning, and only those', () => {
  assert.equal(depthNote(COMPARISON), null)
  const other = { ...COMPARISON, after: { ...LATER, settings: { ...SETTINGS, top_k: 6 } } }
  assert.match(depthNote(other)!, /K=2 and K=6/)
})

test('a saved chart states both runs, each beside its own colour', () => {
  const stack = { ...COMPARISON, before: { ...REPORT, stack: 'A' as const, settings: { ...SETTINGS, openai_ranking: RANKING } } }
  const [before, after] = chartLegend(stack)
  assert.equal(before.swatch, '--color-before')
  assert.match(before.text, /^Before: run 5, Stack A, .*OpenAI ranker on/)
  assert.equal(after.swatch, '--color-after')
  assert.match(after.text, /^After: run 7, Stack B, .*hybrid on/)
})

const verdict = (v: 'better' | 'worse' | 'no real difference') => ({ low: 0, high: 0, real: v !== 'no real difference', verdict: v })
const MOVED = { fixed: [{ test_id: 'q1', category: 'c', question: 'q', before: 2, after: 5 }], broken: [], both_pass: 150, both_fail: 41 }

test('the cost change is in whole percent of Before, and a tiny one reads as the same', () => {
  assert.equal(costChange(0.0012, 0.002), 'costs 67% more per question')
  assert.equal(costChange(0.002, 0.001), 'costs 50% less per question')
  assert.equal(costChange(0.0012, 0.001204), 'costs the same per question')
})

test('a real gain says so, with the gap, the cost and what it fixed and broke', () => {
  const comparison = { ...COMPARISON, change: { accuracy: verdict('better'), mrr: CHANGE }, questions: MOVED }
  assert.equal(recommendation(comparison),
    "Run 7 is really better on accuracy (+0.25 on the 1 to 5 scale) and costs 67% more per question. Keep run 7's set-up. Run 7 fixed 1 question and broke 0.")
})

test('a real loss keeps the Before set-up', () => {
  const worse = { ...COMPARISON, after: { ...LATER, scores: { ...SCORES, accuracy: 3.5 } }, change: { accuracy: verdict('worse'), mrr: CHANGE } }
  assert.equal(recommendation(worse),
    "Run 7 is really worse on accuracy (-0.50 on the 1 to 5 scale) and costs 67% more per question. Keep run 5's set-up.")
})

test('no real difference points to the cheaper run, whichever side it is on', () => {
  assert.equal(recommendation(COMPARISON),
    "No real difference in accuracy (+0.25 on the 1 to 5 scale): a gap this small can come from chance. Keep run 5's set-up, the cheaper one: it costs 40% less per question.")
  const cheaperAfter = { ...COMPARISON, after: { ...LATER, cost_per_question: 0.0006 } }
  assert.match(recommendation(cheaperAfter), /Keep run 7's set-up, the cheaper one: it costs 50% less per question\.$/)
  const same = { ...COMPARISON, after: { ...LATER, cost_per_question: 0.0012 } }
  assert.match(recommendation(same), /Both cost the same per question, so either set-up will do\.$/)
})

test('a real gain is not kept when its run fails a gate; the other run is', () => {
  const failing = { ...COMPARISON, after: { ...LATER, failed_gates: ['mrr', 'faithfulness'] }, change: { accuracy: verdict('better'), mrr: CHANGE } }
  assert.equal(recommendation(failing),
    "Run 7 is really better on accuracy (+0.25 on the 1 to 5 scale) and costs 67% more per question. But run 7 fails MRR, Faithfulness, so it is not eligible: keep run 5's set-up.")
})

test('when both runs fail a gate, neither is advised', () => {
  const both = { ...COMPARISON, before: { ...REPORT, failed_gates: ['recall'] }, after: { ...LATER, failed_gates: ['correct_refusal_rate'] } }
  assert.match(recommendation(both), /Neither run is eligible as the best set-up: run 5 fails Recall@K, run 7 fails Correct refusal rate\.$/)
})

test('with no real difference, a cheaper run that fails a gate gives way to the other', () => {
  const cheapFails = { ...COMPARISON, before: { ...REPORT, failed_gates: ['mrr'] } }
  assert.match(recommendation(cheapFails), /But run 5 fails MRR, so it is not eligible: keep run 7's set-up\.$/)
  const sameCost = { ...COMPARISON, after: { ...LATER, cost_per_question: 0.0012, failed_gates: ['recall'] } }
  assert.match(recommendation(sameCost), /Keep run 5's set-up: the other fails Recall@K\.$/)
  const sameCostBeforeFails = { ...COMPARISON, before: { ...REPORT, failed_gates: ['faithfulness'] }, after: { ...LATER, cost_per_question: 0.0012 } }
  assert.match(recommendation(sameCostBeforeFails), /Keep run 7's set-up: the other fails Faithfulness\.$/)
})

test('a real verdict keeps the favoured run when only the other one fails a gate', () => {
  const better = { ...COMPARISON, before: { ...REPORT, failed_gates: ['mrr'] }, change: { accuracy: verdict('better'), mrr: CHANGE } }
  assert.match(recommendation(better), /Keep run 7's set-up\.$/)
  const worse = { ...COMPARISON, after: { ...LATER, failed_gates: ['mrr'] }, change: { accuracy: verdict('worse'), mrr: CHANGE } }
  assert.match(recommendation(worse), /Keep run 5's set-up\.$/)
})

test('a real loss on a run that fails a gate keeps After instead', () => {
  const worse = { ...COMPARISON, before: { ...REPORT, failed_gates: ['recall'] }, change: { accuracy: verdict('worse'), mrr: CHANGE } }
  assert.match(recommendation(worse), /But run 5 fails Recall@K, so it is not eligible: keep run 7's set-up\.$/)
})

test('only the settings the two runs do not share are listed', () => {
  assert.deepEqual(settingDiffs(RUN, RUN), [])
  const other = { ...RUN, settings: { ...SETTINGS, top_k: 4, prompt_name: 'strict' } }
  assert.deepEqual(settingDiffs(RUN, other), [
    { label: 'Top-K', before: '2', after: '4' },
    { label: 'Prompt', before: 'default', after: 'strict' },
  ])
})

test("runs on different stacks list the stack and each one's own search settings", () => {
  const stackA = { ...RUN, stack: 'A' as const, settings: { ...SETTINGS, openai_ranking: RANKING } }
  assert.deepEqual(settingDiffs(RUN, stackA), [
    { label: 'Stack', before: 'B', after: 'A' },
    { label: 'Search', before: 'hybrid on', after: 'OpenAI ranker on, weights 1:2, threshold 0' },
  ])
})
