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

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), { credentials: 'include', ...init })
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Request failed (${response.status})`)
  }
  try {
    return (await response.json()) as T
  } catch (error) {
    throw new Error(
      `Invalid JSON response from ${path}: ${error instanceof Error ? error.message : 'Unknown parse error'}`,
    )
  }
}
