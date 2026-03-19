function trimTrailingSlash(url: string): string {
  return url.endsWith('/') ? url.slice(0, -1) : url
}

export function getStandaloneDocsUrl(): string {
  const configured = (import.meta.env.VITE_DOCS_SITE_URL as string | undefined)?.trim()
  return configured ? trimTrailingSlash(configured) : '/docs'
}

export function getStandaloneDocUrl(slug?: string | null): string {
  const base = getStandaloneDocsUrl()
  if (!slug) return base
  if (base === '/docs') return `/docs/${slug}`
  return `${base}/${slug}`
}
