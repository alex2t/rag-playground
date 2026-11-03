import { useEffect, useState } from 'react'
import { getPrompts, savePrompt } from '../api/client.ts'
import type { PromptVersion } from '../api/types.ts'
import Guide from '../components/Guide.tsx'
import { runCount, runLine, saveProblem } from '../prompts.ts'
import { pageLink } from '../route.ts'

const LONG_NAME = '[overflow-wrap:anywhere]'

const STEPS = [
  'Pick the version to start from under Saved versions. The default is the one the study uses from S0 to S5.',
  'Edit the text in the editor.',
  'Type a new name and press Save new version. A saved version never changes: to change it, save another one.',
  'Test it: Test on Evaluate opens Evaluate with this version chosen and the 20-question smoke test selected (about $0.02 per stack, shown before you pay). Try on Ask asks one question with it.',
  'For the study\'s prompt step (S6 on Story), type the names of up to 4 versions there.',
]

function VersionList({ versions, selected, onPick }: { versions: PromptVersion[]; selected: PromptVersion; onPick: (version: PromptVersion) => void }) {
  return (
    <nav aria-label="Saved versions" className="min-w-0 self-start card p-3">
      <h2 className="px-2 pb-2 font-semibold">Saved versions</h2>
      {versions.map((version) => (
        <button key={version.name} type="button" aria-current={version.name === selected.name}
          className={`block w-full rounded-lg px-3 py-2 text-left text-sm ${version.name === selected.name ? 'bg-accent-soft font-semibold text-accent-text' : 'hover:bg-page'}`}
          onClick={() => onPick(version)}>
          <span className={`block ${LONG_NAME}`}>{version.name}</span>
          <span className="block text-xs font-normal text-muted">{runCount(version)}</span>
        </button>
      ))}
    </nav>
  )
}

function TestVersion({ version, edited }: { version: PromptVersion; edited: boolean }) {
  return (
    <section aria-label="Test this version" className="min-w-0 space-y-3 card p-5">
      <h2 className={`font-semibold ${LONG_NAME}`}>Test '{version.name}'</h2>
      {edited && <p className="text-sm text-warn">Your edits are not saved: these buttons test the saved text of this version. Save first to test your edits.</p>}
      <div className="flex flex-wrap gap-2">
        <a className="btn-primary text-sm" href={pageLink('Evaluate', { prompt: version.name, questions: 'smoke' })}>Test on Evaluate</a>
        <a className="btn text-sm" href={pageLink('Ask', { prompt: version.name })}>Try on Ask</a>
      </div>
      {version.runs.length === 0 && <p className="text-sm text-muted">No run has used this version yet.</p>}
      {version.runs.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Runs that used it ({version.runs.length})</h3>
          <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto text-sm">
            {version.runs.map((run) => (
              <li key={run.id} className="flex items-center justify-between gap-2 border-t border-line pt-1">
                <span className="text-muted">{runLine(run)}</span>
                <a className="btn shrink-0 px-2 py-0.5 text-xs" href={pageLink('Evaluate', { run: String(run.id) })}>Open</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** Saved system prompt versions (T36): start from one, edit its text, save it under a new name, then test it. */
export default function Prompt() {
  const [versions, setVersions] = useState<PromptVersion[] | null>(null)
  const [selectedName, setSelectedName] = useState('default')
  const [text, setText] = useState('')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPrompts().then((all) => {
      setVersions(all)
      setText(all[0].text)
    }).catch((e: Error) => setError(e.message))
  }, [])

  if (error && versions === null) return <p role="alert" className="text-sm text-danger">{error}</p>
  if (versions === null) return <p className="text-sm text-muted">Loading...</p>

  const selected = versions.find((version) => version.name === selectedName) ?? versions[0]
  const problem = saveProblem(name, text, versions)

  function pick(version: PromptVersion) {
    if (text !== selected.text && !confirm('Your edits have not been saved. Discard them?')) return
    setSelectedName(version.name)
    setText(version.text)
    setSaved(null)
  }

  async function save() {
    setSaving(true)
    setError(null)
    setSaved(null)
    try {
      await savePrompt(name, text)
      setVersions(await getPrompts())
      setSelectedName(name)
      setName('')
      setSaved(`Saved '${name}'. Test it below.`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prompt</h1>
        <p className="text-muted">Write your own instructions for the answer model, then test them.</p>
      </div>
      <Guide page="Prompt" steps={STEPS}
        purpose="The system prompt tells the answer model how to answer: use only the retrieved passages, say when it cannot answer, and so on. Changing it is one of the study's steps (S6)." />
      <div className="grid gap-5 md:grid-cols-[16rem_minmax(0,1fr)]">
        <VersionList versions={versions} selected={selected} onPick={pick} />
        <div className="min-w-0 space-y-5">
          <section aria-label="Edit a version" className="min-w-0 space-y-3 card p-5">
            <h2 className={`font-semibold ${LONG_NAME}`}>Editor: starting from '{selected.name}'</h2>
            <label className="block text-sm">
              System prompt
              <textarea rows={16} className="mt-1 field font-mono text-sm leading-relaxed" value={text}
                onChange={(e) => setText(e.target.value)} />
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <label className="block min-w-0 flex-1 text-sm">
                New version name
                <input className="mt-1 field" value={name} placeholder="for example strict-v1"
                  onChange={(e) => setName(e.target.value)} />
              </label>
              <button type="button" className="btn-primary text-sm"
                disabled={saving || problem !== null} onClick={() => void save()}>Save new version</button>
            </div>
            <p className="text-sm text-muted">{problem ?? 'Ready to save. A saved version never changes.'}</p>
            {saved && <p role="status" className={`text-sm font-medium text-good ${LONG_NAME}`}>{saved}</p>}
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          </section>
          <TestVersion version={selected} edited={text !== selected.text} />
        </div>
      </div>
    </div>
  )
}
