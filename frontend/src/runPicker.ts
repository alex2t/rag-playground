/** Compare's run choice as one dropdown per setting: each offers only values a finished full run has. */

import type { RunSummary } from './api/types.ts'
import { settingFields } from './compare.ts'

export type Picks = Record<string, string>

export const LABELS = ['Stack', 'Question set', 'Chunking method', 'Chunk size', 'Overlap', 'Top-K', 'Search', 'Reranking',
  'Answer model', 'Prompt']
const SPLITS = { dev: 'dev (192 questions)', heldout: 'held-out (48 questions)' }

/** The runs After can use: those that asked Before's questions, or every run while Before is not chosen. */
export function afterPool(runs: RunSummary[], before: RunSummary | undefined): RunSummary[] {
  return before ? runs.filter((run) => run.split === before.split) : runs
}

/** A run's value for every dropdown. */
export function valuesOf(run: RunSummary): Picks {
  const [stack, ...rest] = settingFields(run)
  return Object.fromEntries([stack, ['Question set', SPLITS[run.split]], ...rest])
}

function sameAs(run: RunSummary, picks: Picks, labels: string[]): boolean {
  const values = valuesOf(run)
  return labels.every((label) => values[label] === picks[label])
}

/** The values `label` can take, given the choices in the dropdowns above it; numbers in numeric order. */
export function options(runs: RunSummary[], picks: Picks, label: string): string[] {
  const above = LABELS.slice(0, LABELS.indexOf(label))
  const values = [...new Set(runs.filter((run) => sameAs(run, picks, above)).map((run) => valuesOf(run)[label]))]
  const numeric = values.every((value) => /^\d+$/.test(value))
  return values.sort(numeric ? (a, b) => Number(a) - Number(b) : undefined)
}

/** The choices that still hold, top to bottom: a value no run has is dropped, a lone value is filled in, and a
 * dropdown stays empty until every one above it is chosen. */
export function settle(runs: RunSummary[], picks: Picks): Picks {
  const settled: Picks = {}
  for (const label of LABELS) {
    const offered = options(runs, settled, label)
    const value = offered.includes(picks[label]) ? picks[label] : offered.length === 1 ? offered[0] : undefined
    if (value === undefined) break
    settled[label] = value
  }
  return settled
}

/** The run every dropdown points to, the oldest when several share those settings, and how many do. */
export function pickedRun(runs: RunSummary[], picks: Picks): { run: RunSummary; count: number } | null {
  const matching = runs.filter((run) => sameAs(run, picks, LABELS)).sort((a, b) => a.id - b.id)
  return matching.length ? { run: matching[0], count: matching.length } : null
}

/** Runs of the same question set that differ from `chosen` in one setting only, one per set-up (the oldest), in
 * dropdown order. */
export function oneApart(runs: RunSummary[], chosen: RunSummary): { run: RunSummary; label: string }[] {
  const base = valuesOf(chosen)
  const found = new Map<string, { run: RunSummary; label: string }>()
  for (const run of runs.filter((run) => run.split === chosen.split).sort((a, b) => a.id - b.id)) {
    const values = valuesOf(run)
    const differ = LABELS.filter((label) => values[label] !== base[label])
    const key = JSON.stringify(values)
    if (differ.length === 1 && !found.has(key)) found.set(key, { run, label: differ[0] })
  }
  return [...found.values()].sort((a, b) => LABELS.indexOf(a.label) - LABELS.indexOf(b.label))
}
