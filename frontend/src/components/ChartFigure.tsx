import { useRef, useState, type ReactNode } from 'react'
import { downloadChart, pngName, type LegendLine } from '../chartImage.ts'

type Props = { title: string; legend: LegendLine[]; note: string; children: ReactNode }

/** A chart's frame: its title, the note under it, and the button that saves it with its legend as a PNG. */
export default function ChartFigure({ title, legend, note, children }: Props) {
  const figure = useRef<HTMLElement>(null)
  const [error, setError] = useState<string | null>(null)

  function savePng() {
    setError(null)
    downloadChart(figure.current!, title, legend).catch((e: Error) => setError(e.message))
  }

  return (
    <figure ref={figure} className="min-w-0 card p-4">
      <figcaption className="mb-2 flex items-start justify-between gap-2 text-sm font-medium">
        <span>{title}</span>
        <button type="button" className="shrink-0 rounded border border-line px-2 py-0.5 text-xs font-normal"
          aria-label={`Download ${pngName(title)}`} onClick={savePng}>Download PNG</button>
      </figcaption>
      {children}
      <p className="mt-1 text-xs text-muted">{note}</p>
      {error && <p role="alert" className="mt-1 text-sm text-danger">{error}</p>}
    </figure>
  )
}
