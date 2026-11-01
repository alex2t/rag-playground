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
  accuracy_ci: [number, number]
  mrr_ci: [number, number]
  cost_per_question: number
  failed_gates: string[]
}

export type Change = { low: number; high: number; real: boolean }

export type Step = { step: string; kept: Config; change: { accuracy: Change; mrr: Change } | null; tried: Option[] }

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

export type Answer = {
  test_id: string
  category: string
  question: string
  reference_answer: string
  answer: string
  refused: boolean
  accuracy: number
  completeness: number
  relevance: number
  faithfulness: number
  feedback: string
  faithfulness_feedback: string
  chunks: { source: string; text: string }[]
}

export type PromptRun = { id: number; stack: StackId; split: string; status: string; created_at: string }

export type PromptVersion = { name: string; text: string; sha256: string; runs: PromptRun[] }

export type OpenAIRanking = { ranker: 'auto' | 'none'; embedding_weight: number; text_weight: number; score_threshold: number }

export type PanelOptions = {
  min_chunk_size: number
  max_chunk_size: number
  max_overlap_share: number
  max_top_k: number
  answer_models: string[]
  start: {
    chunking_method: 'fixed' | 'llm_enriched'
    chunk_size: number
    overlap: number
    top_k: number
    rerank: boolean
    answer_model: string
    openai_ranking: OpenAIRanking
    hybrid: boolean
  }
}

export type PanelRequest = Omit<PanelOptions['start'], 'openai_ranking' | 'hybrid'> & {
  stack: StackId
  prompt_name: string
  openai_ranking?: OpenAIRanking
  hybrid?: boolean
}

export type AskQuestion = { id: string; category: string; question: string }

export type AskChunk = { rank: number; source: string; score: number; text: string; gold: boolean }

export type AskJudgement = {
  refused: boolean
  accuracy: number
  completeness: number
  relevance: number
  faithfulness: number
  feedback: string
  faithfulness_feedback: string
}

export type AskResult = {
  answer: string
  stack: StackId
  latency_s: number
  cost_usd: number
  temperature_controlled: boolean
  rerank_repaired: boolean
  chunks: AskChunk[]
  reference_answer: string | null
  gold_sources: string[]
  judgement: AskJudgement | null
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
