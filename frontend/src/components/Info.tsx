import { useId, useState, type ReactNode } from 'react'

/** A field's label with an "i" button that shows or hides what the setting is for. */
export function InfoLabel({ label, info, htmlFor, children }: { label: string; info: string; htmlFor?: string; children?: ReactNode }) {
  const [open, setOpen] = useState(false)
  const textId = useId()
  return (
    <div className="text-sm">
      <div className="flex items-center gap-1.5">
        {children}
        <label htmlFor={htmlFor}>{label}</label>
        <button type="button" className="info-btn" aria-label={`About ${label}`} aria-expanded={open} aria-controls={textId}
          onClick={() => setOpen(!open)}>i</button>
      </div>
      <p id={textId} hidden={!open} className="mt-1.5 rounded-md border border-line bg-accent-soft/50 p-2 text-xs leading-relaxed">{info}</p>
    </div>
  )
}
