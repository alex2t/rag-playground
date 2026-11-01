import { useEffect, useState } from 'react'
import { getAnswers } from '../api/client.ts'
import type { Answer } from '../api/types.ts'

function Scores({ item }: { item: Answer }) {
  return (
    <p className="text-muted">
      Accuracy {item.accuracy}, completeness {item.completeness}, relevance {item.relevance}, faithfulness {item.faithfulness}
      {item.refused && ', refused'}
    </p>
  )
}

/** One run's questions, lowest accuracy first: what the system answered and what the judge said. */
export default function AnswersPanel({ runId, onOpen }: { runId: number; onOpen?: (testId: string) => void }) {
  const [answers, setAnswers] = useState<Answer[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAnswers(runId).then(setAnswers).catch((e: Error) => setError(e.message))
  }, [runId])

  if (error) return <p role="alert" className="mt-2 text-sm text-danger">{error}</p>
  if (answers === null) return <p className="mt-2 text-sm text-muted">Loading answers...</p>
  return (
    <div className="my-2 max-h-96 overflow-y-auto rounded border border-line p-2 text-sm font-normal text-ink">
      <h3 className="font-medium">Run {runId}: {answers.length} answers, lowest accuracy first</h3>
      {answers.map((item) => (
        <details key={item.test_id} className="mt-2 border-t border-line pt-2">
          <summary className="cursor-pointer">{item.accuracy} of 5: {item.question}</summary>
          <div className="mt-1 space-y-1">
            <Scores item={item} />
            {onOpen && <button type="button" className="underline" onClick={() => onOpen(item.test_id)}>Open in Ask</button>}
            <p><span className="font-medium">Answer:</span> {item.answer}</p>
            <p><span className="font-medium">Reference answer:</span> {item.reference_answer}</p>
            <p><span className="font-medium">Judge:</span> {item.feedback}</p>
            <p><span className="font-medium">Judge on faithfulness:</span> {item.faithfulness_feedback}</p>
            <details>
              <summary className="cursor-pointer">Chunks retrieved ({item.chunks.length})</summary>
              {item.chunks.map((chunk, index) => (
                <p key={index} className="mt-1 whitespace-pre-wrap text-muted">{chunk.source}: {chunk.text}</p>
              ))}
            </details>
          </div>
        </details>
      ))}
    </div>
  )
}
