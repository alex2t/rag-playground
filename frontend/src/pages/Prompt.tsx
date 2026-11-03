import { useEffect, useState } from 'react'
import { getPrompts, savePrompt } from '../api/client.ts'
import type { PromptVersion } from '../api/types.ts'
import { runCount, runLine, saveProblem } from '../prompts.ts'

const LONG_NAME = '[overflow-wrap:anywhere]'

function VersionList({ versions, selected, onPick }: { versions: PromptVersion[]; selected: PromptVersion; onPick: (version: PromptVersion) => void }) {
  return (
    <nav aria-label="Saved versions" className="min-w-0 card p-2">
      {versions.map((version) => (
        <button key={version.name} type="button" aria-current={version.name === selected.name}
          className={`block w-full rounded px-2 py-1 text-left text-sm ${version.name === selected.name ? 'bg-page font-medium' : ''}`}
          onClick={() => onPick(version)}>
          <span className={`block ${LONG_NAME}`}>{version.name}</span>
          <span className="block font-normal text-muted">{runCount(version)}</span>
        </button>
      ))}
    </nav>
  )
}

function RunsUsing({ version }: { version: PromptVersion }) {
  if (version.runs.length === 0) return <p className="text-sm text-muted">No run has used this version.</p>
  return (
    <details className="text-sm">
      <summary className="cursor-pointer">Runs that used this version ({version.runs.length})</summary>
      <ul className="mt-1 max-h-48 overflow-y-auto text-muted">
        {version.runs.map((run) => <li key={run.id}>{runLine(run)}</li>)}
      </ul>
    </details>
  )
}

/** Saved system prompt versions (T36): start from one, edit its text, save it under a new name. */
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
      setSaved(`Saved '${name}'.`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-[16rem_minmax(0,1fr)]">
      <VersionList versions={versions} selected={selected} onPick={pick} />
      <section aria-label="Edit a version" className="min-w-0 space-y-3 card p-4">
        <h2 className={`font-semibold ${LONG_NAME}`}>Starting from {selected.name}</h2>
        <RunsUsing version={selected} />
        <label className="block text-sm">
          System prompt
          <textarea rows={14} className="mt-1 field" value={text}
            onChange={(e) => setText(e.target.value)} />
        </label>
        <label className="block text-sm">
          New version name
          <input className="mt-1 field" value={name}
            onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="button" className="btn-primary text-sm"
          disabled={saving || problem !== null} onClick={() => void save()}>Save new version</button>
        <p className="text-sm text-muted">{problem ?? 'A saved version never changes.'}</p>
        {saved && <p role="status" className={`text-sm ${LONG_NAME}`}>{saved}</p>}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      </section>
    </div>
  )
}
