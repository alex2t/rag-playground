import type { ReactNode } from 'react'
import type { OpenAIRanking, PanelOptions } from '../api/types.ts'
import { stacksOf, type PanelValues, type StackChoice } from '../panel.ts'

const BOX = 'mt-1 w-full rounded border border-line bg-transparent px-2 py-1'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block text-sm">{label}{children}</label>
}

function NumberField({ label, value, step = 1, onChange }: { label: string; value: number; step?: number; onChange: (value: number) => void }) {
  return (
    <Field label={label}>
      <input type="number" step={step} className={BOX} value={Number.isNaN(value) ? '' : value}
        onChange={(e) => onChange(e.target.valueAsNumber)} />
    </Field>
  )
}

function Switch({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />{label}
    </label>
  )
}

function StackASearch({ ranking, onChange }: { ranking: OpenAIRanking; onChange: (ranking: OpenAIRanking) => void }) {
  const change = (part: Partial<OpenAIRanking>) => onChange({ ...ranking, ...part })
  return (
    <fieldset className="grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
      <legend className="pr-2 text-sm font-medium">Stack A search</legend>
      <Field label="Ranker">
        <select className={BOX} value={ranking.ranker} onChange={(e) => change({ ranker: e.target.value as OpenAIRanking['ranker'] })}>
          <option value="auto">auto</option>
          <option value="none">none</option>
        </select>
      </Field>
      <NumberField label="Score threshold (0 to 1)" step={0.05} value={ranking.score_threshold} onChange={(score_threshold) => change({ score_threshold })} />
      <NumberField label="Semantic weight" step={0.1} value={ranking.embedding_weight} onChange={(embedding_weight) => change({ embedding_weight })} />
      <NumberField label="Keyword weight" step={0.1} value={ranking.text_weight} onChange={(text_weight) => change({ text_weight })} />
      {ranking.ranker === 'auto' && <p className="text-sm text-muted sm:col-span-2">Ranker auto is OpenAI's own re-ranking; the weights have no measured effect with it.</p>}
    </fieldset>
  )
}

type Props = { values: PanelValues; options: PanelOptions; promptNames: string[]; onChange: (values: PanelValues) => void }

/** The settings shared by Ask, Evaluate and Sweep (T35). Each stack shows its own search settings (T40). */
export default function SettingsPanel({ values, options, promptNames, onChange }: Props) {
  const change = (part: Partial<PanelValues>) => onChange({ ...values, ...part })
  const stacks = stacksOf(values.stacks)
  return (
    <section aria-label="Settings" className="min-w-0 space-y-3 rounded-lg border border-line bg-panel p-4">
      <h2 className="font-semibold">Settings</h2>
      <Field label="Stack">
        <select className={BOX} value={values.stacks} onChange={(e) => change({ stacks: e.target.value as StackChoice })}>
          <option value="both">Both side by side</option>
          <option value="A">Stack A</option>
          <option value="B">Stack B</option>
        </select>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <NumberField label={`Chunk size (${options.min_chunk_size} to ${options.max_chunk_size})`} value={values.chunk_size} onChange={(chunk_size) => change({ chunk_size })} />
        <NumberField label="Overlap (tokens)" value={values.overlap} onChange={(overlap) => change({ overlap })} />
        <Field label="Chunking method">
          <select className={BOX} value={values.chunking_method} onChange={(e) => change({ chunking_method: e.target.value as PanelValues['chunking_method'] })}>
            <option value="fixed">fixed</option>
            <option value="llm_enriched">llm_enriched</option>
          </select>
        </Field>
        <NumberField label={`Top-K (1 to ${options.max_top_k})`} value={values.top_k} onChange={(top_k) => change({ top_k })} />
      </div>
      {stacks.includes('A') && <StackASearch ranking={values.openai_ranking} onChange={(openai_ranking) => change({ openai_ranking })} />}
      {stacks.includes('B') && <Switch label="Stack B hybrid search" on={values.hybrid} onChange={(hybrid) => change({ hybrid })} />}
      <Switch label="Reranking" on={values.rerank} onChange={(rerank) => change({ rerank })} />
      <Field label="Answer model">
        <select className={BOX} value={values.answer_model} onChange={(e) => change({ answer_model: e.target.value })}>
          {options.answer_models.map((model) => <option key={model}>{model}</option>)}
        </select>
      </Field>
      <Field label="System prompt version">
        <select className={BOX} value={values.prompt_name} onChange={(e) => change({ prompt_name: e.target.value })}>
          {promptNames.map((name) => <option key={name}>{name}</option>)}
        </select>
      </Field>
    </section>
  )
}
