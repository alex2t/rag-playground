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

export type RunSettings = {
  chunking_method: 'fixed' | 'llm_enriched'
  chunk_size: number
  overlap: number
  chunk_set_id: string
  top_k: number
  hybrid: boolean
  openai_ranking: OpenAIRanking | null
  rerank: boolean
  answer_model: string
  prompt_name: string
  temperature_controlled: boolean
}

export type RunSummary = {
  id: number
  created_at: string
  status: 'running' | 'done' | 'failed'
  error: string | null
  stack: StackId
  split: 'dev' | 'heldout'
  questions: number
  full: boolean
  done: number
  job_id: number | null
  job_status: 'queued' | 'running' | null
  settings: RunSettings
}

export type RunScores = {
  mrr: number
  recall: number
  ndcg: number
  hit: number
  keyword_recall: number
  accuracy: number
  completeness: number
  relevance: number
  faithfulness: number
  correct_refusal_rate: number
  false_refusal_rate: number
}

export type CategoryScores = { category: string; questions: number; accuracy: number; completeness: number; relevance: number; faithfulness: number }

export type RunReport = RunSummary & {
  scores: RunScores
  failed_gates: string[]
  cost_per_question: number
  latency_s: number
  categories: CategoryScores[] | null
}

export type PairedChange = Change & { verdict: 'better' | 'worse' | 'no real difference' }

export type MovedQuestion = { test_id: string; category: string; question: string; before: number; after: number }

export type QuestionChanges = { fixed: MovedQuestion[]; broken: MovedQuestion[]; both_pass: number; both_fail: number }

export type Comparison = {
  before: RunReport
  after: RunReport
  change: { accuracy: PairedChange; mrr: PairedChange }
  questions: QuestionChanges | null
}

export type BuildSettings = { chunking_method: 'fixed' | 'llm_enriched'; chunk_size: number; overlap: number }

export type BuildEstimate = { chunk_set_id: string; chunks: number; enrichment_usd: number; built: StackId[]; budget_left_usd: number }

export type BuiltSet = BuildSettings & { stack: StackId; chunk_set_id: string; chunk_count: number; created_at: string }

export type BuildJob = BuildSettings & { id: number; created_at: string; status: Job['status']; stack: StackId; chunk_set_id: string; error: string | null }

export type Builds = { built: BuiltSet[]; jobs: BuildJob[] }

export type SweepValue = number | string | boolean

export type SweepRun = {
  run_id: number
  accuracy: number
  accuracy_ci: [number, number]
  mrr: number
  mrr_ci: [number, number]
  cost_per_question: number
  failed_gates: string[]
  change: { accuracy: PairedChange; mrr: PairedChange } | null
}

export type SweepItem = { value: SweepValue; base: boolean; chunk_set_id: string; built: boolean; run: SweepRun | null; estimate_usd: number | null }

export type SweepPlan = {
  stack: StackId
  variable: string
  items: SweepItem[]
  runs_to_do: number
  estimate_usd: number
  budget_left_usd: number
}

export type OpsJob = { id: number; created_at: string; kind: string; stack: StackId | null; status: 'failed'; error: string; cause: 'fault' | 'budget' | 'restart' }

export type OpsSummary = {
  window_days: number
  budget: { budget_usd: number; spent_usd: number; left_usd: number; in_runs_usd: number; outside_runs_usd: number }
  jobs: { finished: number; active: number; faults: number; budget_stops: number; restarts: number; error_rate: number | null; failed: OpsJob[] }
  latency: { stack: StackId; questions: number; p50_s: number; p95_s: number }[]
  version: string
  qdrant: string
}

export type Estimate = { questions: number; estimate_usd: number; seconds: number; budget_left_usd: number }

export type QuestionSet = 'dev' | 'heldout' | 'smoke'

export type Job = {
  id: number
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed'
  run_id: number | null
  progress: number
  message: string
  error: string | null
}
