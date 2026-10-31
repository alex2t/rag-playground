/** Typed calls to the backend. A refused request throws its reason, as the API words it. */

import type { Answer, Job, LadderState, StackId } from './types.ts'

async function send<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request refused (${response.status})`)
  return body
}

function post<T>(url: string, body?: object): Promise<T> {
  return send(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

export function getLadder(stack: StackId, prompts: string[] = []): Promise<LadderState> {
  const query = new URLSearchParams(prompts.map((name) => ['prompts', name]))
  return send(`/api/story/${stack}?${query}`)
}

export function getJob(id: number): Promise<Job> {
  return send(`/api/jobs/${id}`)
}

export function getAnswers(runId: number): Promise<Answer[]> {
  return send(`/api/runs/${runId}/answers`)
}

export async function startStep(stack: StackId, prompts?: string[]): Promise<number> {
  return (await post<{ job_id: number }>('/api/story', { stack, prompts })).job_id
}

export async function startHeldout(stack: StackId): Promise<number> {
  return (await post<{ job_id: number }>(`/api/story/${stack}/heldout`)).job_id
}
