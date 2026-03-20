import { useState } from 'react'
import { apiUrl } from '../lib/api'
import { getStandaloneDocUrl } from '../lib/site'
import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { PublicHeader } from '../public/PublicHeader'

const GOOGLE_ICON_URL = 'https://i.postimg.cc/2SwWrKwz/download_1.jpg'
const GITHUB_ICON_URL = 'https://i.postimg.cc/BZXzgmHC/download_27.png'

type AuthUser = {
  uid: string
  email: string
  name: string
  avatar_url?: string | null
  provider?: string
}

type AuthPageProps = {
  onAuthenticated: (user: AuthUser) => void
  onBack: () => void
  onOpenDocsHome: () => void
  onOpenDoc: (slug: string) => void
}

const AUTH_SLIDES: EntrySlide[] = [
  {
    id: 'path',
    eyebrow: 'First session path',
    title: 'Sign in, connect a model, and run the first task without guesswork.',
    description:
      'The auth surface should do more than collect credentials. It should explain the next two or three moves clearly so the first run feels intentional.',
    bullets: [
      'Choose a sign-in method that matches the environment',
      'Connect provider keys if you are using BYOK',
      'Start from the quickstart or tutorial if you need a guided first run',
    ],
    statLabel: 'Onboarding',
    statValue: 'Auth -> Settings -> Live session',
    icon: (className) => Icons.user({ className }),
  },
  {
    id: 'proof',
    eyebrow: 'Product proof',
    title: 'The operator shell is built for live supervision, not blind fire-and-forget automation.',
    description:
      'Aegis keeps the frame, action log, workflow view, and transcripts visible while the session is running. That makes it easier to trust, redirect, and reuse successful work.',
    bullets: [
      'Real-time frame and action log updates',
      'Workflow capture after a successful run',
      'Steer, interrupt, and queue controls inside the session',
    ],
    statLabel: 'Operator mode',
    statValue: 'Live + visible',
    icon: (className) => Icons.workflows({ className }),
  },
  {
    id: 'docs',
    eyebrow: 'Docs assist',
    title: 'Need setup help? The relevant docs are one click away.',
    description:
      'Quickstart, auth details, provider-key setup, and deployment notes should be available directly from auth so the user never feels stuck at the gate.',
    bullets: [
      'Read the auth guide without leaving the main app domain',
      'Jump to tutorials for a guided first-run path',
      'Open the standalone docs portal for deeper browsing',
    ],
    statLabel: 'Docs links',
    statValue: 'Embedded + standalone',
    icon: (className) => Icons.globe({ className }),
  },
]

export function AuthPage({ onAuthenticated, onBack, onOpenDocsHome, onOpenDoc }: AuthPageProps) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!email || !password) return
    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match.')
      setMessage(null)
      return
    }

    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const response = await fetch(apiUrl(mode === 'signup' ? '/api/auth/password/signup' : '/api/auth/password/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password, name }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        if (response.status === 503) {
          throw new Error('The backend is still starting. Retry in a few seconds.')
        }
        throw new Error(data?.detail ?? (mode === 'signup' ? 'Sign-up failed.' : 'Sign-in failed.'))
      }
      if (data?.user) onAuthenticated(data.user as AuthUser)
      else setMessage(mode === 'signup' ? 'Account created.' : 'Signed in.')
    } catch (err) {
      if (err instanceof TypeError) {
        setError('Could not reach the backend. Check the deployed API URL and try again.')
      } else {
        setError(err instanceof Error ? err.message : mode === 'signup' ? 'Sign-up failed.' : 'Sign-in failed.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className='min-h-screen bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={onBack}
        onGoAuth={() => undefined}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={getStandaloneDocUrl()}
      />

      <div className='mx-auto grid w-full max-w-7xl gap-10 px-6 py-12 lg:grid-cols-[0.92fr_1.08fr] lg:py-18'>
        <section className='rounded-[32px] border border-white/8 bg-[#0c1018] p-7 shadow-[0_24px_70px_rgba(0,0,0,0.32)]'>
          <div className='flex items-center gap-3'>
            <img src='/shield.svg' alt='Aegis logo' className='h-11 w-11' />
            <div>
              <p className='text-lg font-semibold text-white'>Aegis</p>
              <p className='text-sm text-zinc-400'>Sign in or create an account to start a live navigation session.</p>
            </div>
          </div>

          <div className='mt-6 grid grid-cols-2 rounded-2xl border border-white/8 bg-[#080b12] p-1 text-sm'>
            <button
              type='button'
              onClick={() => { setMode('signin'); setError(null); setMessage(null) }}
              className={`rounded-2xl px-4 py-3 transition ${mode === 'signin' ? 'bg-cyan-500 text-slate-950' : 'text-zinc-300 hover:bg-white/6'}`}
            >
              Sign in
            </button>
            <button
              type='button'
              onClick={() => { setMode('signup'); setError(null); setMessage(null) }}
              className={`rounded-2xl px-4 py-3 transition ${mode === 'signup' ? 'bg-cyan-500 text-slate-950' : 'text-zinc-300 hover:bg-white/6'}`}
            >
              Sign up
            </button>
          </div>

          <div className='mt-6 grid gap-3'>
            <button
              type='button'
              onClick={() => { window.location.href = apiUrl('/api/auth/google/login') }}
              className='flex w-full items-center justify-center gap-3 rounded-2xl border border-white/8 bg-white/3 px-4 py-3 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              <img src={GOOGLE_ICON_URL} alt='Google' className='h-5 w-5 rounded-sm' />
              <span>Continue with Google</span>
            </button>
            <button
              type='button'
              onClick={() => { window.location.href = apiUrl('/api/auth/github/login') }}
              className='flex w-full items-center justify-center gap-3 rounded-2xl border border-white/8 bg-white/3 px-4 py-3 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              <img src={GITHUB_ICON_URL} alt='GitHub' className='h-5 w-5 rounded-sm' />
              <span>Continue with GitHub</span>
            </button>
            <button
              type='button'
              onClick={() => { window.location.href = apiUrl('/api/auth/sso/login') }}
              className='flex w-full items-center justify-center gap-3 rounded-2xl border border-white/8 bg-white/3 px-4 py-3 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'
            >
              {Icons.user({ className: 'h-4 w-4 text-zinc-300' })}
              <span>Continue with SSO</span>
            </button>
          </div>

          <div className='my-6 flex items-center gap-3 text-xs uppercase tracking-[0.24em] text-zinc-500'>
            <span className='h-px w-full bg-white/8' />
            or
            <span className='h-px w-full bg-white/8' />
          </div>

          <div className='grid gap-3 text-left text-sm'>
            {mode === 'signup' && (
              <>
                <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Name</label>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder='Your name'
                  className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
                />
              </>
            )}

            <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Email</label>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder='you@company.com'
              className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
            />

            <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Password</label>
            <input
              type='password'
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder='Enter your password'
              className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
            />

            {mode === 'signup' && (
              <>
                <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Confirm password</label>
                <input
                  type='password'
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder='Repeat your password'
                  className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
                />
              </>
            )}

            <button
              type='button'
              onClick={submit}
              disabled={busy || !email || !password || (mode === 'signup' && !confirmPassword)}
              className='mt-2 rounded-2xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60'
            >
              {mode === 'signup' ? 'Create account' : 'Sign in'}
            </button>

            {message && <p className='rounded-2xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200'>{message}</p>}
            {error && <p className='rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-200'>{error}</p>}
          </div>

          <div className='mt-8 grid gap-3 rounded-3xl border border-white/8 bg-white/3 p-5'>
            <p className='text-xs uppercase tracking-[0.24em] text-zinc-500'>Need setup help?</p>
            <div className='flex flex-wrap gap-3'>
              <button type='button' onClick={() => onOpenDoc('quickstart')} className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>
                Quickstart
              </button>
              <button type='button' onClick={() => onOpenDoc('authentication')} className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>
                Auth guide
              </button>
              <button type='button' onClick={() => onOpenDoc('provider-keys')} className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>
                Provider keys
              </button>
              <button type='button' onClick={() => onOpenDoc('deployment')} className='rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-100 transition hover:border-cyan-400/30 hover:bg-cyan-400/8'>
                Deployment
              </button>
            </div>
            <button type='button' onClick={onBack} className='justify-self-start text-sm text-zinc-400 transition hover:text-white'>
              Back to home
            </button>
          </div>
        </section>

        <EntrySlider slides={AUTH_SLIDES} className='self-start lg:sticky lg:top-28' />
      </div>
    </main>
  )
}
