export function getApiBase(): string {
  const base = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
  if (!base) return ''
  return base.endsWith('/') ? base.slice(0, -1) : base
}

export function apiUrl(path: string): string {
  const base = getApiBase()
  if (!path.startsWith('/')) {
    path = `/${path}`
  }
  return base ? `${base}${path}` : path
}
