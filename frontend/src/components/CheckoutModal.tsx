import { useEffect, useState } from 'react'
import { Icons } from './icons'
import { apiUrl } from '../lib/api'

type Plan = 'pro' | 'team' | 'enterprise'

type PaymentsConfig = {
  stripe_publishable_key: string
  active_methods: string[]
}

interface CheckoutModalProps {
  plan: Plan
  onClose: () => void
}

const PLAN_LABELS: Record<Plan, string> = {
  pro: 'Pro',
  team: 'Team',
  enterprise: 'Enterprise',
}

const PLAN_PRICES: Record<Plan, string> = {
  pro: '$29/month',
  team: '$79/seat/month',
  enterprise: '$299/month',
}

function CreditCardIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className={className ?? 'h-6 w-6'} aria-hidden='true'>
      <rect x='2' y='5' width='20' height='14' rx='2' />
      <path d='M2 10h20' />
      <path d='M6 15h4' />
    </svg>
  )
}

function BitcoinIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className={className ?? 'h-6 w-6'} aria-hidden='true'>
      <path d='M9.5 2H14a3.5 3.5 0 0 1 0 7H9.5V2Z' />
      <path d='M9.5 9H15a3.5 3.5 0 0 1 0 7H9.5V9Z' />
      <path d='M8 2v18M12 2v2M12 18v2' />
    </svg>
  )
}

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' className={`animate-spin ${className ?? 'h-5 w-5'}`} fill='none' aria-hidden='true'>
      <circle cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='3' strokeDasharray='40' strokeDashoffset='10' />
    </svg>
  )
}

export function CheckoutModal({ plan, onClose }: CheckoutModalProps) {
  const [config, setConfig] = useState<PaymentsConfig | null>(null)
  const [loadingConfig, setLoadingConfig] = useState(true)
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(apiUrl('/api/payments/config'))
        if (!res.ok) throw new Error('Failed to load payment config')
        const data = (await res.json()) as PaymentsConfig
        setConfig(data)
        if (data.active_methods.length > 0) {
          setSelectedMethod(data.active_methods[0])
        }
      } catch {
        setError('Could not load payment options.')
      } finally {
        setLoadingConfig(false)
      }
    })()
  }, [])

  const handleProceed = async () => {
    if (!selectedMethod || !config) return
    setLoading(true)
    setError(null)

    try {
      const origin = window.location.origin
      const successUrl = `${origin}/?payment=success&plan=${plan}`
      const cancelUrl = `${origin}/?payment=cancelled`

      if (selectedMethod === 'stripe') {
        const res = await fetch(apiUrl('/api/payments/stripe/create-checkout'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ plan, success_url: successUrl, cancel_url: cancelUrl }),
        })
        if (!res.ok) {
          const err = (await res.json()) as { detail?: string }
          throw new Error(err.detail ?? 'Failed to create checkout session')
        }
        const data = (await res.json()) as { checkout_url: string }
        window.location.href = data.checkout_url
      } else if (selectedMethod === 'coinbase') {
        const res = await fetch(apiUrl('/api/payments/coinbase/create-charge'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ plan }),
        })
        if (!res.ok) {
          const err = (await res.json()) as { detail?: string }
          throw new Error(err.detail ?? 'Failed to create crypto charge')
        }
        const data = (await res.json()) as { hosted_url: string }
        window.location.href = data.hosted_url
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
      setLoading(false)
    }
  }

  const noMethods = !loadingConfig && config && config.active_methods.length === 0

  return (
    <div
      className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm'
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className='relative w-full max-w-md rounded-2xl border border-white/10 bg-[#0c1018] shadow-2xl'>
        {/* Header */}
        <div className='flex items-start justify-between border-b border-white/8 p-6'>
          <div>
            <p className='text-[11px] uppercase tracking-[0.22em] text-cyan-300'>Upgrade to</p>
            <h2 className='mt-1 text-xl font-semibold text-white'>{PLAN_LABELS[plan]}</h2>
            <p className='mt-1 text-sm text-zinc-400'>{PLAN_PRICES[plan]}</p>
          </div>
          <button
            type='button'
            onClick={onClose}
            className='flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition hover:bg-white/8 hover:text-white'
          >
            {Icons.back({ className: 'h-4 w-4 rotate-180' })}
            <span className='sr-only'>Close</span>
          </button>
        </div>

        {/* Body */}
        <div className='p-6'>
          {loadingConfig ? (
            <div className='flex items-center justify-center py-8 text-zinc-500'>
              <SpinnerIcon className='h-5 w-5' />
              <span className='ml-2 text-sm'>Loading payment options…</span>
            </div>
          ) : noMethods ? (
            <p className='py-6 text-center text-sm text-zinc-400'>
              No payment methods are currently available. Please contact support.
            </p>
          ) : (
            <>
              <p className='mb-4 text-sm font-medium text-zinc-300'>Select payment method</p>
              <div className='space-y-3'>
                {config?.active_methods.includes('stripe') && (
                  <button
                    type='button'
                    onClick={() => setSelectedMethod('stripe')}
                    className={`flex w-full items-center gap-4 rounded-xl border px-4 py-4 text-left transition ${
                      selectedMethod === 'stripe'
                        ? 'border-cyan-500/50 bg-cyan-500/8 text-white'
                        : 'border-white/8 text-zinc-300 hover:border-white/16 hover:bg-white/4'
                    }`}
                  >
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                      selectedMethod === 'stripe' ? 'bg-cyan-500/20 text-cyan-300' : 'bg-white/6 text-zinc-400'
                    }`}>
                      <CreditCardIcon className='h-5 w-5' />
                    </div>
                    <div>
                      <p className='text-sm font-medium'>Pay with Card</p>
                      <p className='text-[12px] text-zinc-500'>Credit or debit via Stripe</p>
                    </div>
                    {selectedMethod === 'stripe' && (
                      <div className='ml-auto'>
                        {Icons.check({ className: 'h-4 w-4 text-cyan-400' })}
                      </div>
                    )}
                  </button>
                )}

                {config?.active_methods.includes('coinbase') && (
                  <button
                    type='button'
                    onClick={() => setSelectedMethod('coinbase')}
                    className={`flex w-full items-center gap-4 rounded-xl border px-4 py-4 text-left transition ${
                      selectedMethod === 'coinbase'
                        ? 'border-orange-500/50 bg-orange-500/8 text-white'
                        : 'border-white/8 text-zinc-300 hover:border-white/16 hover:bg-white/4'
                    }`}
                  >
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                      selectedMethod === 'coinbase' ? 'bg-orange-500/20 text-orange-300' : 'bg-white/6 text-zinc-400'
                    }`}>
                      <BitcoinIcon className='h-5 w-5' />
                    </div>
                    <div>
                      <p className='text-sm font-medium'>Pay with Crypto</p>
                      <p className='text-[12px] text-zinc-500'>Bitcoin, ETH & more via Coinbase</p>
                    </div>
                    {selectedMethod === 'coinbase' && (
                      <div className='ml-auto'>
                        {Icons.check({ className: 'h-4 w-4 text-orange-400' })}
                      </div>
                    )}
                  </button>
                )}
              </div>

              {error && (
                <p className='mt-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400'>
                  {error}
                </p>
              )}

              <button
                type='button'
                onClick={() => void handleProceed()}
                disabled={!selectedMethod || loading}
                className='mt-6 flex w-full items-center justify-center gap-2 rounded-full bg-cyan-500 py-3 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50'
              >
                {loading ? (
                  <>
                    <SpinnerIcon className='h-4 w-4' />
                    Redirecting…
                  </>
                ) : (
                  <>Continue to {selectedMethod === 'stripe' ? 'Stripe' : selectedMethod === 'coinbase' ? 'Coinbase' : 'Checkout'}</>
                )}
              </button>

              <p className='mt-4 text-center text-[11px] text-zinc-600'>
                Payments are processed securely by {selectedMethod === 'stripe' ? 'Stripe' : 'Coinbase Commerce'}. You can cancel anytime.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
