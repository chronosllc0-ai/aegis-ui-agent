import { Icons } from '../components/icons'
import { CHRONOS_LOGO_URL } from '../lib/models'

type PublicHeaderProps = {
  onGoHome: () => void
  onGoAuth: () => void
  onGoDocsHome: () => void
  onGoDoc: (slug: string) => void
  docsPortalHref: string
}

export function PublicHeader({ onGoHome, onGoAuth, onGoDocsHome, onGoDoc, docsPortalHref }: PublicHeaderProps) {
  return (
    <header className='sticky top-0 z-20 border-b border-white/8 bg-[#0a0d14]/82 backdrop-blur-xl'>
      <div className='mx-auto flex w-full max-w-7xl items-center justify-between gap-6 px-6 py-5'>
        <button type='button' onClick={onGoHome} className='flex items-center gap-3 text-left'>
          <img src={CHRONOS_LOGO_URL} alt='Chronos AI' className='chronos-spin h-8 w-8 rounded-full' />
          <div>
            <p className='text-sm font-semibold text-white'>Aegis</p>
            <p className='text-[11px] uppercase tracking-[0.22em] text-cyan-200'>by Chronos AI</p>
          </div>
        </button>

        <nav className='hidden items-center gap-5 text-sm text-zinc-300 lg:flex'>
          <button type='button' onClick={onGoHome} className='transition hover:text-white'>Product</button>
          <button type='button' onClick={onGoDocsHome} className='transition hover:text-white'>Docs</button>
          <button type='button' onClick={() => onGoDoc('first-live-run')} className='transition hover:text-white'>Tutorials</button>
          <button type='button' onClick={() => onGoDoc('api-auth-reference')} className='transition hover:text-white'>API</button>
          <button type='button' onClick={() => onGoDoc('faq')} className='transition hover:text-white'>FAQ</button>
          <button type='button' onClick={() => onGoDoc('changelog')} className='transition hover:text-white'>Changelog</button>
          <a href={docsPortalHref} className='transition hover:text-white'>Docs portal</a>
        </nav>

        <div className='flex items-center gap-3'>
          <button
            type='button'
            onClick={onGoDocsHome}
            className='hidden rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-200 transition hover:border-cyan-400/30 hover:bg-cyan-400/8 md:inline-flex'
          >
            Read docs
          </button>
          <button
            type='button'
            onClick={onGoAuth}
            className='inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
          >
            {Icons.user({ className: 'h-4 w-4' })}
            <span>Get started</span>
          </button>
        </div>
      </div>
    </header>
  )
}
