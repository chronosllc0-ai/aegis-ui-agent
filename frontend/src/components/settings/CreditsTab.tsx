import { useCallback, useEffect, useState } from 'react'
import { LuCreditCard, LuZap, LuLoader, LuCalendar, LuChartBar } from 'react-icons/lu'
import { apiUrl } from '../../lib/api'

// ── Types ────────────────────────────────────────────────────────────────

type BalanceSummary = {
  plan: string
  used: number
  allowance: number
  percent: number
  overage?: number
  remaining?: number
  spending_cap?: number | null
  cycle_end?: string | null
}

type PaymentsConfig = {
  stripe_publishable_key: string
  active_methods: string[]
}

// ── Plans — mirrors PRICING in LandingPage.tsx ───────────────────────────

const PLANS = [
  {
    key: 'pro' as const,
    name: 'Pro',
    price: 29,
    period: '/month',
    credits: 50_000,
    description: 'Serious throughput, saved workflows, and priority support.',
    highlight: true,
  },
  {
    key: 'team' as const,
    name: 'Team',
    price: 79,
    period: '/seat/month',
    credits: 200_000,
    description: 'Shared credit pools, SSO, team workflows, and admin dashboard.',
    highlight: false,
  },
  {
    key: 'enterprise' as const,
    name: 'Enterprise',
    price: 299,
    period: '/month',
    credits: 1_000_000,
    description: 'Dedicated support, custom limits, and advanced security.',
    highlight: false,
  },
] as const

type PlanKey = (typeof PLANS)[number]['key']

// ── Helper ───────────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return <LuLoader className={`animate-spin ${className ?? 'h-4 w-4'}`} />
}

// ── Main component ───────────────────────────────────────────────────────

interface CreditsTabProps {
  /** If set (from landing page redirect), pre-select matching plan */
  initialPlan?: PlanKey
}

export function CreditsTab({ initialPlan }: CreditsTabProps) {
  const [balance, setBalance] = useState<BalanceSummary | null>(null)
  const [paymentsConfig, setPaymentsConfig] = useState<PaymentsConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedPlan, setSelectedPlan] = useState<PlanKey | null>(initialPlan ?? null)
  const [selectedMethod, setSelectedMethod] = useState<'stripe' | 'coinbase' | null>(null)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoTopUp, setAutoTopUp] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [balanceRes, configRes] = await Promise.all([
        fetch(apiUrl('/api/usage/balance'), { credentials: 'include' }),
        fetch(apiUrl('/api/payments/config'), { credentials: 'include' }),
      ])
      if (balanceRes.ok) setBalance((await balanceRes.json()) as BalanceSummary)
      if (configRes.ok) {
        const data = (await configRes.json()) as PaymentsConfig
        setPaymentsConfig(data)
        if (!selectedMethod && data.active_methods[0]) {
          setSelectedMethod(data.active_methods[0] as 'stripe' | 'coinbase')
        }
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleProceed = async () => {
    if (!selectedPlan || !selectedMethod) return
    setCheckoutLoading(true)
    setError(null)
    const plan = PLANS.find((p) => p.key === selectedPlan)!
    try {
      if (selectedMethod === 'stripe') {
        const origin = window.location.origin
        const res = await fetch(apiUrl('/api/payments/stripe/create-checkout'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            plan: plan.key,
            success_url: `${origin}/?plan_success=1`,
            cancel_url: `${origin}/?plan_cancelled=1`,
          }),
        })
        if (!res.ok) throw new Error('Failed to create checkout session')
        const data = (await res.json()) as { checkout_url: string }
        window.location.href = data.checkout_url
      } else {
        const res = await fetch(apiUrl('/api/payments/coinbase/create-charge'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ plan: plan.key }),
        })
        if (!res.ok) throw new Error('Failed to create crypto charge')
        const data = (await res.json()) as { hosted_url: string }
        window.location.href = data.hosted_url
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Payment failed. Please try again.')
    } finally {
      setCheckoutLoading(false)
    }
  }

  const creditBalance = balance ? balance.allowance - balance.used + (balance.remaining ?? 0) : 0
  const balanceUsd = (creditBalance / 1000).toFixed(2)
  const currentPlanName = balance?.plan
    ? balance.plan.charAt(0).toUpperCase() + balance.plan.slice(1)
    : 'Free'

  return (
    <div className='space-y-6'>

      {/* Header */}
      <div>
        <h2 className='text-base font-semibold text-white'>Credits & Plan</h2>
        <p className='mt-0.5 text-xs text-zinc-500'>Manage your Aegis subscription and credit balance.</p>
      </div>

      {/* Balance card */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-2'>
            <LuZap className='h-4 w-4 text-cyan-400' />
            <span className='text-sm font-medium text-zinc-300'>Current balance</span>
          </div>
          <button
            type='button'
            onClick={() => void loadData()}
            className='rounded p-1 text-zinc-500 hover:text-zinc-300'
            title='Refresh'
          >
            <LuLoader className='h-3.5 w-3.5' />
          </button>
        </div>

        {loading ? (
          <div className='mt-4 flex items-center gap-2 text-zinc-500'>
            <SpinnerIcon /> <span className='text-sm'>Loading…</span>
          </div>
        ) : (
          <>
            <p className='mt-3 text-3xl font-semibold text-white'>${balanceUsd}</p>
            {balance && (
              <div className='mt-3 grid grid-cols-2 gap-3'>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Current plan</p>
                  <p className='mt-1 text-xs font-medium text-cyan-300'>{currentPlanName}</p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Cycle renews</p>
                  <p className='mt-1 text-xs text-zinc-300'>
                    {balance.cycle_end ? new Date(balance.cycle_end).toLocaleDateString() : '—'}
                  </p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Credits used</p>
                  <p className='mt-1 text-xs text-zinc-300'>{balance.used.toLocaleString()}</p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Monthly allowance</p>
                  <p className='mt-1 text-xs text-zinc-300'>{balance.allowance.toLocaleString()}</p>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Upgrade / Subscribe */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center gap-2 mb-4'>
          <LuCreditCard className='h-4 w-4 text-cyan-400' />
          <h3 className='text-sm font-semibold text-white'>Upgrade Plan</h3>
        </div>

        {/* Plan cards */}
        <div className='space-y-3 mb-5'>
          {PLANS.map((plan) => {
            const isSelected = selectedPlan === plan.key
            const isCurrent = balance?.plan === plan.key
            return (
              <button
                key={plan.key}
                type='button'
                onClick={() => setSelectedPlan(plan.key)}
                disabled={isCurrent}
                className={`w-full rounded-xl border px-4 py-3.5 text-left transition ${
                  isCurrent
                    ? 'cursor-default border-zinc-700/50 bg-zinc-800/30 opacity-60'
                    : isSelected
                    ? plan.highlight
                      ? 'border-cyan-500/60 bg-cyan-500/8'
                      : 'border-zinc-500/60 bg-zinc-700/10'
                    : 'border-[#2a2a2a] hover:border-zinc-600'
                }`}
              >
                <div className='flex items-center justify-between'>
                  <div className='flex items-center gap-2'>
                    <span className='text-sm font-semibold text-white'>
                      {plan.name}
                      {plan.highlight && (
                        <span className='ml-2 rounded-full bg-cyan-500/20 px-2 py-0.5 text-[10px] font-medium text-cyan-300'>
                          Popular
                        </span>
                      )}
                    </span>
                    {isCurrent && (
                      <span className='rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400'>
                        Current
                      </span>
                    )}
                  </div>
                  <div className='text-right'>
                    <span className='text-lg font-bold text-white'>${plan.price}</span>
                    <span className='text-[11px] text-zinc-500'>{plan.period}</span>
                  </div>
                </div>
                <p className='mt-1 text-[11px] text-zinc-500'>{plan.description}</p>
                <p className='mt-1 text-[11px] text-cyan-400/70'>
                  {plan.credits.toLocaleString()} credits/month
                </p>
              </button>
            )
          })}
        </div>

        {/* Payment method */}
        {paymentsConfig && paymentsConfig.active_methods.length > 0 && (
          <div className='space-y-2 mb-5'>
            {paymentsConfig.active_methods.includes('stripe') && (
              <button
                type='button'
                onClick={() => setSelectedMethod('stripe')}
                className={`flex w-full items-center gap-4 rounded-xl border px-4 py-3 text-left transition ${
                  selectedMethod === 'stripe'
                    ? 'border-cyan-500/50 bg-cyan-500/8 text-white'
                    : 'border-[#2a2a2a] text-zinc-300 hover:border-zinc-600'
                }`}
              >
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                  selectedMethod === 'stripe' ? 'bg-cyan-500/20 text-cyan-300' : 'bg-[#1a1a1a] text-zinc-400'
                }`}>
                  <LuCreditCard className='h-4 w-4' />
                </div>
                <div className='flex-1'>
                  <p className='text-sm font-medium'>Pay with Card</p>
                  <p className='text-[11px] text-zinc-500'>Credit or debit via Stripe</p>
                </div>
                {selectedMethod === 'stripe' && <LuZap className='h-4 w-4 text-cyan-400' />}
              </button>
            )}

            {paymentsConfig.active_methods.includes('coinbase') && (
              <button
                type='button'
                onClick={() => setSelectedMethod('coinbase')}
                className={`flex w-full items-center gap-4 rounded-xl border px-4 py-3 text-left transition ${
                  selectedMethod === 'coinbase'
                    ? 'border-orange-500/50 bg-orange-500/8 text-white'
                    : 'border-[#2a2a2a] text-zinc-300 hover:border-zinc-600'
                }`}
              >
                <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                  selectedMethod === 'coinbase' ? 'bg-orange-500/20 text-orange-300' : 'bg-[#1a1a1a] text-zinc-400'
                }`}>
                  <LuCreditCard className='h-4 w-4' />
                </div>
                <div className='flex-1'>
                  <p className='text-sm font-medium'>Pay with Crypto</p>
                  <p className='text-[11px] text-zinc-500'>Bitcoin, ETH & more via Coinbase</p>
                </div>
                {selectedMethod === 'coinbase' && <LuZap className='h-4 w-4 text-orange-400' />}
              </button>
            )}
          </div>
        )}

        {error && (
          <div className='mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400'>
            {error}
          </div>
        )}

        <button
          type='button'
          onClick={() => void handleProceed()}
          disabled={!selectedPlan || !selectedMethod || checkoutLoading}
          className='flex w-full items-center justify-center gap-2 rounded-full bg-cyan-500 py-3 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50'
        >
          {checkoutLoading ? (
            <>
              <SpinnerIcon className='h-4 w-4' />
              Redirecting…
            </>
          ) : selectedPlan ? (
            <>
              Subscribe to {PLANS.find((p) => p.key === selectedPlan)?.name} —{' '}
              ${PLANS.find((p) => p.key === selectedPlan)?.price}
              {PLANS.find((p) => p.key === selectedPlan)?.period}
            </>
          ) : (
            'Select a plan'
          )}
        </button>

        <p className='mt-3 text-center text-[11px] text-zinc-600'>
          Recurring monthly subscription. Cancel any time.
        </p>
      </div>

      {/* Auto Top-Up */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-2'>
            <LuChartBar className='h-4 w-4 text-zinc-400' />
            <div>
              <p className='text-sm font-medium text-zinc-300'>Automatic Top Up</p>
              <p className='text-[11px] text-zinc-500'>
                Automatically purchase more credits when your balance runs out.
              </p>
            </div>
          </div>
          <button
            type='button'
            onClick={() => setAutoTopUp((prev) => !prev)}
            className={`relative h-5 w-9 rounded-full transition-colors ${autoTopUp ? 'bg-cyan-600' : 'bg-zinc-700'}`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                autoTopUp ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Credit history (plan-level activity) */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center gap-2 mb-4'>
          <LuCalendar className='h-4 w-4 text-zinc-400' />
          <h3 className='text-sm font-semibold text-white'>Billing History</h3>
          <span className='ml-auto text-[11px] text-zinc-600'>See Invoice tab for full records</span>
        </div>
        {balance ? (
          <div className='text-xs text-zinc-400 space-y-2'>
            <div className='flex justify-between py-2 border-b border-[#1e1e1e]'>
              <span>
                {currentPlanName} plan — current cycle
              </span>
              <span className='text-zinc-300'>
                {balance.used.toLocaleString()} / {balance.allowance.toLocaleString()} credits
              </span>
            </div>
            {balance.cycle_end && (
              <div className='flex justify-between py-1'>
                <span className='text-zinc-500'>Next renewal</span>
                <span className='text-zinc-400'>{new Date(balance.cycle_end).toLocaleDateString()}</span>
              </div>
            )}
          </div>
        ) : (
          <p className='text-xs text-zinc-600'>No billing data available.</p>
        )}
      </div>
    </div>
  )
}
