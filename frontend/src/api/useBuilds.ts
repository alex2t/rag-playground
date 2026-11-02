import { useCallback, useEffect, useState } from 'react'
import { isWorking } from '../build.ts'
import { getBuilds } from './client.ts'
import type { Builds } from './types.ts'

const POLL_MS = 2000

/** What is built and every build job, polled while a build waits or runs, so leaving the page keeps following it. */
export function useBuilds() {
  const [builds, setBuilds] = useState<Builds | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      setBuilds(await getBuilds())
      setError(null)
    } catch (e) {
      setError(`Cannot read the builds, still trying: ${(e as Error).message}`)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const working = builds !== null && isWorking(builds.jobs)
  useEffect(() => {
    if (!working) return
    const timer = setInterval(() => void reload(), POLL_MS)
    return () => clearInterval(timer)
  }, [working, reload])

  return { builds, error, reload }
}
