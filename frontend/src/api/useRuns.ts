import { useCallback, useEffect, useState } from 'react'
import { isWorking } from '../evaluate.ts'
import { getRuns } from './client.ts'
import type { RunSummary } from './types.ts'

const POLL_MS = 2000

/** The stored runs, polled while a job works on one, so leaving the page and coming back keeps following it. */
export function useRuns() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async (): Promise<RunSummary[] | null> => {
    try {
      const fresh = await getRuns()
      setRuns(fresh)
      setError(null)
      return fresh
    } catch (e) {
      setError(`Cannot read the runs, still trying: ${(e as Error).message}`)
      return null
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const working = runs !== null && isWorking(runs)
  useEffect(() => {
    if (!working) return
    const timer = setInterval(() => void reload(), POLL_MS)
    return () => clearInterval(timer)
  }, [working, reload])

  return { runs, error, reload }
}
