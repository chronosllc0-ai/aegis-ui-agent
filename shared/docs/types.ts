export type DocsSectionId = 'guides' | 'tutorials' | 'reference' | 'support'

export type DocsBlock =
  | { type: 'heading'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'steps'; items: Array<{ title: string; body: string }> }
  | { type: 'callout'; tone: 'info' | 'success' | 'warning'; title: string; body: string }
  | { type: 'code'; language: string; code: string }
  | { type: 'table'; columns: string[]; rows: string[][] }
  | { type: 'faq'; items: Array<{ question: string; answer: string }> }
  | { type: 'timeline'; items: Array<{ date: string; title: string; description: string }> }
  | { type: 'linkCards'; items: Array<{ slug: string; title: string; description: string }> }

export type DocsPage = {
  slug: string
  title: string
  summary: string
  section: DocsSectionId
  audience: string
  updatedAt: string
  featured?: boolean
  blocks: DocsBlock[]
  related: string[]
}

export type DocsSectionMeta = {
  id: DocsSectionId
  title: string
  description: string
}
