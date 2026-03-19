import { DOCS_PAGES, DOCS_SECTIONS } from './content'
import type { DocsPage, DocsSectionMeta } from './types'

export type { DocsBlock, DocsPage, DocsSectionId, DocsSectionMeta } from './types'

export function listDocsSections(): DocsSectionMeta[] {
  return DOCS_SECTIONS
}

export function listDocsPages(): DocsPage[] {
  return DOCS_PAGES
}

export function getDocsPage(slug: string | null | undefined): DocsPage | undefined {
  if (!slug) return undefined
  return DOCS_PAGES.find((page) => page.slug === slug)
}

export function getDocsPagesBySection(sectionId: DocsSectionMeta['id']): DocsPage[] {
  return DOCS_PAGES.filter((page) => page.section === sectionId)
}

export function getFeaturedDocsPages(): DocsPage[] {
  return DOCS_PAGES.filter((page) => page.featured)
}

export function findDocsPages(query: string): DocsPage[] {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return DOCS_PAGES
  return DOCS_PAGES.filter((page) => {
    const haystack = [page.title, page.summary, page.audience, page.section].join(' ').toLowerCase()
    return haystack.includes(normalized)
  })
}

export function getRelatedDocs(page: DocsPage): DocsPage[] {
  return page.related
    .map((slug) => getDocsPage(slug))
    .filter((relatedPage): relatedPage is DocsPage => Boolean(relatedPage))
}
