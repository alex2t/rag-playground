import { useId, type ReactNode } from 'react'
import type { BuiltSet, OpenAIRanking, PanelOptions } from '../api/types.ts'
import { missingStacks } from '../build.ts'
import { byMethod, choiceLabel, chunkChoices, chunkKey, fromKey, METHOD_LABEL, missingLine } from '../chunks.ts'
import { HELP } from '../help.ts'
import { stacksOf, type PanelValues, type StackChoice } from '../panel.ts'
import { hashOf } from '../route.ts'
import { InfoLabel } from './Info.tsx'

const BOX = 'mt-1 field'

function Field({ label, info, children }: { label: string; info: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return <div><InfoLabel label={label} info={info} htmlFor={id} />{children(id)}</div>
}

function NumberField({ label, info, value, step = 1, onChange }: { label: string; info: string; value: number; step?: number; onChange: (value: number) => void }) {
  return (
    <Field label={label} info={info}>
      {(id) => <input id={id} type="number" step={step} className={BOX} value={Number.isNaN(value) ? '' : value}
        onChange={(e) => onChange(e.target.valueAsNumber)} />}
    </Field>
  )
}

function Switch({ label, info, on, onChange }: { label: string; info: string; on: boolean; onChange: (on: boolean) => void }) {
  const id = useId()
  return (
    <InfoLabel label={label} info={info} htmlFor={id}>
      <input id={id} type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} />
    </InfoLabel>
  )
}

function StackASearch({ ranking, onChange }: { ranking: OpenAIRanking; onChange: (ranking: OpenAIRanking) => void }) {
  const change = (part: Partial<OpenAIRanking>) => onChange({ ...ranking, ...part })
  return (
    <fieldset className="grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
      <legend className="pr-2 text-sm font-medium">Stack A search</legend>
      <Field label="Ranker" info={HELP.ranker}>
        {(id) => (
          <select id={id} className={BOX} value={ranking.ranker} onChange={(e) => change({ ranker: e.target.value as OpenAIRanking['ranker'] })}>
            <option value="auto">auto</option>
            <option value="none">none</option>
          </select>
        )}
      </Field>
      <NumberField label="Score threshold" info={HELP.threshold} step={0.05} value={ranking.score_threshold} onChange={(score_threshold) => change({ score_threshold })} />
      <NumberField label="Semantic weight" info={HELP.semantic} step={0.1} value={ranking.embedding_weight} onChange={(embedding_weight) => change({ embedding_weight })} />
      <NumberField label="Keyword weight" info={HELP.keyword} step={0.1} value={ranking.text_weight} onChange={(text_weight) => change({ text_weight })} />
      {ranking.ranker === 'auto' && <p className="text-sm text-muted sm:col-span-2">Ranker auto is OpenAI's own re-ranking; the weights have no measured effect with it.</p>}
    </fieldset>
  )
}

/** The chunk set, picked among those already built; a set chosen before but not built is shown as such. */
function ChunkSelect({ values, built, onChange }: { values: PanelValues; built: BuiltSet[]; onChange: (part: Partial<PanelValues>) => void }) {
  const choices = chunkChoices(built)
  const current = chunkKey(values)
  const known = choices.some((choice) => chunkKey(choice) === current)
  const missing = missingLine(missingStacks(built, values))
  return (
    <Field label="Chunks" info={HELP.chunks}>
      {(id) => (
        <>
          <select id={id} className={BOX} value={current} onChange={(e) => onChange(fromKey(e.target.value))}>
            {!known && <option value={current} disabled>{values.chunk_size} / {values.overlap} tokens, not built</option>}
            {byMethod(choices).map(([method, items]) => (
              <optgroup key={method} label={METHOD_LABEL[method]}>
                {items.map((choice) => <option key={chunkKey(choice)} value={chunkKey(choice)}>{choiceLabel(choice)}</option>)}
              </optgroup>
            ))}
          </select>
          {missing && <p role="alert" className="mt-1.5 text-sm text-warn">{missing}</p>}
          <a href={hashOf('Build')} className="mt-1 inline-block text-sm text-accent-text underline-offset-2 hover:underline">Build a new chunk set</a>
        </>
      )}
    </Field>
  )
}

type Props = { values: PanelValues; options: PanelOptions; promptNames: string[]; built: BuiltSet[] | null; onChange: (values: PanelValues) => void }

/** The settings shared by Ask, Evaluate and Sweep (T35). Each stack shows its own search settings (T40). */
export default function SettingsPanel({ values, options, promptNames, built, onChange }: Props) {
  const change = (part: Partial<PanelValues>) => onChange({ ...values, ...part })
  const stacks = stacksOf(values.stacks)
  return (
    <section aria-label="Settings" className="min-w-0 space-y-3 card p-4">
      <h2 className="font-semibold">Settings</h2>
      <Field label="Stack" info={HELP.stack}>
        {(id) => (
          <select id={id} className={BOX} value={values.stacks} onChange={(e) => change({ stacks: e.target.value as StackChoice })}>
            <option value="both">Both side by side</option>
            <option value="A">Stack A (OpenAI)</option>
            <option value="B">Stack B (Qdrant)</option>
          </select>
        )}
      </Field>
      {built === null ? <p className="text-sm text-muted">Loading the chunk sets...</p> : <ChunkSelect values={values} built={built} onChange={change} />}
      <NumberField label={`Top-K (1 to ${options.max_top_k})`} info={HELP.topK} value={values.top_k} onChange={(top_k) => change({ top_k })} />
      {stacks.includes('A') && <StackASearch ranking={values.openai_ranking} onChange={(openai_ranking) => change({ openai_ranking })} />}
      <div className="space-y-3 border-t border-line pt-3">
        {stacks.includes('B') && <Switch label="Stack B hybrid search" info={HELP.hybrid} on={values.hybrid} onChange={(hybrid) => change({ hybrid })} />}
        <Switch label="Reranking" info={HELP.rerank} on={values.rerank} onChange={(rerank) => change({ rerank })} />
      </div>
      <Field label="Answer model" info={HELP.answerModel}>
        {(id) => (
          <select id={id} className={BOX} value={values.answer_model} onChange={(e) => change({ answer_model: e.target.value })}>
            {options.answer_models.map((model) => <option key={model}>{model}</option>)}
          </select>
        )}
      </Field>
      <Field label="System prompt version" info={HELP.prompt}>
        {(id) => (
          <select id={id} className={BOX} value={values.prompt_name} onChange={(e) => change({ prompt_name: e.target.value })}>
            {promptNames.map((name) => <option key={name}>{name}</option>)}
          </select>
        )}
      </Field>
    </section>
  )
}
