/** Pure logic of the settings panel's chunk choice: only chunk sets already built can be picked. */

import type { BuildSettings, BuiltSet, StackId } from './api/types.ts'
import { missingStacks, type BuildValues } from './build.ts'

export type ChunkChoice = BuildSettings & { stacks: StackId[] }

const METHOD_ORDER: BuildSettings['chunking_method'][] = ['fixed', 'llm_enriched']
export const METHOD_LABEL: Record<BuildSettings['chunking_method'], string> = { fixed: 'Fixed chunks', llm_enriched: 'LLM-enriched chunks' }

export function chunkKey({ chunking_method, chunk_size, overlap }: BuildSettings): string {
  return `${chunking_method}|${chunk_size}|${overlap}`
}

export function fromKey(key: string): BuildSettings {
  const [chunking_method, size, overlap] = key.split('|')
  return { chunking_method: chunking_method as BuildSettings['chunking_method'], chunk_size: Number(size), overlap: Number(overlap) }
}

/** One choice per built chunk set, with the stacks it is built on, sorted by method, size, then overlap. */
export function chunkChoices(built: BuiltSet[]): ChunkChoice[] {
  const byKey = new Map<string, ChunkChoice>()
  for (const { chunking_method, chunk_size, overlap, stack } of built) {
    const key = chunkKey({ chunking_method, chunk_size, overlap })
    const choice = byKey.get(key) ?? { chunking_method, chunk_size, overlap, stacks: [] }
    if (!choice.stacks.includes(stack)) choice.stacks = [...choice.stacks, stack].sort()
    byKey.set(key, choice)
  }
  return [...byKey.values()].sort((a, b) => METHOD_ORDER.indexOf(a.chunking_method) - METHOD_ORDER.indexOf(b.chunking_method)
    || a.chunk_size - b.chunk_size || a.overlap - b.overlap)
}

/** The choices grouped by chunking method, in display order; a method with nothing built is left out. */
export function byMethod(choices: ChunkChoice[]): [BuildSettings['chunking_method'], ChunkChoice[]][] {
  return METHOD_ORDER.map((method) => [method, choices.filter((choice) => choice.chunking_method === method)] as [BuildSettings['chunking_method'], ChunkChoice[]])
    .filter(([, items]) => items.length > 0)
}

function stacksWord(stacks: StackId[]): string {
  return stacks.length === 2 ? 'A and B' : `${stacks[0]} only`
}

export function choiceLabel({ chunk_size, overlap, stacks }: ChunkChoice): string {
  return `${chunk_size} / ${overlap} tokens, on ${stacksWord(stacks)}`
}

/** Why a page may not ask, estimate or start with these chunks: the built sets are not read yet, or a chosen stack
 * lacks the chosen set. Null when every chosen stack has it. Shared by Ask, Evaluate and Sweep. */
export function chunksProblem(built: BuiltSet[] | null, values: BuildValues): string | null {
  if (built === null) return 'Reading which chunk sets are built...'
  const missing = missingStacks(built, values)
  return missing.length ? `Pick chunks built on ${missing.map((stack) => `Stack ${stack}`).join(' and ')}, or change the stack.` : null
}

/** Why the chosen chunk set cannot answer on the chosen stacks, or null when every chosen stack has it. */
export function missingLine(missing: StackId[]): string | null {
  if (missing.length === 0) return null
  const names = missing.map((stack) => `Stack ${stack}`).join(' and ')
  return `These chunks are not built on ${names}. Pick another chunk set, another stack, or build them on the Build page.`
}
