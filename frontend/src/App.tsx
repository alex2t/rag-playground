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

const PAGE_VIEWS: Record<Page, () => React.JSX.Element> = { Home, Story, Ask, Evaluate, Compare, Build, Prompt, Sweep, Ops }

/** Picks the page from the address. A new address builds the page again, so a link's values (prompt, run, ...) are read. */
export default function App() {
  const [hash, setHash] = useState(location.hash)

  useEffect(() => {
    const follow = () => setHash(location.hash)
    addEventListener('hashchange', follow)
    return () => removeEventListener('hashchange', follow)
  }, [])

  const page = pageFor(hash)
  const View = PAGE_VIEWS[page]
  return <Layout page={page}><View key={hash} /></Layout>
}
