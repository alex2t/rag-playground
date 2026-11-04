import { useEffect, useState } from 'react'
import { ask, getAskQuestions } from '../api/client.ts'
import type { AskQuestion, AskResult, StackId } from '../api/types.ts'
import { useBuilds } from '../api/useBuilds.ts'
import { usePanel } from '../api/usePanel.ts'
import { byCategory, filtered, questionBody } from '../ask.ts'
import { chunksProblem } from '../chunks.ts'
import AskResultCard from '../components/AskResultCard.tsx'
import Guide from '../components/Guide.tsx'
import { InfoLabel } from '../components/Info.tsx'
import { HELP } from '../help.ts'
import PageTitle from '../components/PageTitle.tsx'
import SettingsPanel from '../components/SettingsPanel.tsx'
import { panelProblem, requestFor, saveValues, settingsLine, stacksOf, type PanelValues } from '../panel.ts'
import { linkedParam, linkedTest } from '../route.ts'

type Reply = { stack: StackId; line: string; result?: AskResult; error?: string }

function QuestionBox({ questions, typed, testId, onType, onPick }: {
  questions: AskQuestion[]
  typed: string
  testId: string
  onType: (text: string) => void
  onPick: (id: string) => void
}) {
  const [filter, setFilter] = useState('')
  const shown = filtered(questions, filter, testId)
  return (
    <>
      <div>
        <InfoLabel label="Your question" info={HELP.typed} htmlFor="ask-typed" />
        <textarea id="ask-typed" rows={3} className="mt-1 field" value={typed}
          onChange={(e) => onType(e.target.value)} />
      </div>
      <div>
        <InfoLabel label={`Or a test question (${questions.length})`} info={HELP.test} htmlFor="ask-test" />
        <input type="search" aria-label="Filter the test questions" placeholder="Filter by words or category"
          className="mt-1 field" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select id="ask-test" className="mt-2 field" value={testId} onChange={(e) => onPick(e.target.value)}>
          <option value="">{filter.trim() ? `None (${shown.length} match)` : 'None'}</option>
          {byCategory(shown).map(([category, items]) => (
            <optgroup key={category} label={category}>
              {items.map((item) => <option key={item.id} value={item.id}>{item.question}</option>)}
            </optgroup>
          ))}
        </select>
      </div>
    </>
  )
}

/** Where each stack's answer comes from: always shown, unlike the guide, which can be closed. */
function Sources() {
  return (
    <section aria-label="Where the answers come from" className="card p-4 text-sm">
      <p>Both stacks search the <strong>same chunks</strong> of the same 48 documents, and the <strong>same answer model</strong> writes
        the answer from what was found. Only the search engine differs:</p>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        <li className="rounded-md border border-line p-2"><span className="font-semibold text-stack-a">Stack A</span>: OpenAI's vector store, run by OpenAI.</li>
        <li className="rounded-md border border-line p-2"><span className="font-semibold text-stack-b">Stack B</span>: nomic embeddings in Qdrant, run by this app.</li>
      </ul>
    </section>
  )
}

function ReplyCard({ reply }: { reply: Reply }) {
  return (
    <section aria-label={`Stack ${reply.stack}`} className="min-w-0 card p-4">
      <h3 className="mb-2 font-semibold">Stack {reply.stack}</h3>
      {reply.result
        ? <AskResultCard line={reply.line} result={reply.result} />
        : <><p className="mb-1 text-sm text-muted">{reply.line}</p><p role="alert" className="text-sm text-danger">{reply.error}</p></>}
    </section>
  )
}

/** One question with the panel's settings (T54), on one stack or both side by side. */
const STEPS = [
  'Choose the settings in the Settings box: the stack, the chunks, how many to search (top-K), the answer model and the prompt.',
  'Type your own question, or pick one of the test questions.',
  'Press Ask. The answer shows with the chunks it was given, its time and its cost.',
  'For a test question you also see the reference answer, the documents that hold it (highlighted where they were found) and the judge\'s scores. A question you type has no reference answer, so it gets no scores.',
]

export default function Ask() {
  const { options, promptNames, values, setValues, error: panelError } = usePanel(linkedParam(location.hash, 'prompt'))
  const { builds } = useBuilds()
  const [questions, setQuestions] = useState<AskQuestion[]>([])
  const [typed, setTyped] = useState('')
  const [testId, setTestId] = useState(linkedTest(location.hash))
  const [asking, setAsking] = useState(false)
  const [replies, setReplies] = useState<Reply[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAskQuestions().then(setQuestions).catch((e: Error) => setError(e.message))
  }, [])

  if (error ?? panelError) return <p role="alert" className="text-sm text-danger">{error ?? panelError}</p>
  if (options === null || values === null) return <p className="text-sm text-muted">Loading...</p>

  const body = questionBody(typed, testId)
  const problem = panelProblem(values, options) ?? chunksProblem(builds?.built ?? null, values)
    ?? (body ? null : 'Type a question or pick a test question.')

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
    <div className="space-y-5">
      <PageTitle title="Ask" about="Try one question and see the passages the answer came from." />
      <Guide page="Ask" steps={STEPS}
        purpose="See how one set-up answers one question, and which passages of the documents it read to answer."
        note="Each question runs at once, without an estimate: it costs under half a cent (about $0.001 on Stack B, $0.004 on Stack A with its search fee)." />
      <Sources />
      <div className="grid gap-5 md:grid-cols-[22rem_minmax(0,1fr)]">
        <SettingsPanel values={values} options={options} promptNames={promptNames} built={builds?.built ?? null} onChange={setValues} />
        <div className="min-w-0 space-y-5">
        <section aria-label="Question" className="min-w-0 space-y-3 card p-4">
          <QuestionBox questions={questions} typed={typed} testId={testId}
            onType={(text) => { setTyped(text); setTestId('') }}
            onPick={(id) => { setTestId(id); setTyped('') }} />
          <button type="button" className="btn-primary text-sm"
            disabled={asking || problem !== null} onClick={() => void send(values, body!)}>{asking ? 'Asking...' : 'Ask'}</button>
          {problem && <p className="text-sm text-muted">{problem}</p>}
        </section>
        {replies.length > 0 && (
          <div className={`grid gap-4 ${replies.length > 1 ? 'xl:grid-cols-2' : ''}`}>
            {replies.map((reply) => <ReplyCard key={reply.stack} reply={reply} />)}
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
