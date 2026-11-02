/** Typed calls to the backend. A refused request throws its reason, as the API words it. */

import type { Answer, AskQuestion, AskResult, Comparison, Estimate, Job, LadderState, PanelOptions, PanelRequest, PromptVersion, QuestionSet, RunReport, RunSummary, StackId } from './types.ts'

/** The API's reason, or a line with the status: a crash or a proxy answers in plain text, not JSON. */
export function refusal(status: number, text: string): string {
  try {
    const { detail } = JSON.parse(text)
    if (typeof detail === 'string') return detail
  } catch {
    return `The server failed (${status}).`
  }
  return `Request refused (${status})`
}

async function send<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  const text = await response.text()
  if (!response.ok) throw new Error(refusal(response.status, text))
  return JSON.parse(text)
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

export function getPrompts(): Promise<PromptVersion[]> {
  return send('/api/prompts')
}

export function savePrompt(name: string, text: string): Promise<Omit<PromptVersion, 'runs'>> {
  return post('/api/prompts', { name, text })
}

export function getPanel(): Promise<PanelOptions> {
  return send('/api/panel')
}

export function getAskQuestions(): Promise<AskQuestion[]> {
  return send('/api/ask/questions')
}

export function ask(settings: PanelRequest, question: { question: string } | { test_id: string }): Promise<AskResult> {
  return post('/api/ask', { ...settings, ...question })
}

export function getRuns(): Promise<RunSummary[]> {
  return send('/api/runs')
}

export function getReport(runId: number): Promise<RunReport> {
  return send(`/api/runs/${runId}/report`)
}

export function getComparison(before: number, after: number): Promise<Comparison> {
  return send(`/api/compare?before=${before}&after=${after}`)
}

export function estimateRun(settings: PanelRequest, questions: QuestionSet): Promise<Estimate> {
  return post('/api/runs/estimate', { ...settings, questions })
}

export async function startRun(settings: PanelRequest, questions: QuestionSet): Promise<number> {
  return (await post<{ job_id: number }>('/api/runs', { ...settings, questions })).job_id
}

export async function startStep(stack: StackId, prompts?: string[]): Promise<number> {
  return (await post<{ job_id: number }>('/api/story', { stack, prompts })).job_id
}

export async function startHeldout(stack: StackId): Promise<number> {
  return (await post<{ job_id: number }>(`/api/story/${stack}/heldout`)).job_id
}
