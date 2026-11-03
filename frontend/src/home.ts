/** Pure logic of the Home page (D31 Q2). */

import type { RunSummary } from './api/types.ts'
import type { Page } from './route.ts'

export type Need = { want: string; page: Page; cost: string }

/** "Which page do I need?": each task, its page and what it costs. Costs are the measured baseline ones; every paid
 * page shows its exact estimate before anything is spent. */
export const NEEDS: Need[] = [
  { want: 'See how the system answers one question', page: 'Ask', cost: 'under 1 cent' },
  { want: 'Measure one set-up on many questions', page: 'Evaluate', cost: 'Stack B about $0.02 (smoke test) or $0.23 (192 dev questions); Stack A about $0.08 or $0.72, its search fee included' },
  { want: 'Know whether one set-up beats another', page: 'Compare', cost: 'free: it reads finished runs' },
  { want: 'See how the values of one setting change the scores', page: 'Sweep', cost: 'one dev run per value not run yet' },
  { want: 'Run the study, one fixed step at a time', page: 'Story', cost: 'one or more dev runs per step' },
  { want: 'Write new instructions for the answer model', page: 'Prompt', cost: 'free to save; tested on Evaluate' },
  { want: 'Cut the documents into chunks of a new size', page: 'Build', cost: 'free, except LLM-enriched chunks' },
  { want: 'Check spend and failures', page: 'Ops', cost: 'free' },
]

export type Step = { page: Page; title: string; text: string }

/** The usual path through the app, in order. */
export const PATH: Step[] = [
  { page: 'Build', title: 'Build', text: 'Cut the 48 documents into chunks and store them on a stack.' },
  { page: 'Ask', title: 'Ask', text: 'Try one question and see the chunks the answer came from.' },
  { page: 'Evaluate', title: 'Evaluate', text: 'Score a set-up on the test questions, graded by a judge model.' },
  { page: 'Compare', title: 'Compare', text: 'Check whether a change really helped, or was chance.' },
]

/** The newest run that finished, for the "latest result" link, or null. */
export function latestFinished(runs: RunSummary[]): RunSummary | null {
  return runs.find((run) => run.status === 'done') ?? null
}
