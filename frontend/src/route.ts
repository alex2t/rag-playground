/** Pages are chosen by the address's hash, so a refresh or a link keeps the page. */

export const PAGES = ['Story', 'Ask', 'Evaluate', 'Compare', 'Build', 'Prompt'] as const
export type Page = (typeof PAGES)[number]

export function hashOf(page: Page): string {
  return `#/${page.toLowerCase()}`
}

/** An empty or unknown hash opens the first page. What follows a '?' is for the page itself. */
export function pageFor(hash: string): Page {
  const [address] = hash.split('?')
  return PAGES.find((page) => hashOf(page) === address) ?? PAGES[0]
}

/** The test question a link to Ask asks for, or an empty string. */
export function linkedTest(hash: string): string {
  return new URLSearchParams(hash.split('?')[1]).get('test') ?? ''
}
