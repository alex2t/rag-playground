import { useEffect, useState } from 'react'
import { getComparison } from './client.ts'
import type { Comparison } from './types.ts'

type Loaded = { key: string; comparison?: Comparison; error?: string }

/** The comparison of two runs. A late reply for an earlier pair is dropped, and an earlier pair's result is never shown. */
export function useComparison(before: number | null, after: number | null) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const key = `${before}-${after}`

  useEffect(() => {
    if (before === null || after === null) return
    let current = true
    getComparison(before, after)
      .then((comparison) => { if (current) setLoaded({ key, comparison }) })
      .catch((e: Error) => { if (current) setLoaded({ key, error: e.message }) })
    return () => { current = false }
  }, [before, after, key])

  return loaded?.key === key ? loaded : { comparison: undefined, error: undefined }
}
