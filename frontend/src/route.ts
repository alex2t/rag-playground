/** Pages are chosen by the address's hash, so a refresh or a link keeps the page. */

export const PAGES = ['Story', 'Ask', 'Evaluate', 'Compare', 'Build', 'Prompt', 'Sweep', 'Ops'] as const
export type Page = (typeof PAGES)[number]

export type MenuItem = { page: Page; about: string }

/** The pages grouped by what the user is doing, each with a one-line description. */
export const MENU: { title: string; items: MenuItem[] }[] = [
  { title: 'Explore', items: [{ page: 'Ask', about: 'Try one question' }] },
  {
    title: 'Measure',
    items: [
      { page: 'Evaluate', about: 'Score one configuration' },
      { page: 'Compare', about: 'Is one run really better?' },
      { page: 'Sweep', about: 'Try values of one setting' },
      { page: 'Story', about: 'The study, step by step' },
    ],
  },
  {
    title: 'Prepare',
    items: [
      { page: 'Build', about: 'Cut and store chunks' },
      { page: 'Prompt', about: 'Write answer instructions' },
    ],
  },
  { title: 'Monitor', items: [{ page: 'Ops', about: 'Spend and health' }] },
]

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
