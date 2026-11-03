import { useLadder } from '../api/useLadder.ts'
import Guide from '../components/Guide.tsx'
import PageTitle from '../components/PageTitle.tsx'
import LadderChart from '../components/LadderChart.tsx'
import StackPanel from '../components/StackPanel.tsx'
import { chartRows } from '../story.ts'

const STEPS = [
  'Each stack\'s box below shows its next step and what it will cost. Press its Run button: one step per click.',
  'Step S4 (LLM-enriched chunks) asks you to confirm its build cost first. At S6, type up to 4 prompt versions written on Prompt, and press Estimate.',
  'The charts draw one line per stack: accuracy and MRR at each step, with bars for the 95% interval; + or - marks a real change from the step before.',
  'Open Every option tried to see each option\'s scores, and View answers to read what it answered.',
  'When a stack\'s ladder is finished, confirm its best set-up on the 48 held-out questions.',
]

/** The ladder on both stacks: one step per click, one line per stack (T50). */
export default function Story() {
  const a = useLadder('A')
  const b = useLadder('B')
  return (
    <div className="space-y-5">
      <PageTitle title="Story" about="The study itself: one fixed step at a time, each changing one setting." />
      <Guide page="Story" steps={STEPS}
        purpose="A fixed ladder of steps, S0 to S7, run on each stack separately. Each step tries the options for one setting on the 192 dev questions, and a rule fixed in advance keeps the winner, so a result cannot be steered after seeing it."
        note="Each step runs one or more full dev runs, about $0.23 each on Stack B and $0.72 on Stack A (its search fee included); finished runs are reused, never paid twice." />
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
