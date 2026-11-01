/** Pure logic of the Prompt page. */

import type { PromptRun, PromptVersion } from './api/types.ts'

/** Why this version cannot be saved yet, or null. The API checks the name again; this says why in plain words. */
export function saveProblem(name: string, text: string, versions: PromptVersion[]): string | null {
  if (name === '') return 'Give the new version a name.'
  if (name !== name.trim()) return 'A name cannot start or end with a space.'
  if (name.includes(',')) return 'A name cannot contain a comma: the S6 box on Story separates names with commas.'
  if (versions.some((version) => version.name === name)) return `A version named '${name}' already exists.`
  if (text.trim() === '') return 'The prompt text is empty.'
  const same = versions.find((version) => version.text === text)
  return same ? `This is the same text as '${same.name}': edit it first.` : null
}

export function runLine(run: PromptRun): string {
  return `Run ${run.id}, Stack ${run.stack}, ${run.split}, ${run.status}, ${run.created_at.slice(0, 10)}`
}

export function runCount(version: PromptVersion): string {
  return version.runs.length === 1 ? '1 run' : `${version.runs.length} runs`
}
