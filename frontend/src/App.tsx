import { useEffect, useState } from 'react'
import Layout from './components/Layout.tsx'
import Ask from './pages/Ask.tsx'
import Build from './pages/Build.tsx'
import Compare from './pages/Compare.tsx'
import Evaluate from './pages/Evaluate.tsx'
import Home from './pages/Home.tsx'
import Ops from './pages/Ops.tsx'
import Prompt from './pages/Prompt.tsx'
import Story from './pages/Story.tsx'
import Sweep from './pages/Sweep.tsx'
import { pageFor, type Page } from './route.ts'
import { getMode } from './api/client.ts'
import { READ_ONLY_NOTICE, ReadOnly, readOnlyOf, type Mode } from './readOnly.ts'

const PAGE_VIEWS: Record<Page, () => React.JSX.Element> = { Home, Story, Ask, Evaluate, Compare, Build, Prompt, Sweep, Ops }

/** Picks the page from the address. A new address builds the page again, so a link's values (prompt, run, ...) are read. */
export default function App() {
  const [hash, setHash] = useState(location.hash)
  const [mode, setMode] = useState<Mode | null>(null)
  const [modeError, setModeError] = useState<string | null>(null)

  useEffect(() => {
    getMode().then(setMode).catch((e: Error) => setModeError(e.message))
  }, [])

  useEffect(() => {
    const follow = () => setHash(location.hash)
    addEventListener('hashchange', follow)
    return () => removeEventListener('hashchange', follow)
  }, [])

  const page = pageFor(hash)
  const View = PAGE_VIEWS[page]
  return (
    <ReadOnly value={readOnlyOf(mode)}>
      <Layout page={page} notice={mode?.read_only ? READ_ONLY_NOTICE : null} modeError={modeError}><View key={hash} /></Layout>
    </ReadOnly>
  )
}
