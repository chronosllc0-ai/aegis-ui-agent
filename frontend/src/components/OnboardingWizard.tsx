import { useState } from 'react'
import { Icons } from './icons'
import { PROVIDERS, renderProviderIcon } from '../lib/models'
import { apiUrl } from '../lib/api'
import { useToast } from '../hooks/useToast'

/* ── storage key ─────────────────────────────────────────────────── */
const ONBOARDING_KEY = 'aegis.onboarding.complete'
export const isOnboardingComplete = () => localStorage.getItem(ONBOARDING_KEY) === '1'
export const markOnboardingComplete = () => localStorage.setItem(ONBOARDING_KEY, '1')

/* ── types ────────────────────────────────────────────────────────── */
type WizardProps = {
  userName: string
  userEmail: string
  onComplete: (data: OnboardingData) => void
}

export type OnboardingData = {
  useCase: string
  displayName: string
}

const USE_CASES = [
  { id: 'automation', label: 'Browser Automation', desc: 'Automate repetitive web tasks', icon: '🤖' },
  { id: 'testing', label: 'QA & Testing', desc: 'Test web applications visually', icon: '🧪' },
  { id: 'extraction', label: 'Data Extraction', desc: 'Scrape and collect web data', icon: '📊' },
  { id: 'development', label: 'Development', desc: 'Build & prototype with AI assist', icon: '💻' },
  { id: 'research', label: 'Research', desc: 'Navigate and summarise web sources', icon: '🔍' },
  { id: 'other', label: 'Something Else', desc: 'Explore what Aegis can do', icon: '✨' },
]

/* ── step indicator ───────────────────────────────────────────────── */
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className='flex items-center gap-2'>
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-1.5 rounded-full transition-all ${
            i === current ? 'w-8 bg-cyan-400' : i < current ? 'w-4 bg-cyan-400/40' : 'w-4 bg-white/10'
          }`}
        />
      ))}
    </div>
  )
}

/* ── main wizard ─────────────────────────────────────────────────── */
export function OnboardingWizard({ userName, userEmail, onComplete }: WizardProps) {
  const [step, setStep] = useState(0)
  const [useCase, setUseCase] = useState<string | null>(null)
  const [displayName, setDisplayName] = useState(userName || '')
  const [selectedProvider, setSelectedProvider] = useState('google')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [keySaved, setKeySaved] = useState(false)
  const toast = useToast()

  const TOTAL_STEPS = 4

  const next = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1))
  const back = () => setStep((s) => Math.max(s - 1, 0))

  const saveApiKey = async () => {
    if (!apiKey.trim()) return
    setSaving(true)
    try {
      const res = await fetch(apiUrl('/api/keys'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ provider: selectedProvider, api_key: apiKey.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail ?? 'Failed to save key')
      toast.success('API key saved', `${selectedProvider} key connected.`)
      setKeySaved(true)
    } catch (err) {
      toast.error('Failed to save key', err instanceof Error ? err.message : 'Try again.')
    } finally {
      setSaving(false)
    }
  }

  const finish = () => {
    markOnboardingComplete()
    onComplete({ useCase: useCase ?? 'other', displayName: displayName.trim() || userName })
  }

  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center bg-[#070b12]/95 backdrop-blur-md'>
      <div className='w-full max-w-lg mx-4'>
        {/* ── step 0: welcome + use case ── */}
        {step === 0 && (
          <div className='animate-in fade-in slide-in-from-bottom-2 duration-300'>
            <div className='text-center mb-8'>
              <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10'>
                <img src='/aegis-owl-logo.svg' alt='Aegis' className='h-10 w-10' />
              </div>
              <h1 className='text-2xl font-bold text-white'>Welcome to Aegis{displayName ? `, ${displayName.split(' ')[0]}` : ''}!</h1>
              <p className='mt-2 text-sm text-zinc-400'>Let's set things up so your first session goes smoothly.</p>
            </div>

            <p className='mb-3 text-xs font-medium uppercase tracking-widest text-zinc-500'>What will you use Aegis for?</p>
            <div className='grid grid-cols-2 gap-2'>
              {USE_CASES.map((uc) => (
                <button
                  key={uc.id}
                  type='button'
                  onClick={() => setUseCase(uc.id)}
                  className={`rounded-xl border p-3 text-left transition ${
                    useCase === uc.id
                      ? 'border-cyan-400/40 bg-cyan-400/10'
                      : 'border-white/8 bg-white/3 hover:border-white/15 hover:bg-white/5'
                  }`}
                >
                  <span className='text-lg'>{uc.icon}</span>
                  <p className='mt-1 text-sm font-medium text-white'>{uc.label}</p>
                  <p className='text-xs text-zinc-500'>{uc.desc}</p>
                </button>
              ))}
            </div>

            <div className='mt-6 flex justify-between items-center'>
              <StepIndicator current={0} total={TOTAL_STEPS} />
              <button
                type='button'
                onClick={next}
                disabled={!useCase}
                className='rounded-xl bg-cyan-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-40'
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* ── step 1: profile ── */}
        {step === 1 && (
          <div className='animate-in fade-in slide-in-from-bottom-2 duration-300'>
            <div className='text-center mb-8'>
              <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10'>
                {Icons.user({ className: 'h-8 w-8 text-cyan-400' })}
              </div>
              <h2 className='text-xl font-bold text-white'>Your profile</h2>
              <p className='mt-2 text-sm text-zinc-400'>How should Aegis address you?</p>
            </div>

            <div className='space-y-4'>
              <div>
                <label className='mb-1.5 block text-xs font-medium uppercase tracking-widest text-zinc-500'>Display name</label>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder='Your name'
                  className='w-full rounded-xl border border-white/8 bg-[#0c1018] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
                />
              </div>
              <div>
                <label className='mb-1.5 block text-xs font-medium uppercase tracking-widest text-zinc-500'>Email</label>
                <div className='w-full rounded-xl border border-white/6 bg-white/3 px-4 py-3 text-sm text-zinc-500'>{userEmail}</div>
              </div>
            </div>

            <div className='mt-6 flex justify-between items-center'>
              <StepIndicator current={1} total={TOTAL_STEPS} />
              <div className='flex gap-2'>
                <button type='button' onClick={back} className='rounded-xl border border-white/10 px-4 py-2.5 text-sm text-zinc-300 transition hover:bg-white/5'>
                  Back
                </button>
                <button
                  type='button'
                  onClick={next}
                  disabled={!displayName.trim()}
                  className='rounded-xl bg-cyan-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-40'
                >
                  Continue
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── step 2: API key (skippable) ── */}
        {step === 2 && (
          <div className='animate-in fade-in slide-in-from-bottom-2 duration-300'>
            <div className='text-center mb-6'>
              <div className='mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10'>
                {Icons.lock({ className: 'h-7 w-7 text-cyan-400' })}
              </div>
              <h2 className='text-xl font-bold text-white'>Connect your AI model</h2>
              <p className='mt-2 text-sm text-zinc-400'>
                Aegis uses your own API key to power sessions. This keeps you in control of costs and model choice.
              </p>
            </div>

            {/* recommended badge */}
            <div className='mb-4 flex items-center gap-2 rounded-xl border border-cyan-400/15 bg-cyan-400/5 px-3 py-2'>
              <svg viewBox='0 0 16 16' className='h-4 w-4 shrink-0 text-cyan-400' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round'>
                <circle cx='8' cy='8' r='6' />
                <path d='M8 5v3M8 10.5h.01' />
              </svg>
              <p className='text-xs text-cyan-200'>
                <span className='font-semibold'>Recommended.</span> Connecting a key now means you can start a live session right away.
                You can always add or change keys later in Settings.
              </p>
            </div>

            {!keySaved ? (
              <div className='space-y-3'>
                <div>
                  <label className='mb-1.5 block text-xs font-medium uppercase tracking-widest text-zinc-500'>Provider</label>
                  <div className='grid grid-cols-3 gap-1.5 sm:grid-cols-5'>
                    {PROVIDERS.map((p) => (
                      <button
                        key={p.id}
                        type='button'
                        onClick={() => { setSelectedProvider(p.id); setApiKey('') }}
                        className={`flex flex-col items-center gap-1 rounded-lg border p-2 text-xs transition ${
                          selectedProvider === p.id
                            ? 'border-cyan-400/40 bg-cyan-400/10'
                            : 'border-white/8 bg-white/3 hover:border-white/15'
                        }`}
                      >
                        {renderProviderIcon(p, 'h-5 w-5 rounded-sm')}
                        <span className='text-zinc-300'>{p.id === 'google' ? 'Google' : p.id === 'openai' ? 'OpenAI' : p.id === 'anthropic' ? 'Anthropic' : p.id === 'xai' ? 'xAI' : p.id === 'openrouter' ? 'OpenRouter' : p.displayName}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className='mb-1.5 block text-xs font-medium uppercase tracking-widest text-zinc-500'>API Key</label>
                  <input
                    type='password'
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={`Paste your ${selectedProvider} API key`}
                    className='w-full rounded-xl border border-white/8 bg-[#0c1018] px-4 py-3 text-sm text-zinc-100 outline-none transition focus:border-cyan-400/30'
                  />
                </div>

                <button
                  type='button'
                  onClick={saveApiKey}
                  disabled={!apiKey.trim() || saving}
                  className='w-full rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-40'
                >
                  {saving ? 'Saving…' : 'Connect key'}
                </button>
              </div>
            ) : (
              <div className='flex items-center gap-3 rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3'>
                <svg viewBox='0 0 16 16' className='h-5 w-5 shrink-0 text-emerald-400' fill='none' stroke='currentColor' strokeWidth='2.5' strokeLinecap='round' strokeLinejoin='round'>
                  <path d='m3 8 3.5 3.5L13 5' />
                </svg>
                <div>
                  <p className='text-sm font-medium text-emerald-200'>API key connected</p>
                  <p className='text-xs text-emerald-300/70'>You're ready to run live sessions with {selectedProvider}.</p>
                </div>
              </div>
            )}

            <div className='mt-6 flex justify-between items-center'>
              <StepIndicator current={2} total={TOTAL_STEPS} />
              <div className='flex gap-2'>
                <button type='button' onClick={back} className='rounded-xl border border-white/10 px-4 py-2.5 text-sm text-zinc-300 transition hover:bg-white/5'>
                  Back
                </button>
                <button type='button' onClick={next} className='rounded-xl bg-cyan-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'>
                  {keySaved ? 'Continue' : 'Skip for now'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── step 3: all set ── */}
        {step === 3 && (
          <div className='animate-in fade-in slide-in-from-bottom-2 duration-300 text-center'>
            <div className='mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full border border-emerald-400/20 bg-emerald-400/10'>
              <svg viewBox='0 0 24 24' className='h-10 w-10 text-emerald-400' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
                <path d='m5 12 4 4 10-10' />
              </svg>
            </div>
            <h2 className='text-2xl font-bold text-white'>You're all set!</h2>
            <p className='mt-2 text-sm text-zinc-400'>
              We'll give you a quick tour of the interface, then you're ready to run your first task.
            </p>

            <div className='mt-6 grid gap-2 text-left rounded-xl border border-white/8 bg-white/3 p-4'>
              <div className='flex items-center gap-3'>
                <span className='flex h-6 w-6 items-center justify-center rounded-full bg-cyan-400/20 text-xs font-bold text-cyan-400'>✓</span>
                <span className='text-sm text-zinc-300'>Use case: <span className='text-white font-medium'>{USE_CASES.find((u) => u.id === useCase)?.label ?? useCase}</span></span>
              </div>
              <div className='flex items-center gap-3'>
                <span className='flex h-6 w-6 items-center justify-center rounded-full bg-cyan-400/20 text-xs font-bold text-cyan-400'>✓</span>
                <span className='text-sm text-zinc-300'>Name: <span className='text-white font-medium'>{displayName || userName}</span></span>
              </div>
              <div className='flex items-center gap-3'>
                <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${keySaved ? 'bg-emerald-400/20 text-emerald-400' : 'bg-zinc-700/50 text-zinc-500'}`}>
                  {keySaved ? '✓' : '–'}
                </span>
                <span className='text-sm text-zinc-300'>API key: <span className={keySaved ? 'text-white font-medium' : 'text-zinc-500'}>{keySaved ? `${selectedProvider} connected` : 'Skipped (add later in Settings)'}</span></span>
              </div>
            </div>

            <div className='mt-8 flex justify-between items-center'>
              <StepIndicator current={3} total={TOTAL_STEPS} />
              <div className='flex gap-2'>
                <button type='button' onClick={back} className='rounded-xl border border-white/10 px-4 py-2.5 text-sm text-zinc-300 transition hover:bg-white/5'>
                  Back
                </button>
                <button type='button' onClick={finish} className='rounded-xl bg-cyan-500 px-8 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400'>
                  Launch Aegis 🚀
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
