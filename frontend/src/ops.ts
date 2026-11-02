/** Pure logic of the Ops page (D30). */

import type { OpsJob, OpsSummary } from './api/types.ts'
import { money } from './story.ts'

export type Tone = 'good' | 'warn' | 'bad'

export function budgetLine({ budget }: OpsSummary): string {
  return `${money(budget.spent_usd)} spent of ${money(budget.budget_usd)}`
}

/** What is left, said plainly when spend has passed the budget: new paid work is refused until it is raised. */
export function leftLine({ budget }: OpsSummary): string {
  return budget.left_usd < 0 ? `${money(-budget.left_usd)} over the budget: paid work is refused until BUDGET_USD is raised`
    : `${money(budget.left_usd)} left`
}

export function splitLine({ budget }: OpsSummary): string {
  return `Runs ${money(budget.in_runs_usd)}, outside runs (Ask, enrichment) ${money(budget.outside_runs_usd)}`
}

export function budgetTone({ budget }: OpsSummary): Tone {
  return budget.left_usd < 0 ? 'bad' : budget.left_usd < budget.budget_usd * 0.1 ? 'warn' : 'good'
}

export function rateText({ jobs, window_days }: OpsSummary): string {
  if (jobs.error_rate === null) return `No job finished in ${window_days} days`
  return `${Math.round(jobs.error_rate * 100)}% (${jobs.faults} of ${jobs.finished} jobs)`
}

export function rateTone({ jobs }: OpsSummary): Tone {
  return jobs.faults === 0 ? 'good' : 'bad'
}

/** Stops on purpose, counted apart from the rate. */
export function apartLine({ jobs }: OpsSummary): string {
  return `Budget stops ${jobs.budget_stops}, cut off by a restart ${jobs.restarts}, waiting or running ${jobs.active}`
}

const CAUSES: Record<OpsJob['cause'], string> = { fault: 'fault', budget: 'budget stop', restart: 'app restart' }

export function failureLine(job: OpsJob): string {
  const what = job.stack ? `${job.kind} on Stack ${job.stack}` : job.kind
  return `${job.created_at.slice(0, 16)} UTC, job ${job.id}, ${what}, ${CAUSES[job.cause]}: ${job.error}`
}

export function seconds(value: number): string {
  return `${value.toFixed(1)} s`
}
