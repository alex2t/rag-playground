/** The read-only demo mode (D32): the pages turn off every button that pays or writes. A notice, not a guard. */

import { createContext, useContext } from 'react'

export type Mode = { read_only: boolean }

/** Buttons stay off until the server has answered, so a visitor never meets the password prompt.
 * In a read-only demo, the admin's sign-in turns them on in that browser only. */
export function readOnlyOf(mode: Mode | null, signedIn: boolean): boolean {
  return mode === null || (mode.read_only && !signedIn)
}

/** The notice and its sign-in button show only in a read-only demo, until the admin has signed in. */
export function offersSignIn(mode: Mode | null, signedIn: boolean): boolean {
  return mode !== null && mode.read_only && !signedIn
}

/** Why POST /api/sign-in did not succeed: the server's Nginx answers 401 to a cancelled or wrong password. */
export function signInProblem(status: number): string {
  return status === 401 ? 'Sign-in cancelled or wrong password.' : `Sign-in failed (${status}).`
}

export const READ_ONLY_NOTICE = 'Read-only demo: every result can be browsed. Asking, estimating, running, building and saving are turned off.'
export const SIGNED_IN_NOTICE = 'Signed in as the admin: asking, estimating, running, building and saving are on until this page is reloaded.'

/** The line at the top of every page: none on a site that is not a read-only demo. */
export function noticeOf(mode: Mode | null, signedIn: boolean): string | null {
  if (mode === null || !mode.read_only) return null
  return signedIn ? SIGNED_IN_NOTICE : READ_ONLY_NOTICE
}

export const ReadOnly = createContext(true)

export function useReadOnly(): boolean {
  return useContext(ReadOnly)
}
