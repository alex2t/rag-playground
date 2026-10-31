import { useLadder } from '../api/useLadder.ts'
import LadderChart from '../components/LadderChart.tsx'
import StackPanel from '../components/StackPanel.tsx'
import { chartRows } from '../story.ts'

/** The ladder on both stacks: one step per click, one line per stack (T50). */
export default function Story() {
  const a = useLadder('A')
  const b = useLadder('B')
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <LadderChart title="Accuracy per step (1 to 5, 192 dev questions)" rows={chartRows(a.state, b.state, 'accuracy')}
          domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} />
        <LadderChart title="MRR per step (0 to 1, answerable dev questions)" rows={chartRows(a.state, b.state, 'mrr')}
          domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <StackPanel stack="A" ladder={a} />
        <StackPanel stack="B" ladder={b} />
      </div>
    </div>
  )
}
