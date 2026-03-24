import React, { useEffect, useState } from 'react'
import { Icons } from '../icons'
import { useToast } from '../../hooks/useToast'
import { apiUrl } from '../../lib/api'

type PaymentMethod = {
  id: string
  name: string
  description: string
  enabled: boolean
}

interface PaymentSettingsModalProps {
  onClose: () => void
}

function CreditCardIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className={className ?? 'h-5 w-5'} aria-hidden='true'>
      <rect x='2' y='5' width='20' height='14' rx='2' />
      <path d='M2 10h20' />
      <path d='M6 15h4' />
    </svg>
  )
}

function BitcoinIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' className={className ?? 'h-5 w-5'} aria-hidden='true'>
      <path d='M9.5 2H14a3.5 3.5 0 0 1 0 7H9.5V2Z' />
      <path d='M9.5 9H15a3.5 3.5 0 0 1 0 7H9.5V9Z' />
      <path d='M8 2v18M12 2v2M12 18v2' />
    </svg>
  )
}

const METHOD_ICONS: Record<string, (p: { className?: string }) => React.ReactElement> = {
  stripe: CreditCardIcon,
  coinbase: BitcoinIcon,
}

const METHOD_COLORS: Record<string, string> = {
  stripe: 'text-cyan-400 bg-cyan-500/10',
  coinbase: 'text-orange-400 bg-orange-500/10',
}

export function PaymentSettingsModal({ onClose }: PaymentSettingsModalProps) {
  const [methods, setMethods] = useState<PaymentMethod[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(apiUrl('/api/admin/payment-settings'), { credentials: 'include' })
        if (!res.ok) throw new Error('Failed to load payment settings')
        const data = (await res.json()) as { methods: PaymentMethod[] }
        setMethods(data.methods)
      } catch {
        toast.error('Failed to load payment settings')
      } finally {
        setLoading(false)
      }
    })()
  }, [toast])

  const toggleMethod = (id: string) => {
    setMethods((prev) =>
      prev.map((m) => (m.id === id ? { ...m, enabled: !m.enabled } : m))
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const methodsPayload: Record<string, boolean> = {}
      for (const m of methods) {
        methodsPayload[m.id] = m.enabled
      }
      const res = await fetch(apiUrl('/api/admin/payment-settings'), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ methods: methodsPayload }),
      })
      if (!res.ok) throw new Error('Failed to save')
      toast.success('Payment settings saved')
      onClose()
    } catch {
      toast.error('Failed to save payment settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm'
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className='relative w-full max-w-md rounded-2xl border border-white/10 bg-[#0c1018] shadow-2xl'>
        {/* Header */}
        <div className='flex items-center justify-between border-b border-white/8 p-5'>
          <div className='flex items-center gap-3'>
            <div className='flex h-8 w-8 items-center justify-center rounded-lg bg-white/6 text-zinc-400'>
              {Icons.settings({ className: 'h-4 w-4' })}
            </div>
            <div>
              <h2 className='text-sm font-semibold text-white'>Payment Methods</h2>
              <p className='text-[11px] text-zinc-500'>Toggle which methods are active for users</p>
            </div>
          </div>
          <button
            type='button'
            onClick={onClose}
            className='flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-white/8 hover:text-white'
          >
            {Icons.back({ className: 'h-3.5 w-3.5 rotate-180' })}
            <span className='sr-only'>Close</span>
          </button>
        </div>

        {/* Body */}
        <div className='p-5'>
          {loading ? (
            <p className='py-6 text-center text-sm text-zinc-500'>Loading…</p>
          ) : (
            <div className='space-y-3'>
              {methods.map((method) => {
                const Icon = METHOD_ICONS[method.id]
                const colorClass = METHOD_COLORS[method.id] ?? 'text-zinc-400 bg-white/6'
                return (
                  <div
                    key={method.id}
                    className={`flex items-center gap-4 rounded-xl border p-4 transition ${
                      method.enabled
                        ? 'border-white/12 bg-white/4'
                        : 'border-white/6 bg-transparent opacity-60'
                    }`}
                  >
                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${colorClass}`}>
                      {Icon && <Icon className='h-5 w-5' />}
                    </div>
                    <div className='min-w-0 flex-1'>
                      <p className='text-sm font-medium text-white'>{method.name}</p>
                      <p className='text-[12px] text-zinc-500'>{method.description}</p>
                    </div>
                    {/* Toggle */}
                    <button
                      type='button'
                      role='switch'
                      aria-checked={method.enabled}
                      onClick={() => toggleMethod(method.id)}
                      className={`relative flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors focus:outline-none ${
                        method.enabled ? 'bg-cyan-500' : 'bg-zinc-700'
                      }`}
                    >
                      <span
                        className={`h-4 w-4 rounded-full bg-white shadow transition-transform ${
                          method.enabled ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                      <span className='sr-only'>{method.enabled ? 'Enabled' : 'Disabled'}</span>
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          {!loading && (
            <div className='mt-5 flex gap-3'>
              <button
                type='button'
                onClick={onClose}
                className='flex-1 rounded-full border border-white/10 py-2.5 text-sm text-zinc-400 transition hover:border-white/20 hover:text-zinc-200'
              >
                Cancel
              </button>
              <button
                type='button'
                onClick={() => void handleSave()}
                disabled={saving}
                className='flex-1 rounded-full bg-cyan-500 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50'
              >
                {saving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
