/** The API's Story responses (backend story.py). */

export type StackId = 'A' | 'B'

export type Config = {
  chunk_size: number
  overlap: number
  top_k: number
  answer_model: string
  prompt_name: string
  method: string
  rerank: boolean
}

export type Option = {
  config: Config
  kept: boolean
  run_id: number
  accuracy: number
  mrr: number
  cost_per_question: number
  failed_gates: string[]
}

export type Step = { step: string; kept: Config; tried: Option[] }

export type Change = { low: number; high: number; real: boolean }

export type Heldout = {
  runs: Option[]
  missing: Config[]
  estimate_usd: number
  gain: { accuracy: Change; mrr: Change } | null
}

export type LadderState = {
  stack: StackId
  steps: Step[]
  next_step: string | null
  needs_prompts: boolean
  missing: Config[]
  estimate_usd: number
  enrichment_usd: number
  budget_left_usd: number
  job_id: number | null
  last_error: string | null
  saved_prompts: string[] | null
  heldout: Heldout | null
}

export type Job = {
  id: number
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed'
  run_id: number | null
  progress: number
  message: string
  error: string | null
}
