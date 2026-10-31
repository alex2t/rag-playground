import { Fragment, useState } from 'react'
import type { Step } from '../api/types.ts'
import { describe, tradeOff } from '../story.ts'
import AnswersPanel from './AnswersPanel.tsx'

/** Every option each step tried: the table view of the chart. The kept option is marked in words. A run's answers open
 * directly under its row; a run reused by two steps has two rows, so a row is its step and its run. */
export default function StepsTable({ steps }: { steps: Step[] }) {
  const [openRow, setOpenRow] = useState<string | null>(null)
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-muted">
        <tr><th className="pr-3">Step</th><th className="pr-3">Configuration</th><th className="pr-3">Run</th>
          <th className="pr-3">Accuracy</th><th className="pr-3">MRR</th><th className="pr-3">Cost per question</th>
          <th>Result</th></tr>
      </thead>
      <tbody>
        {steps.flatMap((step) => step.tried.map((option) => {
          const row = `${step.step}-${option.run_id}`
          const open = openRow === row
          return (
            <Fragment key={row}>
              <tr className={option.kept ? 'font-medium' : 'text-muted'}>
                <td className="pr-3">{step.step}</td>
                <td className="pr-3">{describe(option.config)}</td>
                <td className="pr-3">
                  {option.run_id}{' '}
                  <button type="button" className="text-accent underline" aria-expanded={open}
                    onClick={() => setOpenRow(open ? null : row)}>
                    {open ? 'Hide answers' : 'View answers'}
                  </button>
                </td>
                <td className="pr-3">{option.accuracy.toFixed(3)}</td>
                <td className="pr-3">{option.mrr.toFixed(3)}</td>
                <td className="pr-3">${option.cost_per_question.toFixed(5)}</td>
                <td>{option.kept ? 'Kept' : ''}{option.failed_gates.length > 0 && ` Failed: ${option.failed_gates.join(', ')}`}</td>
              </tr>
              {open && <tr><td colSpan={7}><AnswersPanel runId={option.run_id} /></td></tr>}
            </Fragment>
          )
        }))}
        {steps.map(tradeOff).filter((report) => report !== null).map((report) => (
          <tr key="s7"><td colSpan={7} className="pt-2">
            Stronger model: accuracy {report.accuracy >= 0 ? '+' : ''}{report.accuracy.toFixed(3)} for cost
            x{report.costTimes.toFixed(1)}. Reported only, never kept.
          </td></tr>
        ))}
      </tbody>
    </table>
  )
}
