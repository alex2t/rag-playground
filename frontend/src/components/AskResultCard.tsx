import type { AskChunk, AskJudgement, AskResult } from '../api/types.ts'
import { chunkLine, missedSources, money, warnings } from '../ask.ts'

function Judge({ reference, verdict }: { reference: string | null; verdict: AskJudgement }) {
  return (
    <div className="space-y-1 border-t border-line pt-2">
      <p><span className="font-medium">Reference answer:</span> {reference}</p>
      <p>Accuracy {verdict.accuracy}, completeness {verdict.completeness}, relevance {verdict.relevance}, faithfulness {verdict.faithfulness}{verdict.refused && ', refused'}</p>
      <p><span className="font-medium">Judge:</span> {verdict.feedback}</p>
      <p><span className="font-medium">Judge on faithfulness:</span> {verdict.faithfulness_feedback}</p>
    </div>
  )
}

function Chunk({ chunk }: { chunk: AskChunk }) {
  return (
    <details className={`rounded border p-2 ${chunk.gold ? 'border-accent' : 'border-line'}`}>
      <summary className="cursor-pointer [overflow-wrap:anywhere]">{chunkLine(chunk)}</summary>
      <p className="mt-1 whitespace-pre-wrap text-muted">{chunk.text}</p>
    </details>
  )
}

/** One stack's answer: the settings it used, what it read, and the judge's verdict on a test question. */
export default function AskResultCard({ line, result }: { line: string; result: AskResult }) {
  const missed = missedSources(result)
  return (
    <div className="space-y-2 text-sm">
      <p className="text-muted">{line}</p>
      <p className="whitespace-pre-wrap">{result.answer}</p>
      {warnings(result).map((warning) => <p key={warning} className="font-medium">{warning}</p>)}
      <p className="text-muted">{result.latency_s.toFixed(1)} s, {money(result.cost_usd)}</p>
      {result.judgement && <Judge reference={result.reference_answer} verdict={result.judgement} />}
      {missed.length > 0 && <p>Not retrieved, but holds the answer: {missed.join(', ')}</p>}
      <h4 className="border-t border-line pt-2 font-medium">Chunks given to the model ({result.chunks.length})</h4>
      {result.chunks.map((chunk) => <Chunk key={chunk.rank} chunk={chunk} />)}
    </div>
  )
}
