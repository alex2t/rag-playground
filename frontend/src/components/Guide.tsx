import { useState, type ReactNode } from 'react'

function storedOpen(key: string): boolean {
  try {
    return localStorage.getItem(key) !== 'closed'
  } catch {
    return true
  }
}

function storeOpen(key: string, open: boolean) {
  try {
    localStorage.setItem(key, open ? 'open' : 'closed')
  } catch {
    // Browser storage may be blocked; the guide then just opens again next time.
  }
}

type Props = { page: string; purpose: string; steps: string[]; note?: string; children?: ReactNode }

/** The box at the top of a page: what it is for and what to do, in order, then any extra explanation.
Closing it is remembered on this browser. */
export default function Guide({ page, purpose, steps, note, children }: Props) {
  const key = `guide:${page}`
  const [open, setOpen] = useState(() => storedOpen(key))

  function toggle(next: boolean) {
    setOpen(next)
    storeOpen(key, next)
  }

  return (
    <details open={open} onToggle={(e) => toggle(e.currentTarget.open)}
      className="card border-accent-soft bg-accent-soft/40 px-5 py-4">
      <summary className="cursor-pointer font-semibold">{page}: how this page works</summary>
      <p className="mt-2 text-sm">{purpose}</p>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
        {steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      {note && <p className="mt-2 text-sm text-muted">{note}</p>}
      {children}
    </details>
  )
}
