import { useEffect, useState } from 'react'
import Layout from './components/Layout.tsx'
import Ask from './pages/Ask.tsx'
import Prompt from './pages/Prompt.tsx'
import Story from './pages/Story.tsx'
import { pageFor, type Page } from './route.ts'

const PAGE_VIEWS: Record<Page, () => React.JSX.Element> = { Story, Ask, Prompt }

export default function App() {
  const [page, setPage] = useState(pageFor(location.hash))

  useEffect(() => {
    const follow = () => setPage(pageFor(location.hash))
    addEventListener('hashchange', follow)
    return () => removeEventListener('hashchange', follow)
  }, [])

  const View = PAGE_VIEWS[page]
  return <Layout page={page}><View /></Layout>
}
