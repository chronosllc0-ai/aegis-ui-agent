import { useEffect, useState } from 'react'

function normalizePath(path: string): string {
  if (!path || path === '/') return '/'
  return path.endsWith('/') ? path.slice(0, -1) : path
}

export function navigateTo(path: string): void {
  const normalized = normalizePath(path)
  if (normalizePath(window.location.pathname) === normalized) return
  window.history.pushState({}, '', normalized)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(() => normalizePath(window.location.pathname))

  useEffect(() => {
    const update = () => setPathname(normalizePath(window.location.pathname))
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  return pathname
}

export function docsPath(slug?: string | null): string {
  return slug ? `/docs/${slug}` : '/docs'
}

export const PRIVACY_PATH = '/privacy'
export const TERMS_PATH = '/terms'
