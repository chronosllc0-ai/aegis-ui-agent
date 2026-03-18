import { useState } from 'react'
import { apiUrl } from '../lib/api'
import { Icons } from './icons'

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
  onBack?: () => void
}

export function AuthPage({ onAuthenticated, onBack }: AuthPageProps) {
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
      if (!response.ok) throw new Error(data?.detail ?? (mode === 'signup' ? 'Sign-up failed.' : 'Sign-in failed.'))
      if (data?.user) onAuthenticated(data.user as AuthUser)
      else setMessage(mode === 'signup' ? 'Account created.' : 'Signed in.')
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === 'signup' ? 'Sign-up failed.' : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className='flex min-h-screen items-center justify-center bg-[#111] text-zinc-100'>
      <section className='w-full max-w-md rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] p-6 text-center'>
        <img src='/shield.svg' alt='Aegis logo' className='mx-auto mb-4 h-14 w-14' />
        <h1 className='text-2xl font-semibold'>{mode === 'signup' ? 'Create your Aegis account' : 'Sign in to Aegis'}</h1>
        <p className='mt-2 text-sm text-zinc-400'>
          {mode === 'signup' ? 'Create an account with email and password, or use SSO.' : 'Use SSO or your email and password to start a live navigation session.'}
        </p>

        <div className='mt-5 grid grid-cols-2 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-1 text-sm'>
          <button
            type='button'
            onClick={() => { setMode('signin'); setError(null); setMessage(null) }}
            className={`rounded-md px-3 py-2 transition ${mode === 'signin' ? 'bg-blue-600 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}
          >
            Sign in
          </button>
          <button
            type='button'
            onClick={() => { setMode('signup'); setError(null); setMessage(null) }}
            className={`rounded-md px-3 py-2 transition ${mode === 'signup' ? 'bg-blue-600 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}
          >
            Sign up
          </button>
        </div>

        <div className='mt-5 space-y-2'>
          <button
            type='button'
            onClick={() => { window.location.href = apiUrl('/api/auth/google/login') }}
            className='flex w-full items-center justify-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-4 py-2 text-sm hover:border-blue-500/60'
          >
            <img src={GOOGLE_ICON_URL} alt='Google' className='h-5 w-5 rounded-sm' />
            Continue with Google
          </button>
          <button
            type='button'
            onClick={() => { window.location.href = apiUrl('/api/auth/github/login') }}
            className='flex w-full items-center justify-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-4 py-2 text-sm hover:border-blue-500/60'
          >
            <img src={GITHUB_ICON_URL} alt='GitHub' className='h-5 w-5 rounded-sm' />
            Continue with GitHub
          </button>
          <button
            type='button'
            onClick={() => { window.location.href = apiUrl('/api/auth/sso/login') }}
            className='flex w-full items-center justify-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-4 py-2 text-sm hover:border-blue-500/60'
          >
            {Icons.user({ className: 'h-4 w-4 text-zinc-300' })}
            Continue with SSO
          </button>
        </div>

        <div className='my-5 flex items-center gap-3 text-xs text-zinc-500'>
          <span className='h-px w-full bg-[#2a2a2a]' />
          or
          <span className='h-px w-full bg-[#2a2a2a]' />
        </div>

        <div className='space-y-2 text-left text-sm'>
          {mode === 'signup' && (
            <>
              <label className='text-xs text-zinc-400'>Name</label>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder='Your name'
                className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm'
              />
            </>
          )}
          <label className='text-xs text-zinc-400'>Email</label>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder='you@company.com'
            className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm'
          />
          <label className='text-xs text-zinc-400'>Password</label>
          <input
            type='password'
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder='Enter your password'
            className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm'
          />
          {mode === 'signup' && (
            <>
              <label className='text-xs text-zinc-400'>Confirm password</label>
              <input
                type='password'
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder='Repeat your password'
                className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2 text-sm'
              />
            </>
          )}
          <button type='button' onClick={submit} disabled={busy || !email || !password || (mode === 'signup' && !confirmPassword)} className='w-full rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium hover:bg-blue-500 disabled:opacity-60'>
            {mode === 'signup' ? 'Create account' : 'Sign in'}
          </button>
          {message && <p className='text-xs text-emerald-300'>{message}</p>}
          {error && <p className='text-xs text-red-300'>{error}</p>}
        </div>

        {onBack && (
          <button type='button' onClick={onBack} className='mt-4 text-xs text-zinc-400 hover:text-zinc-200'>
            Back to home
          </button>
        )}
      </section>
    </main>
  )
}
