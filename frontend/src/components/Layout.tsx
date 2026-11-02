import type { ReactNode } from 'react'
import { hashOf, PAGES, type Page } from '../route.ts'

/** The shared page frame; each page adds its name to PAGES as it is built. */
export default function Layout({ page, children }: { page: Page; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-line pb-3">
        <span className="text-lg font-semibold">RAG Playground</span>
        <nav aria-label="Pages" className="flex flex-wrap gap-x-4">
          {PAGES.map((name) => (
            <a key={name} href={hashOf(name)} aria-current={name === page ? 'page' : undefined}
              className={name === page ? 'font-medium underline underline-offset-4' : 'text-muted'}>{name}</a>
          ))}
        </nav>
      </header>
      <main>{children}</main>
    </div>
  )
}
