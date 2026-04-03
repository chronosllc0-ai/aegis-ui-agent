import { useState } from 'react'
import { Icons } from '../components/icons'

type PublicHeaderProps = {
  onGoHome: () => void
  onGoAuth: () => void
  onGoDocsHome: () => void
  onGoDoc: (slug: string) => void
  docsPortalHref: string
}

export function PublicHeader({ onGoHome, onGoAuth, onGoDocsHome, onGoDoc: _onGoDoc, docsPortalHref }: PublicHeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <header className='sticky top-0 z-20 border-b border-white/8 bg-[#0a0d14]/82 backdrop-blur-xl'>
      <div className='mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:gap-6 sm:px-6 sm:py-5'>
        <button type='button' onClick={onGoHome} className='flex items-center gap-2 text-left sm:gap-3'>
          <img src='/aegis-shield.png' alt='Aegis logo' className='h-7 w-7 sm:h-8 sm:w-8' />
          <div>
            <p className='text-sm font-semibold text-white'>Aegis</p>
            <p className='hidden text-[11px] uppercase tracking-[0.22em] text-cyan-200 sm:block'>by Chronos AI</p>
          </div>
        </button>

        <nav className='hidden items-center gap-5 text-sm text-zinc-300 lg:flex'>
          <a href='/#features' className='transition hover:text-white'>Features</a>
          <a href='/#use-cases' className='transition hover:text-white'>Use cases</a>
          <a href='/#faq' className='transition hover:text-white'>FAQ</a>
          <a href='/#pricing' className='transition hover:text-white'>Pricing</a>
          <button type='button' onClick={onGoDocsHome} className='transition hover:text-white'>Docs</button>
          <a href={docsPortalHref} className='transition hover:text-white'>Docs portal</a>
        </nav>

        <div className='flex items-center gap-2 sm:gap-3'>
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
            className='inline-flex items-center gap-1.5 rounded-full bg-cyan-500 px-3 py-1.5 text-xs font-medium text-slate-950 transition hover:bg-cyan-400 sm:gap-2 sm:px-4 sm:py-2 sm:text-sm'
          >
            {Icons.user({ className: 'h-3.5 w-3.5 sm:h-4 sm:w-4' })}
            <span>Get started</span>
          </button>
          {/* Mobile hamburger */}
          <button
            type='button'
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className='rounded border border-white/10 p-1.5 text-zinc-300 transition hover:bg-white/8 lg:hidden'
            aria-label='Toggle menu'
          >
            {Icons.menu({ className: 'h-5 w-5' })}
          </button>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileMenuOpen && (
        <nav className='border-t border-white/8 bg-[#0a0d14]/95 px-4 py-4 backdrop-blur-xl lg:hidden'>
          <div className='grid gap-2 text-sm text-zinc-300'>
            <a href='/#features' onClick={() => setMobileMenuOpen(false)} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>Features</a>
            <a href='/#use-cases' onClick={() => setMobileMenuOpen(false)} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>Use cases</a>
            <a href='/#faq' onClick={() => setMobileMenuOpen(false)} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>FAQ</a>
            <a href='/#pricing' onClick={() => setMobileMenuOpen(false)} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>Pricing</a>
            <button type='button' onClick={() => { onGoDocsHome(); setMobileMenuOpen(false) }} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>Docs</button>
            <a href={docsPortalHref} onClick={() => setMobileMenuOpen(false)} className='rounded-lg px-3 py-2.5 text-left transition hover:bg-white/6 hover:text-white'>Docs portal</a>
          </div>
        </nav>
      )}
    </header>
  )
}
