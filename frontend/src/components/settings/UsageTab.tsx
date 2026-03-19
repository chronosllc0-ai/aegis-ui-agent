import { useCallback, useEffect, useRef, useState } from 'react'
import {
  LuActivity,
  LuChartBar,
  LuCalendar,
  LuCreditCard,
  LuDownload,
  LuFilter,
  LuLoader,
  LuChartPie,
  LuShield,
  LuZap,
} from 'react-icons/lu'
import { apiUrl } from '../../lib/api'

type BalanceSummary = {
  plan: string
  used: number
  allowance: number
  overage: number
  percent: number
  cycle_start: string | null
  cycle_end: string | null
  spending_cap: number | null
}

type ProviderBreakdown = { provider: string; credits: number; requests: number }
type ModelBreakdown = {
  provider: string
  model: string
  credits: number
  input_tokens: number
  output_tokens: number
  requests: number
}

type SummaryData = {
  balance: BalanceSummary
  by_provider: ProviderBreakdown[]
  by_model: ModelBreakdown[]
}

type HistoryEvent = {
  id: string
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  credits_charged: number
  created_at: string
}

// ── helpers ──────────────────────────────────────────────────────────

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toLocaleString()
}

function meterColor(pct: number): string {
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 75) return 'bg-orange-500'
  if (pct >= 50) return 'bg-yellow-500'
  return 'bg-emerald-500'
}

const PROVIDER_COLORS: Record<string, string> = {
  openai: '#10b981',
  anthropic: '#f97316',
  google: '#3b82f6',
  mistral: '#a855f7',
  groq: '#eab308',
}

function providerColor(p: string): string {
  return PROVIDER_COLORS[p] ?? '#6b7280'
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ── component ────────────────────────────────────────────────────────

export function UsageTab() {
  const [summary, setSummary] = useState<SummaryData | null>(null)
  const [history, setHistory] = useState<HistoryEvent[]>([])
  const [historyOffset, setHistoryOffset] = useState(0)
  const [filterProvider, setFilterProvider] = useState('')
  const [capInput, setCapInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [fetchTick, setFetchTick] = useState(0)
  const loadingRef = useRef(false)

  useEffect(() => {
    let active = true
    loadingRef.current = true
    const params = new URLSearchParams({ limit: '30', offset: String(historyOffset) })
    if (filterProvider) params.set('provider', filterProvider)

    Promise.all([
      fetch(apiUrl('/api/usage/summary'), { credentials: 'include' }).then((r) => r.ok ? r.json() : null),
      fetch(apiUrl(`/api/usage/history?${params}`), { credentials: 'include' }).then((r) => r.ok ? r.json() : null),
    ]).then(([s, h]) => {
      if (!active) return
      if (s) setSummary(s)
      if (h) setHistory(h.events ?? [])
      setLoading(false)
      loadingRef.current = false
    }).catch(() => { if (active) { setLoading(false); loadingRef.current = false } })

    return () => { active = false }
  }, [historyOffset, filterProvider, fetchTick])

  const refetch = useCallback(() => setFetchTick((t) => t + 1), [])

  const handleSetCap = async () => {
    const cap = capInput.trim() ? parseInt(capInput, 10) : null
    await fetch(apiUrl('/api/usage/spending-cap'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ cap }),
    })
    refetch()
    setCapInput('')
  }

  const handleExportCsv = () => {
    if (!history.length) return
    const headers = ['Time', 'Provider', 'Model', 'Input Tokens', 'Output Tokens', 'Credits']
    const rows = history.map((e) => [
      e.created_at, e.provider, e.model, e.input_tokens, e.output_tokens, e.credits_charged,
    ])
    const csv = [headers, ...rows].map((r) => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `aegis-usage-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
  }

  if (loading && !summary) {
    return (
      <div className='flex items-center justify-center py-20'>
        <LuLoader className='h-6 w-6 animate-spin text-zinc-500' />
      </div>
    )
  }

  const bal = summary?.balance
  const pct = bal?.percent ?? 0

  // Provider breakdown total for pie-chart proportions
  const providerTotal = (summary?.by_provider ?? []).reduce((s, p) => s + p.credits, 0) || 1

  return (
    <div className='space-y-6'>
      <h2 className='text-lg font-semibold'>Usage &amp; Credits</h2>

      {/* ── Balance card ───────────────────────────────────────────── */}
      {bal && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4 space-y-3'>
          <div className='flex items-center justify-between'>
            <div className='flex items-center gap-2'>
              <LuCreditCard className='h-4 w-4 text-blue-400' aria-hidden='true' />
              <span className='text-sm font-medium text-zinc-100 capitalize'>{bal.plan} Plan</span>
            </div>
            <span className='text-xs text-zinc-500'>
              <LuCalendar className='mr-1 inline h-3 w-3' aria-hidden='true' />
              Renews {formatDate(bal.cycle_end)}
            </span>
          </div>
          <div className='relative h-3 overflow-hidden rounded-full bg-[#2a2a2a]'>
            <div
              className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ${meterColor(pct)}`}
              style={{ width: `${Math.min(100, pct)}%` }}
            />
          </div>
          <div className='flex items-center justify-between text-xs text-zinc-400'>
            <span>{formatNumber(bal.used)} / {formatNumber(bal.allowance)} credits used</span>
            <span>{pct.toFixed(1)}%</span>
          </div>
          {(bal.overage ?? 0) > 0 && (
            <p className='text-xs text-orange-400'>
              <LuActivity className='mr-1 inline h-3 w-3' aria-hidden='true' />
              {formatNumber(bal.overage ?? 0)} overage credits
            </p>
          )}
        </div>
      )}

      {/* ── Provider breakdown ─────────────────────────────────────── */}
      {(summary?.by_provider?.length ?? 0) > 0 && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4 space-y-3'>
          <div className='flex items-center gap-2 text-sm font-medium text-zinc-100'>
            <LuChartPie className='h-4 w-4 text-purple-400' aria-hidden='true' />
            Provider Breakdown
          </div>
          <div className='flex h-3 overflow-hidden rounded-full bg-[#2a2a2a]'>
            {summary!.by_provider.map((p) => (
              <div
                key={p.provider}
                className='h-full transition-all duration-500'
                style={{
                  width: `${(p.credits / providerTotal) * 100}%`,
                  backgroundColor: providerColor(p.provider),
                }}
                title={`${p.provider}: ${formatNumber(p.credits)} credits`}
              />
            ))}
          </div>
          <div className='flex flex-wrap gap-3 text-xs'>
            {summary!.by_provider.map((p) => (
              <span key={p.provider} className='flex items-center gap-1.5 text-zinc-300'>
                <span className='inline-block h-2 w-2 rounded-full' style={{ backgroundColor: providerColor(p.provider) }} />
                <span className='capitalize'>{p.provider}</span>
                <span className='text-zinc-500'>{formatNumber(p.credits)} cr · {p.requests} req</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Model leaderboard ─────────────────────────────────────── */}
      {(summary?.by_model?.length ?? 0) > 0 && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4 space-y-3'>
          <div className='flex items-center gap-2 text-sm font-medium text-zinc-100'>
            <LuChartBar className='h-4 w-4 text-emerald-400' aria-hidden='true' />
            Top Models
          </div>
          <div className='overflow-x-auto'>
            <table className='w-full text-xs'>
              <thead>
                <tr className='border-b border-[#2a2a2a] text-left text-zinc-500'>
                  <th className='pb-2 font-medium'>Model</th>
                  <th className='pb-2 font-medium'>Provider</th>
                  <th className='pb-2 font-medium text-right'>Credits</th>
                  <th className='pb-2 font-medium text-right'>Requests</th>
                  <th className='pb-2 font-medium text-right'>Tokens</th>
                </tr>
              </thead>
              <tbody className='divide-y divide-[#2a2a2a]'>
                {summary!.by_model.map((m) => (
                  <tr key={`${m.provider}-${m.model}`} className='text-zinc-300'>
                    <td className='py-1.5 font-mono'>{m.model}</td>
                    <td className='py-1.5 capitalize'>{m.provider}</td>
                    <td className='py-1.5 text-right'>{formatNumber(m.credits)}</td>
                    <td className='py-1.5 text-right'>{m.requests}</td>
                    <td className='py-1.5 text-right text-zinc-500'>
                      {formatNumber(m.input_tokens + m.output_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Usage history ─────────────────────────────────────────── */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4 space-y-3'>
        <div className='flex items-center justify-between'>
          <div className='flex items-center gap-2 text-sm font-medium text-zinc-100'>
            <LuZap className='h-4 w-4 text-blue-400' aria-hidden='true' />
            Usage History
          </div>
          <div className='flex items-center gap-2'>
            <label className='flex items-center gap-1 text-xs text-zinc-500'>
              <LuFilter className='h-3 w-3' aria-hidden='true' />
              <select
                value={filterProvider}
                onChange={(e) => { setFilterProvider(e.target.value); setHistoryOffset(0) }}
                className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-1.5 py-0.5 text-xs text-zinc-300 outline-none'
                aria-label='Filter by provider'
              >
                <option value=''>All providers</option>
                {['openai', 'anthropic', 'google', 'mistral', 'groq'].map((p) => (
                  <option key={p} value={p} className='capitalize'>{p}</option>
                ))}
              </select>
            </label>
            <button
              type='button'
              onClick={handleExportCsv}
              disabled={!history.length}
              className='inline-flex items-center gap-1 rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-40'
            >
              <LuDownload className='h-3 w-3' aria-hidden='true' />
              CSV
            </button>
          </div>
        </div>

        {history.length === 0 ? (
          <p className='py-8 text-center text-xs text-zinc-500'>No usage events yet</p>
        ) : (
          <div className='overflow-x-auto'>
            <table className='w-full text-xs'>
              <thead>
                <tr className='border-b border-[#2a2a2a] text-left text-zinc-500'>
                  <th className='pb-2 font-medium'>Time</th>
                  <th className='pb-2 font-medium'>Provider</th>
                  <th className='pb-2 font-medium'>Model</th>
                  <th className='pb-2 font-medium text-right'>In</th>
                  <th className='pb-2 font-medium text-right'>Out</th>
                  <th className='pb-2 font-medium text-right'>Credits</th>
                </tr>
              </thead>
              <tbody className='divide-y divide-[#2a2a2a]'>
                {history.map((e) => (
                  <tr key={e.id} className='text-zinc-300'>
                    <td className='py-1.5 whitespace-nowrap'>{formatTime(e.created_at)}</td>
                    <td className='py-1.5 capitalize'>{e.provider}</td>
                    <td className='py-1.5 font-mono'>{e.model}</td>
                    <td className='py-1.5 text-right'>{formatNumber(e.input_tokens)}</td>
                    <td className='py-1.5 text-right'>{formatNumber(e.output_tokens)}</td>
                    <td className='py-1.5 text-right font-medium text-blue-300'>{e.credits_charged}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className='flex items-center justify-between pt-1'>
          <button
            type='button'
            disabled={historyOffset === 0}
            onClick={() => setHistoryOffset((o) => Math.max(0, o - 30))}
            className='rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-40'
          >
            Previous
          </button>
          <span className='text-[11px] text-zinc-500'>
            Showing {historyOffset + 1}–{historyOffset + history.length}
          </span>
          <button
            type='button'
            disabled={history.length < 30}
            onClick={() => setHistoryOffset((o) => o + 30)}
            className='rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-40'
          >
            Next
          </button>
        </div>
      </div>

      {/* ── Spending cap ──────────────────────────────────────────── */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4 space-y-3'>
        <div className='flex items-center gap-2 text-sm font-medium text-zinc-100'>
          <LuShield className='h-4 w-4 text-orange-400' aria-hidden='true' />
          Spending Cap
        </div>
        <p className='text-xs text-zinc-400'>
          Set a maximum number of overage credits per billing cycle. Leave empty for no limit.
          {bal?.spending_cap != null && (
            <span className='ml-1 text-zinc-300'>Current cap: {formatNumber(bal.spending_cap)} credits</span>
          )}
        </p>
        <div className='flex items-center gap-2'>
          <input
            type='number'
            placeholder={bal?.spending_cap != null ? String(bal.spending_cap) : 'No limit'}
            value={capInput}
            onChange={(e) => setCapInput(e.target.value)}
            className='w-40 rounded border border-[#2a2a2a] bg-[#0f0f0f] px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-blue-500/60'
            aria-label='Spending cap in credits'
          />
          <button
            type='button'
            onClick={handleSetCap}
            className='rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500'
          >
            {capInput.trim() ? 'Set Cap' : 'Remove Cap'}
          </button>
        </div>
      </div>
    </div>
  )
}
