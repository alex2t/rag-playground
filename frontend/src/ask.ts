/** Pure logic of the Ask page. */

import type { AskChunk, AskQuestion, AskResult } from './api/types.ts'

export function byCategory(questions: AskQuestion[]): [string, AskQuestion[]][] {
  const groups = new Map<string, AskQuestion[]>()
  for (const question of questions) groups.set(question.category, [...(groups.get(question.category) ?? []), question])
  return [...groups]
}

/** What to send: the picked test question, or the typed text. Null when there is nothing to ask. */
export function questionBody(typed: string, testId: string): { question: string } | { test_id: string } | null {
  if (testId) return { test_id: testId }
  return typed.trim() ? { question: typed } : null
}

export function money(usd: number): string {
  return `$${usd.toFixed(4)}`
}

export function chunkLine(chunk: AskChunk): string {
  return `${chunk.rank}. ${chunk.source}, score ${chunk.score.toFixed(3)}${chunk.gold ? ', holds the answer' : ''}`
}

/** Documents that hold the answer but were not retrieved: the first thing to read when a test question goes wrong. */
export function missedSources(result: AskResult): string[] {
  const found = new Set(result.chunks.map((chunk) => chunk.source))
  return result.gold_sources.filter((source) => !found.has(source))
}

/** Labels a result must carry (T14), and the reranker's repair flag. */
export function warnings(result: AskResult): string[] {
  return [...(result.temperature_controlled ? [] : ['Temperature not controlled.']),
    ...(result.rerank_repaired ? ["The reranker's order was invalid and had to be completed."] : [])]
}
