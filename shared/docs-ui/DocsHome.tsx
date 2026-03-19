import { getFeaturedDocsPages, getDocsPagesBySection, listDocsSections, findDocsPages } from '../docs'
import { SharedIcons } from './SharedIcons'

type DocsHomeProps = {
  query: string
  onQueryChange: (nextQuery: string) => void
  onNavigate: (slug: string) => void
  onOpenStandalone?: () => void
  standaloneLabel?: string
}

export function DocsHome({
  query,
  onQueryChange,
  onNavigate,
  onOpenStandalone,
  standaloneLabel = 'Open standalone docs',
}: DocsHomeProps) {
  const results = query.trim() ? findDocsPages(query) : []
  const featured = getFeaturedDocsPages()

  return (
    <div className='grid gap-8'>
      <section className='rounded-[32px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_35%),linear-gradient(180deg,#111827_0%,#0a0d14_100%)] p-8 shadow-[0_24px_80px_rgba(0,0,0,0.35)]'>
        <div className='flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between'>
          <div className='max-w-3xl'>
            <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>Aegis docs</p>
            <h1 className='mt-4 text-4xl font-semibold text-white'>Shared docs for operators, builders, and deployers.</h1>
            <p className='mt-4 text-base leading-8 text-zinc-300'>
              Browse quickstart, API reference, tutorials, FAQ, and changelog from one shared source. The embedded docs
              inside the product and the standalone docs portal stay in sync.
            </p>
          </div>
          <div className='flex flex-wrap gap-3'>
            {onOpenStandalone && (
              <button
                type='button'
                onClick={onOpenStandalone}
                className='rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100 transition hover:bg-cyan-400/14'
              >
                {standaloneLabel}
              </button>
            )}
          </div>
        </div>

        <div className='mt-8 rounded-3xl border border-white/8 bg-black/20 p-4'>
          <label htmlFor='docs-search' className='text-xs uppercase tracking-[0.24em] text-zinc-500'>Search docs</label>
          <div className='mt-3 flex items-center gap-3 rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3'>
            {SharedIcons.search({ className: 'h-4 w-4 text-zinc-500' })}
            <input
              id='docs-search'
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder='Search quickstart, WebSocket, deployment, FAQ...'
              className='w-full border-none bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-500'
            />
          </div>
        </div>
      </section>

      {query.trim() ? (
        <section className='grid gap-4'>
          <div className='flex items-center gap-3'>
            {SharedIcons.search({ className: 'h-4 w-4 text-cyan-200' })}
            <h2 className='text-lg font-semibold text-white'>Search results</h2>
          </div>
          <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-3'>
            {results.map((page) => (
              <button
                key={page.slug}
                type='button'
                onClick={() => onNavigate(page.slug)}
                className='rounded-3xl border border-white/8 bg-[#0c1018] p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/6'
              >
                <p className='text-xs uppercase tracking-[0.2em] text-zinc-500'>{page.section}</p>
                <h3 className='mt-3 text-lg font-semibold text-white'>{page.title}</h3>
                <p className='mt-3 text-sm leading-7 text-zinc-300'>{page.summary}</p>
              </button>
            ))}
            {results.length === 0 && (
              <div className='rounded-3xl border border-white/8 bg-[#0c1018] p-5 text-sm text-zinc-400'>
                No docs matched your search yet.
              </div>
            )}
          </div>
        </section>
      ) : (
        <>
          <section className='grid gap-4'>
            <div className='flex items-center gap-3'>
              {SharedIcons.star({ className: 'h-4 w-4 text-cyan-200' })}
              <h2 className='text-lg font-semibold text-white'>Featured docs</h2>
            </div>
            <div className='grid gap-4 md:grid-cols-2 xl:grid-cols-4'>
              {featured.map((page) => (
                <button
                  key={page.slug}
                  type='button'
                  onClick={() => onNavigate(page.slug)}
                  className='rounded-3xl border border-white/8 bg-[#0c1018] p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/6'
                >
                  <p className='text-xs uppercase tracking-[0.2em] text-zinc-500'>{page.section}</p>
                  <h3 className='mt-3 text-lg font-semibold text-white'>{page.title}</h3>
                  <p className='mt-3 text-sm leading-7 text-zinc-300'>{page.summary}</p>
                </button>
              ))}
            </div>
          </section>

          <section className='grid gap-6 xl:grid-cols-2'>
            {listDocsSections().map((section) => {
              const pages = getDocsPagesBySection(section.id)
              return (
                <article key={section.id} className='rounded-[32px] border border-white/8 bg-[#0c1018] p-6'>
                  <div className='flex items-center gap-3'>
                    {SharedIcons.workflows({ className: 'h-4 w-4 text-cyan-200' })}
                    <h2 className='text-lg font-semibold text-white'>{section.title}</h2>
                  </div>
                  <p className='mt-3 text-sm leading-7 text-zinc-400'>{section.description}</p>
                  <div className='mt-5 grid gap-3'>
                    {pages.map((page) => (
                      <button
                        key={page.slug}
                        type='button'
                        onClick={() => onNavigate(page.slug)}
                        className='rounded-2xl border border-white/8 bg-white/3 px-4 py-4 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/6'
                      >
                        <p className='text-sm font-semibold text-white'>{page.title}</p>
                        <p className='mt-2 text-sm leading-7 text-zinc-300'>{page.summary}</p>
                      </button>
                    ))}
                  </div>
                </article>
              )
            })}
          </section>
        </>
      )}
    </div>
  )
}
