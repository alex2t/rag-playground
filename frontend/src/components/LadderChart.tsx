import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ChartRow } from '../story.ts'

type Props = { title: string; rows: ChartRow[]; domain: [number, number]; ticks: number[] }

const AXIS = { fontSize: 12, fill: 'var(--color-muted)' }

function series(stack: 'A' | 'B', color: string, filled: boolean) {
  const dot = { r: 4, fill: filled ? color : 'var(--color-panel)', stroke: color, strokeWidth: 2 }
  return <Line dataKey={stack} name={`Stack ${stack}`} stroke={color} strokeWidth={2} dot={dot}
    connectNulls={false} isAnimationActive={false} />
}

/** One line per stack across the steps. Filled and hollow markers keep the stacks apart without colour. */
export default function LadderChart({ title, rows, domain, ticks }: Props) {
  return (
    <figure className="min-w-0 rounded-lg border border-line bg-panel p-4">
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="var(--color-line)" vertical={false} />
          <XAxis dataKey="step" tick={AXIS} stroke="var(--color-line)" />
          <YAxis domain={domain} ticks={ticks} tick={AXIS} stroke="var(--color-line)" />
          <Tooltip formatter={(value) => Number(value).toFixed(3)}
            contentStyle={{ background: 'var(--color-panel)', borderColor: 'var(--color-line)' }} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={(name) => <span className="text-ink">{name}</span>} />
          {series('A', 'var(--color-stack-a)', true)}
          {series('B', 'var(--color-stack-b)', false)}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  )
}
