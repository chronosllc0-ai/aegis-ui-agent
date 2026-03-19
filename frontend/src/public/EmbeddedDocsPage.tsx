import { useMemo, useState } from 'react'
import { getDocsPage } from '../../../shared/docs'
import { docsPath } from '../lib/routes'
import { getStandaloneDocUrl } from '../lib/site'
import { DocsArticle } from './docs/DocsArticle'
import { DocsHome } from './docs/DocsHome'
import { DocsNavigation, DocsSectionStrip } from './docs/DocsNavigation'
import { PublicFooter } from './PublicFooter'
import { PublicHeader } from './PublicHeader'

type EmbeddedDocsPageProps = {
  slug?: string | null
  onGoHome: () => void
  onGoAuth: () => void
  onGoDocsHome: () => void
  onNavigateToSlug: (slug: string) => void
}

export function EmbeddedDocsPage({ slug, onGoHome, onGoAuth, onGoDocsHome, onNavigateToSlug }: EmbeddedDocsPageProps) {
  const [query, setQuery] = useState('')
  const page = useMemo(() => getDocsPage(slug), [slug])
  const docsPortalHref = getStandaloneDocUrl(slug)

  return (
    <main className='min-h-screen bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={onGoHome}
        onGoAuth={onGoAuth}
        onGoDocsHome={onGoDocsHome}
        onGoDoc={onNavigateToSlug}
        docsPortalHref={getStandaloneDocUrl()}
      />

      <div className='mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10'>
        <section className='flex flex-wrap items-center justify-between gap-4'>
          <div>
            <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>Embedded docs</p>
            <h1 className='mt-3 text-3xl font-semibold text-white'>{page ? page.title : 'Documentation'}</h1>
            <p className='mt-3 max-w-2xl text-sm leading-7 text-zinc-400'>
              Read docs without leaving the main product surface, then jump to the standalone docs portal when you want a full docs-first browsing experience.
            </p>
          </div>
          <a
            href={docsPortalHref}
            className='rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100 transition hover:bg-cyan-400/14'
          >
            Open standalone docs portal
          </a>
        </section>

        <DocsSectionStrip currentPage={page} />

        <div className='grid gap-8 xl:grid-cols-[320px_1fr]'>
          <DocsNavigation activeSlug={page?.slug ?? null} onNavigate={onNavigateToSlug} onGoHome={onGoDocsHome} />

          {page ? (
            <DocsArticle page={page} onNavigate={onNavigateToSlug} />
          ) : (
            <DocsHome
              query={query}
              onQueryChange={setQuery}
              onNavigate={onNavigateToSlug}
              onOpenStandalone={() => { window.location.href = getStandaloneDocUrl() }}
            />
          )}
        </div>

        <section className='rounded-[32px] border border-white/8 bg-[#0c1018] p-8'>
          <div className='flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between'>
            <div>
              <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Need more depth?</p>
              <h2 className='mt-3 text-2xl font-semibold text-white'>Move between docs and product without losing context.</h2>
              <p className='mt-3 max-w-3xl text-sm leading-7 text-zinc-300'>
                Embedded docs are best when you are already inside the main product flow. The standalone docs site is built for deeper browsing, API scanning, and tutorial reading.
              </p>
            </div>
            <div className='flex flex-wrap gap-3'>
              <button
                type='button'
                onClick={() => onNavigateToSlug('first-live-run')}
                className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
              >
                Read tutorial
              </button>
              <button
                type='button'
                onClick={onGoAuth}
                className='rounded-full bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
              >
                Start a session
              </button>
            </div>
          </div>
        </section>
      </div>

      <PublicFooter
        onGoHome={onGoHome}
        onGoAuth={onGoAuth}
        onGoDocsHome={onGoDocsHome}
        onGoDoc={onNavigateToSlug}
        docsPortalHref={getStandaloneDocUrl()}
      />
    </main>
  )
}

export function slugFromDocsPath(pathname: string): string | null {
  if (pathname === '/docs') return null
  if (!pathname.startsWith('/docs/')) return null
  return pathname.slice('/docs/'.length) || null
}

export function docsHref(slug?: string | null): string {
  return docsPath(slug)
}
