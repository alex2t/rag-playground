import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import type { Comparison } from '../api/types.ts'
import { chartLegend, judgeRows, rateRows, type ScoreRow } from '../compare.ts'
import ChartFigure from './ChartFigure.tsx'

const AXIS = { fontSize: 12, fill: 'var(--color-muted)' }
const TOOLTIP = { background: 'var(--color-panel)', borderColor: 'var(--color-line)' }
const BEFORE = 'var(--color-before)'
const AFTER = 'var(--color-after)'
const HEIGHT = 300
const legendText = (name: string) => <span className="text-ink">{name}</span>
const beforeFirst = (item: { name?: unknown }) => (item.name === 'Before' ? 0 : 1)

type BarsProps = { title: string; note: string; rows: ScoreRow[]; domain: [number, number]; ticks: number[]; comparison: Comparison }

function ScoreBars({ title, note, rows, domain, ticks, comparison }: BarsProps) {
  return (
    <ChartFigure title={title} legend={chartLegend(comparison)} note={note}>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <BarChart layout="vertical" data={rows} barSize={11} barGap={2} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--color-line)" horizontal={false} />
          <XAxis type="number" domain={domain} ticks={ticks} tick={AXIS} stroke="var(--color-line)" />
          <YAxis type="category" dataKey="label" width={150} interval={0} tick={AXIS} stroke="var(--color-line)" />
          <Tooltip formatter={(value) => Number(value).toFixed(3)} itemSorter={beforeFirst} contentStyle={TOOLTIP} cursor={{ fill: 'var(--color-line)', opacity: 0.3 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} formatter={legendText} itemSorter={null} />
          <Bar dataKey="before" name="Before" fill={BEFORE} radius={[0, 4, 4, 0]} isAnimationActive={false} />
          <Bar dataKey="after" name="After" fill={AFTER} radius={[0, 4, 4, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFigure>
  )
}

function CostChart({ comparison }: { comparison: Comparison }) {
  const { before, after } = comparison
  const point = (report: Comparison['before']) => [{ cost: report.cost_per_question, accuracy: report.scores.accuracy, name: `Run ${report.id}` }]
  return (
    <ChartFigure title="Cost against accuracy (accuracy 1 to 5)" legend={chartLegend(comparison)}
      note="Up is more accurate, left is cheaper. The circle is Before, the diamond After.">
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 16, left: 0 }}>
          <CartesianGrid stroke="var(--color-line)" />
          <XAxis type="number" dataKey="cost" name="Cost per question" domain={[0, 'auto']} tick={AXIS} stroke="var(--color-line)"
            tickFormatter={(value: number) => `$${value.toFixed(4)}`} tickCount={4}
            label={{ value: 'Cost per question', position: 'bottom', offset: 0, fontSize: 12, fill: 'var(--color-muted)' }} />
          <YAxis type="number" dataKey="accuracy" name="Accuracy" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} width={40} tick={AXIS} stroke="var(--color-line)" />
          <ZAxis range={[100, 100]} />
          <Tooltip contentStyle={TOOLTIP} formatter={(value, name) => (name === 'Accuracy' ? Number(value).toFixed(3) : `$${Number(value).toFixed(4)}`)} />
          <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12 }} formatter={legendText} itemSorter={null} />
          <Scatter name="Before" data={point(before)} fill={BEFORE} isAnimationActive={false}>
            <LabelList dataKey="name" position="top" offset={10} fontSize={12} fill="var(--color-ink)" />
          </Scatter>
          <Scatter name="After" data={point(after)} fill={AFTER} shape="diamond" legendType="diamond" isAnimationActive={false}>
            <LabelList dataKey="name" position="bottom" offset={10} fontSize={12} fill="var(--color-ink)" />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </ChartFigure>
  )
}

/** The scores side by side, one chart per scale, and what the change costs. */
export default function CompareCharts({ comparison }: { comparison: Comparison }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ScoreBars title="Judge scores (1 to 5)" note="Higher is better. Each score is explained by its i button in All scores, below." rows={judgeRows(comparison)} domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} comparison={comparison} />
      <CostChart comparison={comparison} />
      <div className="md:col-span-2">
        <ScoreBars title="Search scores and refusal rates (0 to 1)" note="Higher is better, except the false refusal rate. Each score is explained by its i button in All scores, below."
          rows={rateRows(comparison)} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} comparison={comparison} />
      </div>
    </div>
  )
}
