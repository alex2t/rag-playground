import { useId, useState, type ReactNode } from 'react'

type Props = { label: string; info: string; htmlFor?: string; about?: string; className?: string; children?: ReactNode }

/** A label with an "i" button that shows or hides what the thing is for. With `htmlFor` it labels a form field;
 * without, it is plain text (a score tile, a table row). `about` names it for screen readers when the label is long. */
export function InfoLabel({ label, info, htmlFor, about = label, className = 'text-sm', children }: Props) {
  const [open, setOpen] = useState(false)
  const textId = useId()
  return (
    <div className={className}>
      <div className="flex items-center gap-1.5">
        {children}
        {htmlFor ? <label htmlFor={htmlFor}>{label}</label> : <span>{label}</span>}
        <button type="button" className="info-btn shrink-0" aria-label={`About ${about}`} aria-expanded={open} aria-controls={textId}
          onClick={() => setOpen(!open)}>i</button>
      </div>
      <p id={textId} hidden={!open} className="mt-1.5 rounded-md border border-line bg-accent-soft/50 p-2 text-xs font-normal leading-relaxed text-ink">{info}</p>
    </div>
  )
}
