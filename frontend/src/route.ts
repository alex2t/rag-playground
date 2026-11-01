/** Pages are chosen by the address's hash, so a refresh or a link keeps the page. */

export const PAGES = ['Story', 'Ask', 'Prompt'] as const
export type Page = (typeof PAGES)[number]

export function hashOf(page: Page): string {
  return `#/${page.toLowerCase()}`
}

/** An empty or unknown hash opens the first page. */
export function pageFor(hash: string): Page {
  return PAGES.find((page) => hashOf(page) === hash) ?? PAGES[0]
}
