import { CHRONOS_LOGO_URL } from '../lib/models'
import { PRIVACY_PATH, TERMS_PATH } from '../lib/routes'

type PublicFooterProps = {
  onGoHome: () => void
  onGoAuth: () => void
  onGoDocsHome: () => void
  onGoDoc: (slug: string) => void
  docsPortalHref: string
}

const FOOTER_GROUPS = [
  {
    title: 'Product',
    links: [
      { label: 'Overview', slug: 'home' },
      { label: 'Quickstart', slug: 'quickstart' },
      { label: 'Live sessions', slug: 'live-sessions' },
      { label: 'Integrations', slug: 'integrations' },
    ],
  },
  {
    title: 'Docs',
    links: [
      { label: 'Docs home', slug: 'docs-home' },
      { label: 'API reference', slug: 'api-auth-reference' },
      { label: 'Tutorials', slug: 'first-live-run' },
      { label: 'FAQ', slug: 'faq' },
    ],
  },
  {
    title: 'Operators',
    links: [
      { label: 'Authentication', slug: 'authentication' },
      { label: 'Provider keys', slug: 'provider-keys' },
      { label: 'Workflows', slug: 'workflow-templates' },
      { label: 'Deployment', slug: 'deployment' },
    ],
  },
]

export function PublicFooter({ onGoHome, onGoAuth, onGoDocsHome, onGoDoc, docsPortalHref }: PublicFooterProps) {
  return (
    <footer className='border-t border-white/8 bg-[#090c13]'>
      <div className='mx-auto grid w-full max-w-7xl gap-12 px-6 py-14 lg:grid-cols-[1.2fr_2fr]'>
        <div>
          <button type='button' onClick={onGoHome} className='flex items-center gap-3 text-left'>
            <img src={CHRONOS_LOGO_URL} alt='Chronos AI' className='chronos-spin h-10 w-10 rounded-full' />
            <div>
              <p className='text-lg font-semibold text-white'>Aegis</p>
              <p className='text-sm text-zinc-400'>by Chronos AI</p>
            </div>
          </button>
          <p className='mt-5 max-w-md text-sm leading-7 text-zinc-400'>
            The public site, auth surface, embedded docs, and standalone docs portal are built to guide operators from discovery to live execution.
          </p>
          <div className='mt-6 flex flex-wrap gap-3 text-sm'>
            <button
              type='button'
              onClick={onGoAuth}
              className='rounded-full bg-cyan-500 px-4 py-2 font-medium text-slate-950 transition hover:bg-cyan-400'
            >
              Sign in
            </button>
            <button
              type='button'
              onClick={onGoDocsHome}
              className='rounded-full border border-white/10 px-4 py-2 text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              Embedded docs
            </button>
            <a
              href={docsPortalHref}
              className='rounded-full border border-white/10 px-4 py-2 text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              Standalone docs
            </a>
          </div>
        </div>

        <div className='grid gap-10 sm:grid-cols-3'>
          {FOOTER_GROUPS.map((group) => (
            <section key={group.title}>
              <p className='text-[11px] uppercase tracking-[0.24em] text-zinc-500'>{group.title}</p>
              <div className='mt-4 grid gap-3 text-sm text-zinc-300'>
                {group.links.map((link) => {
                  if (link.slug === 'home') {
                    return <button key={link.label} type='button' onClick={onGoHome} className='text-left transition hover:text-white'>{link.label}</button>
                  }
                  if (link.slug === 'docs-home') {
                    return <button key={link.label} type='button' onClick={onGoDocsHome} className='text-left transition hover:text-white'>{link.label}</button>
                  }
                  return <button key={link.label} type='button' onClick={() => onGoDoc(link.slug)} className='text-left transition hover:text-white'>{link.label}</button>
                })}
              </div>
            </section>
          ))}
        </div>
      </div>

      {/* Legal bar */}
      <div className='border-t border-white/6 px-6 py-4'>
        <div className='mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 text-xs text-zinc-600'>
          <span>© {new Date().getFullYear()} Chronos AI. All rights reserved.</span>
          <div className='flex gap-5'>
            <a
              href={PRIVACY_PATH}
              className='transition hover:text-zinc-300'
            >
              Privacy Policy
            </a>
            <a
              href={TERMS_PATH}
              className='transition hover:text-zinc-300'
            >
              Terms of Service
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
