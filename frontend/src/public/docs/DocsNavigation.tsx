import { getDocsPage, getDocsPagesBySection, listDocsSections, type DocsPage } from '../../../../shared/docs'
import { SharedIcons } from './SharedIcons'

type DocsNavigationProps = {
  activeSlug?: string | null
  onNavigate: (slug: string) => void
  onGoHome: () => void
}

export function DocsNavigation({ activeSlug, onNavigate, onGoHome }: DocsNavigationProps) {
  return (
    <aside className='rounded-[32px] border border-white/8 bg-[#0c1018] p-5 shadow-[0_24px_70px_rgba(0,0,0,0.28)]'>
      <button
        type='button'
        onClick={onGoHome}
        className='flex w-full items-center gap-3 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-left text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/14'
      >
        {SharedIcons.globe({ className: 'h-4 w-4' })}
        <span>Docs home</span>
      </button>

      <div className='mt-6 grid gap-6'>
        {listDocsSections().map((section) => {
          const pages = getDocsPagesBySection(section.id)
          return (
            <section key={section.id} className='grid gap-3'>
              <div>
                <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>{section.title}</p>
                <p className='mt-2 text-xs leading-6 text-zinc-400'>{section.description}</p>
              </div>
              <div className='grid gap-2'>
                {pages.map((page) => {
                  const active = activeSlug === page.slug || (!activeSlug && getDocsPage(page.slug)?.slug === page.slug && page.slug === 'quickstart')
                  return (
                    <button
                      key={page.slug}
                      type='button'
                      onClick={() => onNavigate(page.slug)}
                      className={`rounded-2xl border px-4 py-3 text-left transition ${
                        active
                          ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100'
                          : 'border-white/8 bg-white/3 text-zinc-300 hover:border-white/16 hover:bg-white/5'
                      }`}
                    >
                      <p className='text-sm font-medium'>{page.title}</p>
                      <p className='mt-2 text-xs leading-6 text-zinc-400'>{page.summary}</p>
                    </button>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>
    </aside>
  )
}

type DocsSectionStripProps = {
  currentPage?: DocsPage
}

export function DocsSectionStrip({ currentPage }: DocsSectionStripProps) {
  return (
    <div className='flex flex-wrap gap-2 text-xs text-zinc-400'>
      {listDocsSections().map((section) => (
        <span
          key={section.id}
          className={`rounded-full border px-3 py-1 ${
            currentPage?.section === section.id ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-100' : 'border-white/10'
          }`}
        >
          {section.title}
        </span>
      ))}
    </div>
  )
}
