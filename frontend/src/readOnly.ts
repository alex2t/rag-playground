/** The read-only demo mode (D32): the pages turn off every button that pays or writes. A notice, not a guard. */

import { createContext, useContext } from 'react'

export type Mode = { read_only: boolean }

/** Buttons stay off until the server has answered, so a visitor never meets the password prompt. */
export function readOnlyOf(mode: Mode | null): boolean {
  return mode === null || mode.read_only
}

export const READ_ONLY_NOTICE = 'Read-only demo: every result can be browsed. Asking, estimating, running, building and saving are turned off.'

export const ReadOnly = createContext(true)

export function useReadOnly(): boolean {
  return useContext(ReadOnly)
}
