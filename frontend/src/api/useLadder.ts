import { useCallback, useEffect, useState } from 'react'
import { getJob, getLadder } from './client.ts'
import type { Job, LadderState, StackId } from './types.ts'

const POLL_MS = 2000

/** A stack's ladder and its running job, polled until the job ends. A job found on load is picked up, so a page
 * refresh keeps following it. */
export function useLadder(stack: StackId) {
  const [state, setState] = useState<LadderState | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const next = await getLadder(stack)
      setState(next)
      setError(null)
      if (next.job_id !== null) setJobId(next.job_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [stack])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (jobId === null) return
    const timer = setInterval(async () => {
      try {
        const current = await getJob(jobId)
        setJob(current)
        setError(null)
        if (current.status === 'done' || current.status === 'failed') {
          setJobId(null)
          void reload()
        }
      } catch (e) {
        setError(`Cannot read the running step, still trying: ${(e as Error).message}`)
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [jobId, reload])

  return { state, job, running: jobId !== null, error, setError, follow: setJobId, setState }
}
