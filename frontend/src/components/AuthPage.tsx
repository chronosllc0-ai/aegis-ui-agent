import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../lib/api'
import { getStandaloneDocUrl } from '../lib/site'
import { EntrySlider, type EntrySlide } from './EntrySlider'
import { Icons } from './icons'
import { useToast } from '../hooks/useToast'
import { PublicHeader } from '../public/PublicHeader'
import { PasswordInput } from './PasswordInput'
import { PasswordStrength, usePasswordCriteria } from './PasswordStrength'

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

/* ── Email-exists debounced check ─────────────────────────────────── */

function useEmailExistsCheck() {
  const [emailExists, setEmailExists] = useState<boolean | null>(null)
  const [checking, setChecking] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null)
  const abortRef = useRef<AbortController | null>(null)

  const check = useCallback((email: string, mode: 'signin' | 'signup') => {
    // Reset when not in signup or email is incomplete
    setEmailExists(null)
    setChecking(false)
    if (timerRef.current) clearTimeout(timerRef.current)
    if (abortRef.current) abortRef.current.abort()

    if (mode !== 'signup') return
    const trimmed = email.trim().toLowerCase()
    if (!trimmed || !trimmed.includes('@') || !trimmed.includes('.')) return

    setChecking(true)
    timerRef.current = setTimeout(async () => {
      const controller = new AbortController()
      abortRef.current = controller
      try {
        const res = await fetch(apiUrl('/api/auth/email/check'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: trimmed }),
          signal: controller.signal,
        })
        if (res.ok) {
          const data = await res.json()
          setEmailExists(data.exists ?? null)
        }
      } catch {
        /* ignore abort / network errors */
      } finally {
        setChecking(false)
      }
    }, 600) // 600ms debounce
  }, [])

  const reset = useCallback(() => {
    setEmailExists(null)
    setChecking(false)
    if (timerRef.current) clearTimeout(timerRef.current)
    if (abortRef.current) abortRef.current.abort()
  }, [])

  return { emailExists, checking, check, reset }
}

/* ── Main component ──────────────────────────────────────────────── */

export function AuthPage({ onAuthenticated, onBack, onOpenDocsHome, onOpenDoc }: AuthPageProps) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()

  const { emailExists, checking: emailChecking, check: checkEmail, reset: resetEmailCheck } = useEmailExistsCheck()
  const { criteria } = usePasswordCriteria(password)
  const allCriteriaMet = criteria.every((c) => c.met)

  // Debounce email check on change
  useEffect(() => {
    checkEmail(email, mode)
  }, [email, mode, checkEmail])

  const submit = async () => {
    if (!email || !password) return
    if (mode === 'signup') {
      if (!allCriteriaMet) {
        setError('Please meet all password requirements above.')
        setMessage(null)
        return
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.')
        setMessage(null)
        return
      }
      if (emailExists) {
        setError('An account with this email already exists. Switch to Sign in.')
        setMessage(null)
        return
      }
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
        const errMsg = 'Could not reach the backend. Check the deployed API URL and try again.'
        setError(errMsg)
        toast.error('Connection error', errMsg)
      } else {
        const errMsg = err instanceof Error ? err.message : mode === 'signup' ? 'Sign-up failed.' : 'Sign-in failed.'
        setError(errMsg)
        toast.error(mode === 'signup' ? 'Sign-up failed' : 'Sign-in failed', errMsg)
      }
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (newMode: 'signin' | 'signup') => {
    setMode(newMode)
    setError(null)
    setMessage(null)
    resetEmailCheck()
  }

  // Determine if the Create Account button should be disabled in signup mode
  const signupDisabled =
    mode === 'signup' && (!allCriteriaMet || !confirmPassword || password !== confirmPassword || emailExists === true)

  return (
    <main className='min-h-screen bg-[#070b12] text-zinc-100'>
      <PublicHeader
        onGoHome={onBack}
        onGoAuth={() => undefined}
        onGoDocsHome={onOpenDocsHome}
        onGoDoc={onOpenDoc}
        docsPortalHref={getStandaloneDocUrl()}
      />

      <div className='mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 sm:gap-10 sm:px-6 sm:py-12 lg:grid-cols-[0.92fr_1.08fr] lg:py-18'>
        <section className='rounded-2xl border border-white/8 bg-[#0c1018] p-4 shadow-[0_24px_70px_rgba(0,0,0,0.32)] sm:rounded-[32px] sm:p-7'>
          <div className='flex items-center gap-3'>
            <img src='/shield.svg' alt='Aegis logo' className='h-11 w-11' />
            <div>
              <p className='text-lg font-semibold text-white'>Aegis</p>
              <p className='text-sm text-zinc-400'>Sign in or create an account to start a live navigation session.</p>
            </div>
          </div>

          {/* ── mode toggle ── */}
          <div className='mt-6 grid grid-cols-2 rounded-2xl border border-white/8 bg-[#080b12] p-1 text-sm'>
            <button
              type='button'
              onClick={() => switchMode('signin')}
              className={`rounded-2xl px-4 py-3 transition ${mode === 'signin' ? 'bg-cyan-500 text-slate-950' : 'text-zinc-300 hover:bg-white/6'}`}
            >
              Sign in
            </button>
            <button
              type='button'
              onClick={() => switchMode('signup')}
              className={`rounded-2xl px-4 py-3 transition ${mode === 'signup' ? 'bg-cyan-500 text-slate-950' : 'text-zinc-300 hover:bg-white/6'}`}
            >
              Sign up
            </button>
          </div>

          {/* ── OAuth providers ── */}
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

          {/* ── form fields ── */}
          <div className='grid gap-3 text-left text-sm'>
            {mode === 'signup' && (
              <>
                <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Name</label>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder='Your name'
                  autoComplete='name'
                  className='w-full rounded-2xl border border-white/8 bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
                />
              </>
            )}

            <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Email</label>
            <div className='relative'>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder='you@company.com'
                autoComplete='email'
                className={`w-full rounded-2xl border bg-[#090c13] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30 ${
                  emailExists ? 'border-amber-500/50' : 'border-white/8'
                }`}
              />
              {emailChecking && (
                <span className='absolute right-3 top-1/2 -translate-y-1/2 text-xs text-zinc-500'>checking…</span>
              )}
            </div>
            {emailExists && mode === 'signup' && (
              <p className='flex items-center gap-2 rounded-xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200'>
                <svg viewBox='0 0 16 16' className='h-3.5 w-3.5 shrink-0' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round'>
                  <circle cx='8' cy='8' r='6' /><path d='M8 5v3M8 10.5h.01' />
                </svg>
                This email is already registered.{' '}
                <button type='button' onClick={() => switchMode('signin')} className='font-medium text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>
                  Sign in instead
                </button>
              </p>
            )}

            <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Password</label>
            <PasswordInput
              value={password}
              onChange={setPassword}
              placeholder='Enter your password'
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            />

            {/* password strength indicator — only during signup */}
            {mode === 'signup' && <PasswordStrength password={password} />}

            {mode === 'signup' && (
              <>
                <label className='text-xs uppercase tracking-[0.22em] text-zinc-500'>Confirm password</label>
                <PasswordInput
                  value={confirmPassword}
                  onChange={setConfirmPassword}
                  placeholder='Repeat your password'
                  autoComplete='new-password'
                />
                {confirmPassword && password !== confirmPassword && (
                  <p className='text-xs text-red-400'>Passwords do not match.</p>
                )}
                {confirmPassword && password === confirmPassword && confirmPassword.length > 0 && (
                  <p className='flex items-center gap-1.5 text-xs text-emerald-400'>
                    <svg viewBox='0 0 16 16' className='h-3 w-3' fill='none' stroke='currentColor' strokeWidth='2.5' strokeLinecap='round' strokeLinejoin='round'>
                      <path d='m3 8 3.5 3.5L13 5' />
                    </svg>
                    Passwords match
                  </p>
                )}
              </>
            )}

            <button
              type='button'
              onClick={submit}
              disabled={busy || !email || !password || (mode === 'signup' && (signupDisabled || !confirmPassword))}
              className='mt-2 rounded-2xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60'
            >
              {busy ? (
                <span className='flex items-center justify-center gap-2'>
                  <svg className='h-4 w-4 animate-spin' viewBox='0 0 24 24' fill='none'>
                    <circle cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='3' className='opacity-25' />
                    <path d='M4 12a8 8 0 0 1 8-8' stroke='currentColor' strokeWidth='3' strokeLinecap='round' className='opacity-75' />
                  </svg>
                  {mode === 'signup' ? 'Creating account…' : 'Signing in…'}
                </span>
              ) : mode === 'signup' ? (
                'Create account'
              ) : (
                'Sign in'
              )}
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
