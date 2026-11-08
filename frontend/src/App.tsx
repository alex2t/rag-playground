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
import { getMode, signIn } from './api/client.ts'
import { noticeOf, offersSignIn, ReadOnly, readOnlyOf, signInProblem, type Mode } from './readOnly.ts'

const PAGE_VIEWS: Record<Page, () => React.JSX.Element> = { Home, Story, Ask, Evaluate, Compare, Build, Prompt, Sweep, Ops }

/** Picks the page from the address. A new address builds the page again, so a link's values (prompt, run, ...) are read. */
export default function App() {
  const [hash, setHash] = useState(location.hash)
  const [mode, setMode] = useState<Mode | null>(null)
  const [modeError, setModeError] = useState<string | null>(null)
  const [signedIn, setSignedIn] = useState(false)
  const [signInError, setSignInError] = useState<string | null>(null)

  function signInNow() {
    setSignInError(null)
    signIn()
      .then((status) => (status === 200 ? setSignedIn(true) : setSignInError(signInProblem(status))))
      .catch((e: Error) => setSignInError(e.message))
  }

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
    <ReadOnly value={readOnlyOf(mode, signedIn)}>
      <Layout page={page} notice={noticeOf(mode, signedIn)} modeError={modeError}
        onSignIn={offersSignIn(mode, signedIn) ? signInNow : null} signInError={signInError}><View key={hash} /></Layout>
    </ReadOnly>
  )
}
