import { useEffect, useState } from 'react'

type Health = { status: string; version: string; qdrant: string }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main>
      <h1>RAG Playground</h1>
      {error && <p>Health check failed: {error}</p>}
      {health && (
        <p>
          Status: {health.status} | Version: {health.version} | Qdrant: {health.qdrant}
        </p>
      )}
    </main>
  )
}
