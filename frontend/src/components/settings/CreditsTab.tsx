import { useCallback, useEffect, useState } from 'react'
import { LuCreditCard, LuZap, LuLoader, LuCalendar, LuChartBar } from 'react-icons/lu'
import { apiUrl } from '../../lib/api'

// ── Types ────────────────────────────────────────────────────────────────

type CreditBlock = {
  id: string
  amount_credits: number
  amount_usd: number
  effective_date: string
  expiry_date: string | null
  original_balance: number
  current_balance: number
  source: string
}

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

// ── Credit packages ──────────────────────────────────────────────────────

const CREDIT_PACKAGES = [
  { credits: 10_000, usd: 10, bonus: 3_000, label: 'Buy $10, get $13' },
  { credits: 20_000, usd: 20, bonus: 8_000, label: 'Buy $20, get $28' },
  { credits: 100_000, usd: 100, bonus: 20_000, label: 'Buy $100, get $120' },
] as const

// ── Helper icons ─────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return <LuLoader className={`animate-spin ${className ?? 'h-4 w-4'}`} />
}

// ── Main component ───────────────────────────────────────────────────────

interface CreditsTabProps {
  /** If set (e.g. from landing page redirect), pre-open checkout for a specific package */
  initialCredits?: number
}

export function CreditsTab({ initialCredits }: CreditsTabProps) {
  const [balance, setBalance] = useState<BalanceSummary | null>(null)
  const [creditBlocks, setCreditBlocks] = useState<CreditBlock[]>([])
  const [paymentsConfig, setPaymentsConfig] = useState<PaymentsConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedPackage, setSelectedPackage] = useState<(typeof CREDIT_PACKAGES)[number] | null>(
    () => CREDIT_PACKAGES.find((p) => p.usd === initialCredits) ?? null,
  )
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
      if (balanceRes.ok) {
        const data = (await balanceRes.json()) as BalanceSummary
        setBalance(data)
      }
      if (configRes.ok) {
        const data = (await configRes.json()) as PaymentsConfig
        setPaymentsConfig(data)
        if (data.active_methods[0]) {
          setSelectedMethod(data.active_methods[0] as 'stripe' | 'coinbase')
        }
      }
      // Try to load credit blocks history
      const histRes = await fetch(apiUrl('/api/payments/credit-blocks'), { credentials: 'include' })
      if (histRes.ok) {
        const data = (await histRes.json()) as { blocks: CreditBlock[] }
        setCreditBlocks(data.blocks ?? [])
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleProceed = async () => {
    if (!selectedPackage || !selectedMethod) return
    setCheckoutLoading(true)
    setError(null)
    try {
      if (selectedMethod === 'stripe') {
        const origin = window.location.origin
        const res = await fetch(apiUrl('/api/payments/stripe/create-credits-checkout'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            credits: selectedPackage.credits + selectedPackage.bonus,
            amount_usd: selectedPackage.usd,
            success_url: `${origin}/?credits_success=1`,
            cancel_url: `${origin}/?credits_cancelled=1`,
          }),
        })
        if (!res.ok) throw new Error('Failed to create checkout session')
        const data = (await res.json()) as { checkout_url: string }
        window.location.href = data.checkout_url
      } else {
        const res = await fetch(apiUrl('/api/payments/coinbase/create-credits-charge'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            credits: selectedPackage.credits + selectedPackage.bonus,
            amount_usd: selectedPackage.usd,
          }),
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

  const creditBalance = balance
    ? ((balance.allowance - balance.used) + (balance.remaining ?? 0))
    : 0
  const balanceUsd = (creditBalance / 1000).toFixed(6)

  return (
    <div className='space-y-6'>

      {/* Header */}
      <div>
        <h2 className='text-base font-semibold text-white'>Credits</h2>
        <p className='mt-0.5 text-xs text-zinc-500'>Buy credits to use Aegis with platform-managed AI keys.</p>
      </div>

      {/* Balance card */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-2'>
            <LuZap className='h-4 w-4 text-cyan-400' />
            <span className='text-sm font-medium text-zinc-300'>Credit balance</span>
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
            <SpinnerIcon /> <span className='text-sm'>Loading balance…</span>
          </div>
        ) : (
          <>
            <p className='mt-3 text-3xl font-semibold text-white'>${balanceUsd}</p>
            {balance && (
              <div className='mt-3 grid grid-cols-2 gap-3'>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Effective date</p>
                  <p className='mt-1 text-xs text-zinc-300'>—</p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Expiry date</p>
                  <p className='mt-1 text-xs text-zinc-300'>
                    {balance.cycle_end ? new Date(balance.cycle_end).toLocaleDateString() : '—'}
                  </p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Current balance</p>
                  <p className='mt-1 text-xs text-zinc-300'>${balanceUsd}</p>
                </div>
                <div className='rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] p-3'>
                  <p className='text-[10px] uppercase tracking-wider text-zinc-500'>Original balance</p>
                  <p className='mt-1 text-xs text-zinc-300'>${(balance.allowance / 1000).toFixed(6)}</p>
                </div>
              </div>
            )}
            {creditBlocks.length === 0 && (
              <p className='mt-3 text-center text-xs text-zinc-500'>No credit blocks found</p>
            )}
          </>
        )}
      </div>

      {/* Buy Credits */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center gap-2 mb-4'>
          <LuCreditCard className='h-4 w-4 text-cyan-400' />
          <h3 className='text-sm font-semibold text-white'>Buy Credits</h3>
        </div>

        {/* First-time bonus banner */}
        <div className='mb-4 rounded-lg border border-purple-500/30 bg-purple-500/10 px-4 py-3'>
          <p className='text-xs font-semibold text-purple-300'>🎉 Get $20 Extra on Your First Top-Up</p>
          <p className='mt-0.5 text-[11px] text-purple-400'>
            Top up any amount of credits and we'll add $20 on top of it, instantly.
          </p>
          <p className='mt-0.5 text-[10px] text-purple-500'>Free promotional credits expire in 60 days.</p>
        </div>

        {/* Package selector */}
        <div className='flex flex-wrap gap-2 mb-5'>
          {CREDIT_PACKAGES.map((pkg) => (
            <button
              key={pkg.usd}
              type='button'
              onClick={() => setSelectedPackage(pkg)}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                selectedPackage?.usd === pkg.usd
                  ? 'border-cyan-500/60 bg-cyan-500/10 text-cyan-300'
                  : 'border-[#2a2a2a] text-zinc-300 hover:border-zinc-500'
              }`}
            >
              {pkg.label}
            </button>
          ))}
          <button
            type='button'
            onClick={() => setSelectedPackage(null)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
              selectedPackage === null
                ? 'border-cyan-500/60 bg-cyan-500/10 text-cyan-300'
                : 'border-[#2a2a2a] text-zinc-300 hover:border-zinc-500'
            }`}
          >
            Custom
          </button>
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
          disabled={!selectedPackage || !selectedMethod || checkoutLoading}
          className='flex w-full items-center justify-center gap-2 rounded-full bg-cyan-500 py-3 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50'
        >
          {checkoutLoading ? (
            <>
              <SpinnerIcon className='h-4 w-4' />
              Redirecting…
            </>
          ) : selectedPackage ? (
            <>Continue to {selectedMethod === 'stripe' ? 'Stripe' : 'Coinbase'} — ${selectedPackage.usd}</>
          ) : (
            'Select a package'
          )}
        </button>

        <p className='mt-3 text-center text-[11px] text-zinc-600'>
          Payments processed securely. 1 credit = $0.001.
        </p>
      </div>

      {/* Auto Top-Up */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-2'>
            <LuChartBar className='h-4 w-4 text-zinc-400' />
            <div>
              <p className='text-sm font-medium text-zinc-300'>Automatic Top Up</p>
              <p className='text-[11px] text-zinc-500'>Automatically top up your balance when it drops below $5.</p>
            </div>
          </div>
          <button
            type='button'
            onClick={() => setAutoTopUp((prev) => !prev)}
            className={`relative h-5 w-9 rounded-full transition-colors ${autoTopUp ? 'bg-cyan-600' : 'bg-zinc-700'}`}
          >
            <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${autoTopUp ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </button>
        </div>
        {autoTopUp && (
          <p className='mt-3 text-xs text-zinc-500'>
            When your balance drops below $5, we'll automatically charge your saved payment method for $10.
          </p>
        )}
      </div>

      {/* Credit history */}
      {creditBlocks.length > 0 && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5'>
          <div className='flex items-center gap-2 mb-4'>
            <LuCalendar className='h-4 w-4 text-zinc-400' />
            <h3 className='text-sm font-semibold text-white'>Credit History</h3>
          </div>
          <table className='w-full text-xs'>
            <thead>
              <tr className='text-left text-[10px] uppercase tracking-wider text-zinc-500'>
                <th className='pb-2'>Date</th>
                <th className='pb-2'>Credits</th>
                <th className='pb-2'>Source</th>
                <th className='pb-2 text-right'>Balance</th>
              </tr>
            </thead>
            <tbody className='divide-y divide-[#1a1a1a]'>
              {creditBlocks.map((block) => (
                <tr key={block.id} className='text-zinc-300'>
                  <td className='py-2'>{new Date(block.effective_date).toLocaleDateString()}</td>
                  <td className='py-2 text-emerald-400'>+{block.amount_credits.toLocaleString()}</td>
                  <td className='py-2 capitalize text-zinc-500'>{block.source}</td>
                  <td className='py-2 text-right'>{block.current_balance.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
