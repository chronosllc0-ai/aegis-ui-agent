import { useEffect, useMemo, useState } from 'react'
import { getDocsPage } from '../../shared/docs'
import { DocsArticle } from '../../frontend/src/public/docs/DocsArticle'
import { DocsHome } from '../../frontend/src/public/docs/DocsHome'
import { DocsNavigation, DocsSectionStrip } from '../../frontend/src/public/docs/DocsNavigation'

function normalizePath(pathname: string): string {
  if (!pathname || pathname === '/') return '/'
  return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

function productBaseUrl(): string {
  const configured = (import.meta.env.VITE_PRODUCT_SITE_URL as string | undefined)?.trim()
  return configured ? configured.replace(/\/$/, '') : 'http://localhost:5173'
}

function embeddedDocsUrl(slug?: string | null): string {
  const base = productBaseUrl()
  if (!slug) return `${base}/docs`
  return `${base}/docs/${slug}`
}

function navigateTo(path: string): void {
  const normalized = normalizePath(path)
  if (normalizePath(window.location.pathname) === normalized) return
  window.history.pushState({}, '', normalized)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function usePathname(): string {
  const [pathname, setPathname] = useState(() => normalizePath(window.location.pathname))

  useEffect(() => {
    const update = () => setPathname(normalizePath(window.location.pathname))
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  return pathname
}

function slugFromPath(pathname: string): string | null {
  return pathname === '/' ? null : pathname.slice(1) || null
}

export default function App() {
  const pathname = usePathname()
  const slug = slugFromPath(pathname)
  const page = useMemo(() => getDocsPage(slug), [slug])
  const [query, setQuery] = useState('')

  return (
    <main className='min-h-screen bg-[#070b12] text-zinc-100'>
      <header className='border-b border-white/8 bg-[#0a0d14]/88 backdrop-blur-xl'>
        <div className='mx-auto flex w-full max-w-7xl items-center justify-between gap-6 px-6 py-5'>
          <button type='button' onClick={() => navigateTo('/')} className='flex items-center gap-3 text-left'>
            <img src='/shield.svg' alt='Aegis docs logo' className='h-9 w-9' />
            <div>
              <p className='text-lg font-semibold text-white'>Aegis Docs</p>
              <p className='text-[11px] uppercase tracking-[0.22em] text-cyan-200'>Standalone portal</p>
            </div>
          </button>

          <nav className='hidden items-center gap-5 text-sm text-zinc-300 lg:flex'>
            <button type='button' onClick={() => navigateTo('/')} className='transition hover:text-white'>Docs home</button>
            <button type='button' onClick={() => navigateTo('/quickstart')} className='transition hover:text-white'>Quickstart</button>
            <button type='button' onClick={() => navigateTo('/api-auth-reference')} className='transition hover:text-white'>API</button>
            <button type='button' onClick={() => navigateTo('/first-live-run')} className='transition hover:text-white'>Tutorials</button>
            <button type='button' onClick={() => navigateTo('/faq')} className='transition hover:text-white'>FAQ</button>
            <a href={productBaseUrl()} className='transition hover:text-white'>Product site</a>
          </nav>

          <div className='flex flex-wrap gap-3'>
            <a href={embeddedDocsUrl(slug)} className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>
              Embedded docs
            </a>
            <a href={`${productBaseUrl()}/auth`} className='rounded-full bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'>
              Sign in
            </a>
          </div>
        </div>
      </header>

      <div className='mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10'>
        <section className='flex flex-wrap items-center justify-between gap-4'>
          <div>
            <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>Shared docs system</p>
            <h1 className='mt-3 text-3xl font-semibold text-white'>{page ? page.title : 'A docs-first portal for operators and builders.'}</h1>
            <p className='mt-3 max-w-3xl text-sm leading-7 text-zinc-400'>
              This standalone docs app reads the same shared docs content used by the embedded docs experience in the main app. Use it when you want a deeper, docs-first browsing flow.
            </p>
          </div>
        </section>

        <DocsSectionStrip currentPage={page ?? undefined} />

        <div className='grid gap-8 xl:grid-cols-[320px_1fr]'>
          <DocsNavigation activeSlug={page?.slug ?? null} onNavigate={(nextSlug) => navigateTo(`/${nextSlug}`)} onGoHome={() => navigateTo('/')} />

          {page ? (
            <DocsArticle page={page} onNavigate={(nextSlug) => navigateTo(`/${nextSlug}`)} />
          ) : (
            <DocsHome
              query={query}
              onQueryChange={setQuery}
              onNavigate={(nextSlug) => navigateTo(`/${nextSlug}`)}
              onOpenStandalone={undefined}
              standaloneLabel=''
            />
          )}
        </div>

        <footer className='rounded-[32px] border border-white/8 bg-[#0c1018] px-8 py-6 text-sm text-zinc-400'>
          <div className='flex flex-col gap-4 md:flex-row md:items-center md:justify-between'>
            <p>The standalone docs portal is interconnected with the main product surface and the embedded docs routes.</p>
            <div className='flex flex-wrap gap-3'>
              <a href={productBaseUrl()} className='rounded-full border border-white/10 px-4 py-2 text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>Product site</a>
              <a href={embeddedDocsUrl()} className='rounded-full border border-white/10 px-4 py-2 text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>Embedded docs</a>
              <a href={`${productBaseUrl()}/auth`} className='rounded-full border border-white/10 px-4 py-2 text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>Auth</a>
            </div>
          </div>
        </footer>
      </div>
    </main>
  )
}
