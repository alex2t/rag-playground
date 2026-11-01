import { useEffect, useState } from 'react'
import Layout from './components/Layout.tsx'
import Prompt from './pages/Prompt.tsx'
import Story from './pages/Story.tsx'
import { pageFor } from './route.ts'

export default function App() {
  const [page, setPage] = useState(pageFor(location.hash))

  useEffect(() => {
    const follow = () => setPage(pageFor(location.hash))
    addEventListener('hashchange', follow)
    return () => removeEventListener('hashchange', follow)
  }, [])

  return <Layout page={page}>{page === 'Prompt' ? <Prompt /> : <Story />}</Layout>
}
