import type { Change, Heldout } from '../api/types.ts'
import { describe, heldoutLabel, money } from '../story.ts'

function changeLine(name: string, change: Change) {
  return (
    <li>
      {name}: {change.low.toFixed(3)} to {change.high.toFixed(3)} (95% interval). {change.real ? 'A real gain.' : 'No real gain shown.'}
    </li>
  )
}

/** The final numbers: S0 and the final configuration on the 48 held-out questions. */
export default function HeldoutPanel({ heldout, busy, onRun }: { heldout: Heldout | null; busy: boolean; onRun: () => void }) {
  if (heldout === null) return <p className="text-sm text-muted">Held-out confirmation opens when this stack's ladder is finished.</p>
  return (
    <div className="text-sm">
      <h3 className="font-medium">Held-out confirmation</h3>
      <ul>
        {heldout.runs.map((run) => (
          <li key={run.run_id}>
            {heldoutLabel(run, heldout)} (run {run.run_id}): accuracy {run.accuracy.toFixed(3)}, MRR {run.mrr.toFixed(3)}.
            {' '}{describe(run.config)}
          </li>
        ))}
      </ul>
      {heldout.gain && (
        <ul className="mt-1">
          {changeLine('Accuracy change against S0', heldout.gain.accuracy)}
          {changeLine('MRR change against S0', heldout.gain.mrr)}
        </ul>
      )}
      <p className="mt-1 text-muted">With 48 questions these intervals are wide.</p>
      {heldout.missing.length > 0 && (
        <button type="button" className="mt-2 btn" disabled={busy} onClick={onRun}>
          Confirm on held-out questions ({money(heldout.estimate_usd)})
        </button>
      )}
    </div>
  )
}
