import type { ReactNode } from 'react'

/** The shared page frame; each page adds its link here as it is built. */
export default function Layout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex items-baseline gap-6 border-b border-line pb-3">
        <span className="text-lg font-semibold">RAG Playground</span>
        <nav aria-label="Pages">
          <span aria-current="page" className="font-medium underline underline-offset-4">{title}</span>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  )
}
