// Chat-only build: there is no separate docs portal. Docs always live at the
// embedded `/docs` surface inside the main app. `getStandaloneDocUrl`/`…sUrl`
// are kept as thin shims so shared header/footer call sites keep working.

export function getStandaloneDocsUrl(): string {
  return '/docs'
}

export function getStandaloneDocUrl(slug?: string | null): string {
  return slug ? `/docs/${slug}` : '/docs'
}
