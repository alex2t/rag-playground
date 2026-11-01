import { useEffect, useState } from 'react'
import { loadSaved, restoredValues, type PanelValues } from '../panel.ts'
import { getPanel, getPrompts } from './client.ts'
import type { PanelOptions } from './types.ts'

/** The settings panel's options and values, opening with the last values used on this browser (T55). */
export function usePanel() {
  const [options, setOptions] = useState<PanelOptions | null>(null)
  const [promptNames, setPromptNames] = useState<string[]>([])
  const [values, setValues] = useState<PanelValues | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getPanel(), getPrompts()]).then(([panel, prompts]) => {
      const names = prompts.map((prompt) => prompt.name)
      setOptions(panel)
      setPromptNames(names)
      setValues(restoredValues(loadSaved(), panel, names))
    }).catch((e: Error) => setError(e.message))
  }, [])

  return { options, promptNames, values, setValues, error }
}
