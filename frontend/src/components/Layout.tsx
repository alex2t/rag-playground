import type { ReactNode } from 'react'
import { hashOf, MENU, type MenuItem, type Page } from '../route.ts'

function NavLink({ item, current }: { item: MenuItem; current: boolean }) {
  return (
    <a href={hashOf(item.page)} aria-current={current ? 'page' : undefined}
      className={`block rounded-lg px-3 py-1.5 ${current ? 'bg-accent-soft font-semibold text-accent-text' : 'hover:bg-page'}`}>
      <span className="block text-sm">{item.page}</span>
      <span className="hidden text-xs font-normal text-muted md:block">{item.about}</span>
    </a>
  )
}

/** The shared page frame: a sidebar on wide screens, a scrolling bar of links on phones. */
export default function Layout({ page, notice, modeError, onSignIn, signInError, children }: {
  page: Page; notice: string | null; modeError: string | null; onSignIn: (() => void) | null; signInError: string | null; children: ReactNode
}) {
  return (
    <div className="md:flex md:min-h-screen">
      <aside className="border-b border-line bg-panel md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="px-4 py-4 md:px-5 md:py-6">
          <span className="text-base font-bold tracking-tight">RAG Playground</span>
          <span className="hidden text-xs text-muted md:block">Two RAG stacks, measured side by side</span>
        </div>
        <nav aria-label="Pages" className="flex gap-1 overflow-x-auto px-2 pb-3 md:block md:space-y-5 md:px-3">
          {MENU.map((group) => (
            <div key={group.title} className="flex gap-1 md:block md:space-y-0.5">
              <p className="hidden px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted md:block">{group.title}</p>
              {group.items.map((item) => <NavLink key={item.page} item={item} current={item.page === page} />)}
            </div>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-6xl">
          {notice && (
            <div role="status" className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-accent p-3 text-sm">
              <p className="min-w-0 flex-1">{notice}</p>
              {onSignIn && <button type="button" className="btn text-sm" onClick={onSignIn}>Admin sign-in</button>}
            </div>
          )}
          {signInError && <p role="alert" className="mb-5 text-sm text-danger">{signInError}</p>}
          {modeError && <p role="alert" className="mb-5 text-sm text-danger">Cannot read the site mode, so paid and saving buttons stay off: {modeError}</p>}
          {children}
        </div>
      </main>
    </div>
  )
}
