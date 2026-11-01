import { useEffect, useState } from 'react'
import { ask, getAskQuestions, getPanel, getPrompts } from '../api/client.ts'
import type { AskQuestion, AskResult, PanelOptions, StackId } from '../api/types.ts'
import { byCategory, questionBody } from '../ask.ts'
import AskResultCard from '../components/AskResultCard.tsx'
import SettingsPanel from '../components/SettingsPanel.tsx'
import { loadSaved, panelProblem, requestFor, restoredValues, saveValues, settingsLine, stacksOf, type PanelValues } from '../panel.ts'

type Reply = { stack: StackId; line: string; result?: AskResult; error?: string }

function QuestionBox({ questions, typed, testId, onType, onPick }: {
  questions: AskQuestion[]
  typed: string
  testId: string
  onType: (text: string) => void
  onPick: (id: string) => void
}) {
  return (
    <>
      <label className="block text-sm">
        Your question
        <textarea rows={3} className="mt-1 w-full rounded border border-line bg-transparent px-2 py-1" value={typed}
          onChange={(e) => onType(e.target.value)} />
      </label>
      <label className="block text-sm">
        Or a test question
        <select className="mt-1 w-full rounded border border-line bg-transparent px-2 py-1" value={testId} onChange={(e) => onPick(e.target.value)}>
          <option value="">None</option>
          {byCategory(questions).map(([category, items]) => (
            <optgroup key={category} label={category}>
              {items.map((item) => <option key={item.id} value={item.id}>{item.question}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
    </>
  )
}

function ReplyCard({ reply }: { reply: Reply }) {
  return (
    <section aria-label={`Stack ${reply.stack}`} className="min-w-0 rounded-lg border border-line bg-panel p-4">
      <h3 className="mb-2 font-semibold">Stack {reply.stack}</h3>
      {reply.result
        ? <AskResultCard line={reply.line} result={reply.result} />
        : <><p className="mb-1 text-sm text-muted">{reply.line}</p><p role="alert" className="text-sm text-danger">{reply.error}</p></>}
    </section>
  )
}

/** One question with the panel's settings (T54), on one stack or both side by side. */
export default function Ask() {
  const [options, setOptions] = useState<PanelOptions | null>(null)
  const [promptNames, setPromptNames] = useState<string[]>([])
  const [questions, setQuestions] = useState<AskQuestion[]>([])
  const [values, setValues] = useState<PanelValues | null>(null)
  const [typed, setTyped] = useState('')
  const [testId, setTestId] = useState('')
  const [asking, setAsking] = useState(false)
  const [replies, setReplies] = useState<Reply[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getPanel(), getPrompts(), getAskQuestions()]).then(([panel, prompts, tests]) => {
      const names = prompts.map((prompt) => prompt.name)
      setOptions(panel)
      setPromptNames(names)
      setQuestions(tests)
      setValues(restoredValues(loadSaved(), panel, names))
    }).catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <p role="alert" className="text-sm text-danger">{error}</p>
  if (options === null || values === null) return <p className="text-sm text-muted">Loading...</p>

  const body = questionBody(typed, testId)
  const problem = panelProblem(values, options) ?? (body ? null : 'Type a question or pick a test question.')

  async function send(current: PanelValues, question: NonNullable<typeof body>) {
    setAsking(true)
    setReplies([])
    saveValues(current)
    const answered = await Promise.all(stacksOf(current.stacks).map(async (stack): Promise<Reply> => {
      const settings = requestFor(current, stack)
      const line = settingsLine(settings)
      try {
        return { stack, line, result: await ask(settings, question) }
      } catch (e) {
        return { stack, line, error: (e as Error).message }
      }
    }))
    setReplies(answered)
    setAsking(false)
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[22rem_minmax(0,1fr)]">
        <SettingsPanel values={values} options={options} promptNames={promptNames} onChange={setValues} />
        <section aria-label="Question" className="min-w-0 space-y-3 self-start rounded-lg border border-line bg-panel p-4">
          <QuestionBox questions={questions} typed={typed} testId={testId}
            onType={(text) => { setTyped(text); setTestId('') }}
            onPick={(id) => { setTestId(id); setTyped('') }} />
          <button type="button" className="rounded bg-accent px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
            disabled={asking || problem !== null} onClick={() => void send(values, body!)}>{asking ? 'Asking...' : 'Ask'}</button>
          {problem && <p className="text-sm text-muted">{problem}</p>}
        </section>
      </div>
      {replies.length > 0 && (
        <div className={`grid gap-4 ${replies.length > 1 ? 'md:grid-cols-2' : ''}`}>
          {replies.map((reply) => <ReplyCard key={reply.stack} reply={reply} />)}
        </div>
      )}
    </div>
  )
}
