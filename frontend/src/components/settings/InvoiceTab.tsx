import { useCallback, useEffect, useState } from 'react'
import { LuCreditCard, LuLoader, LuCalendar, LuZap, LuChartBar } from 'react-icons/lu'
import { apiUrl } from '../../lib/api'

// ── Types ────────────────────────────────────────────────────────────────

type Invoice = {
  id: string
  date: string
  description: string
  amount_usd: number
  status: 'paid' | 'pending' | 'failed'
  type: 'subscription' | 'topup'
  payment_method?: string
  invoice_url?: string | null
}

// ── Helper ───────────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return <LuLoader className={`animate-spin ${className ?? 'h-4 w-4'}`} />
}

function StatusBadge({ status }: { status: Invoice['status'] }) {
  const styles = {
    paid: 'bg-emerald-500/15 text-emerald-400',
    pending: 'bg-yellow-500/15 text-yellow-400',
    failed: 'bg-red-500/15 text-red-400',
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${styles[status]}`}>
      {status}
    </span>
  )
}

// ── Component ─────────────────────────────────────────────────────────────

export function InvoiceTab() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'subscription' | 'topup'>('all')

  const loadInvoices = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/payments/invoices'), { credentials: 'include' })
      if (res.ok) {
        const data = (await res.json()) as { invoices: Invoice[] }
        setInvoices(data.invoices ?? [])
      }
    } catch {
      // non-fatal
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInvoices()
  }, [loadInvoices])

  const filtered = filter === 'all' ? invoices : invoices.filter((inv) => inv.type === filter)

  const totalPaid = invoices
    .filter((inv) => inv.status === 'paid')
    .reduce((sum, inv) => sum + inv.amount_usd, 0)

  return (
    <div className='space-y-6'>

      {/* Header */}
      <div>
        <h2 className='text-base font-semibold text-white'>Invoices</h2>
        <p className='mt-0.5 text-xs text-zinc-500'>Your billing history and payment receipts.</p>
      </div>

      {/* Summary cards */}
      {!loading && invoices.length > 0 && (
        <div className='grid grid-cols-2 gap-3'>
          <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <LuZap className='h-3.5 w-3.5 text-cyan-400' />
              <p className='text-[11px] uppercase tracking-wider text-zinc-500'>Total paid</p>
            </div>
            <p className='text-xl font-semibold text-white'>${totalPaid.toFixed(2)}</p>
          </div>
          <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
            <div className='flex items-center gap-2 mb-2'>
              <LuCalendar className='h-3.5 w-3.5 text-zinc-400' />
              <p className='text-[11px] uppercase tracking-wider text-zinc-500'>Invoices</p>
            </div>
            <p className='text-xl font-semibold text-white'>{invoices.length}</p>
          </div>
        </div>
      )}

      {/* Filter */}
      {!loading && invoices.length > 0 && (
        <div className='flex gap-2'>
          {(['all', 'subscription', 'topup'] as const).map((f) => (
            <button
              key={f}
              type='button'
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                filter === f
                  ? 'bg-cyan-500/15 text-cyan-300'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {f === 'all' ? 'All' : f === 'subscription' ? 'Subscriptions' : 'Top-ups'}
            </button>
          ))}
        </div>
      )}

      {/* Invoice list */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] overflow-hidden'>
        {loading ? (
          <div className='flex items-center justify-center gap-2 py-12 text-zinc-500'>
            <SpinnerIcon />
            <span className='text-sm'>Loading invoices…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className='flex flex-col items-center justify-center gap-3 py-14 text-center'>
            <div className='flex h-12 w-12 items-center justify-center rounded-full bg-[#1a1a1a]'>
              <LuChartBar className='h-5 w-5 text-zinc-600' />
            </div>
            <div>
              <p className='text-sm font-medium text-zinc-400'>No invoices yet</p>
              <p className='mt-0.5 text-xs text-zinc-600'>
                Your receipts will appear here after your first payment.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Table header */}
            <div className='grid grid-cols-[1fr_auto_auto_auto] gap-4 border-b border-[#1e1e1e] px-5 py-3 text-[10px] uppercase tracking-wider text-zinc-600'>
              <span>Description</span>
              <span className='text-right'>Amount</span>
              <span className='text-right'>Date</span>
              <span className='text-right'>Status</span>
            </div>

            {/* Rows */}
            {filtered.map((inv) => (
              <div
                key={inv.id}
                className='grid grid-cols-[1fr_auto_auto_auto] gap-4 border-b border-[#1a1a1a] px-5 py-3.5 last:border-0 hover:bg-white/[0.02]'
              >
                <div className='min-w-0'>
                  <div className='flex items-center gap-2'>
                    <div className='flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#1a1a1a]'>
                      {inv.type === 'subscription' ? (
                        <LuZap className='h-3.5 w-3.5 text-cyan-400' />
                      ) : (
                        <LuCreditCard className='h-3.5 w-3.5 text-purple-400' />
                      )}
                    </div>
                    <div className='min-w-0'>
                      <p className='truncate text-xs font-medium text-zinc-200'>{inv.description}</p>
                      {inv.payment_method && (
                        <p className='text-[10px] text-zinc-600 capitalize'>{inv.payment_method}</p>
                      )}
                    </div>
                  </div>
                </div>
                <div className='flex items-center justify-end'>
                  <span className='text-sm font-medium text-white'>${inv.amount_usd.toFixed(2)}</span>
                </div>
                <div className='flex items-center justify-end'>
                  <span className='text-xs text-zinc-500'>
                    {new Date(inv.date).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })}
                  </span>
                </div>
                <div className='flex items-center justify-end gap-2'>
                  <StatusBadge status={inv.status} />
                  {inv.invoice_url && (
                    <a
                      href={inv.invoice_url}
                      target='_blank'
                      rel='noreferrer'
                      className='text-[10px] text-cyan-500 hover:text-cyan-300'
                    >
                      PDF
                    </a>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Refresh */}
      {!loading && (
        <div className='flex justify-end'>
          <button
            type='button'
            onClick={() => void loadInvoices()}
            className='flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300'
          >
            <LuLoader className='h-3 w-3' />
            Refresh
          </button>
        </div>
      )}
    </div>
  )
}
