/** Pure logic of the shared settings panel (T35): the API's limits come from GET /api/panel. */

import type { OpenAIRanking, PanelOptions, PanelRequest, StackId } from './api/types.ts'

export type StackChoice = StackId | 'both'

export type PanelValues = PanelOptions['start'] & { stacks: StackChoice; prompt_name: string }

export const DEFAULT_PROMPT = 'default'
const STORE_KEY = 'rag-playground-panel'

export function stacksOf(choice: StackChoice): StackId[] {
  return choice === 'both' ? ['A', 'B'] : [choice]
}

export function startValues(options: PanelOptions): PanelValues {
  return { ...options.start, stacks: 'both', prompt_name: DEFAULT_PROMPT }
}

function parsed(saved: string | null): Partial<PanelValues> {
  try {
    return JSON.parse(saved ?? '{}') ?? {}
  } catch {
    return {}
  }
}

/** The last values used, or the start. Storage can hold what the panel would refuse: a box left blank on a hidden
 * stack is saved as null. A model, prompt or Stack A setting not usable now falls back to the start's; so does
 * everything if the rest cannot be sent. */
export function restoredValues(saved: string | null, options: PanelOptions, promptNames: string[]): PanelValues {
  const start = startValues(options)
  const stored = parsed(saved)
  const { ranker, embedding_weight, text_weight, score_threshold } = { ...start.openai_ranking, ...stored.openai_ranking }
  const ranking = { ranker, embedding_weight, text_weight, score_threshold }
  const values: PanelValues = {
    ...start,
    ...stored,
    openai_ranking: rankingProblem(ranking) ? start.openai_ranking : ranking,
    answer_model: stored.answer_model && options.answer_models.includes(stored.answer_model) ? stored.answer_model : start.answer_model,
    prompt_name: stored.prompt_name && promptNames.includes(stored.prompt_name) ? stored.prompt_name : start.prompt_name,
  }
  return panelProblem(values, options) ? start : values
}

/** The values with the prompt a link asked for, if that version exists; otherwise unchanged. */
export function withPrompt(values: PanelValues, name: string, promptNames: string[]): PanelValues {
  return promptNames.includes(name) ? { ...values, prompt_name: name } : values
}

export function loadSaved(): string | null {
  try {
    return localStorage.getItem(STORE_KEY)
  } catch {
    return null
  }
}

export function saveValues(values: PanelValues): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(values))
  } catch {
    /* blocked storage only loses the convenience */
  }
}

function within(value: number, low: number, high: number): boolean {
  return Number.isInteger(value) && value >= low && value <= high
}

function rankingProblem({ embedding_weight, text_weight, score_threshold }: OpenAIRanking): string | null {
  if (![embedding_weight, text_weight].every((weight) => Number.isFinite(weight) && weight >= 0)) return 'The Stack A weights must be 0 or more.'
  return Number.isFinite(score_threshold) && score_threshold >= 0 && score_threshold <= 1 ? null : 'The Stack A score threshold must be from 0 to 1.'
}

/** Why a chunk size and overlap cannot be sent, or null (T35 ranges). Shared by the settings panel and Build. */
export function chunkProblem({ chunk_size, overlap }: { chunk_size: number; overlap: number }, options: PanelOptions): string | null {
  const { min_chunk_size: low, max_chunk_size: high, max_overlap_share: share } = options
  if (!within(chunk_size, low, high)) return `Chunk size must be a whole number from ${low} to ${high}.`
  const maxOverlap = Math.floor(chunk_size * share)
  return within(overlap, 0, maxOverlap) ? null : `Overlap must be a whole number from 0 to ${maxOverlap}.`
}

/** Why these values cannot be sent yet, or null. The API checks them again; this says why in plain words. */
export function panelProblem(values: PanelValues, options: PanelOptions): string | null {
  const chunks = chunkProblem(values, options)
  if (chunks) return chunks
  if (!within(values.top_k, 1, options.max_top_k)) return `Top-K must be a whole number from 1 to ${options.max_top_k}.`
  return stacksOf(values.stacks).includes('A') ? rankingProblem(values.openai_ranking) : null
}

/** The settings of one stack's request: each stack sends its own search settings and never the other's (T40). */
export function requestFor(values: PanelValues, stack: StackId): PanelRequest {
  const { chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name } = values
  const search = stack === 'A' ? { openai_ranking: values.openai_ranking } : { hybrid: values.hybrid }
  return { stack, chunking_method, chunk_size, overlap, top_k, rerank, answer_model, prompt_name, ...search }
}

/** A stack's own search settings in a few words (T12, T40). */
export function searchLine(request: PanelRequest): string {
  if (request.openai_ranking) {
    const { ranker, embedding_weight, text_weight, score_threshold } = request.openai_ranking
    const label = ranker === 'auto' ? 'OpenAI ranker on' : 'ranker none'
    return `${label}, weights ${embedding_weight}:${text_weight}, threshold ${score_threshold}`
  }
  return request.hybrid ? 'hybrid on' : 'hybrid off'
}

/** Every setting behind an answer, in one line (a result always states its search settings, T12). */
export function settingsLine(request: PanelRequest): string {
  return [`Stack ${request.stack}`, `${request.chunk_size} tokens`, `overlap ${request.overlap}`, request.chunking_method,
    `K=${request.top_k}`, searchLine(request), request.rerank ? 'reranked' : 'no reranking', request.answer_model,
    `prompt ${request.prompt_name}`].join(', ')
}
