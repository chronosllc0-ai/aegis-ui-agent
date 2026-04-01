import { useState } from 'react'
import { LuTriangleAlert, LuArrowUpRight, LuX } from 'react-icons/lu'
import type { UsageBalance } from '../hooks/useUsage'

type SpendingAlertProps = {
  balance: UsageBalance | null
  onUpgrade?: () => void
}

const THRESHOLDS = [90, 75, 50] as const

export function SpendingAlert({ balance, onUpgrade }: SpendingAlertProps) {
  const [dismissed, setDismissed] = useState<Set<number>>(new Set())

  // Derive active threshold from props - no effect needed
  const activeThreshold = (() => {
    if (!balance) return null
    for (const t of THRESHOLDS) {
      if (balance.percent >= t && !dismissed.has(t)) return t
    }
    return null
  })()

  const handleDismiss = () => {
    if (activeThreshold !== null) {
      setDismissed((prev) => new Set([...prev, activeThreshold]))
    }
  }

  if (activeThreshold === null || !balance) return null

  const used = balance.used.toLocaleString()
  const total = balance.allowance.toLocaleString()

  return (
    <div
      role='alert'
      className='fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-3 rounded-xl border border-orange-500/30 bg-[#1a1a1a] px-4 py-3 shadow-lg shadow-orange-500/10 animate-in slide-in-from-right'
    >
      <LuTriangleAlert className='mt-0.5 h-5 w-5 shrink-0 text-orange-400' aria-hidden='true' />
      <div className='flex-1 text-sm'>
        <p className='font-medium text-zinc-100'>
          {activeThreshold}% of credits used
        </p>
        <p className='mt-0.5 text-zinc-400'>
          {used} / {total} credits this cycle.
        </p>
        <div className='mt-2 flex items-center gap-2'>
          {balance.plan === 'free' && onUpgrade && (
            <button
              type='button'
              onClick={onUpgrade}
              className='inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500'
            >
              Upgrade <LuArrowUpRight className='h-3 w-3' aria-hidden='true' />
            </button>
          )}
          <button
            type='button'
            onClick={handleDismiss}
            className='rounded-md border border-[#2a2a2a] px-3 py-1 text-xs text-zinc-400 hover:text-zinc-200'
          >
            Dismiss
          </button>
        </div>
      </div>
      <button type='button' onClick={handleDismiss} className='shrink-0 text-zinc-500 hover:text-zinc-300' aria-label='Close'>
        <LuX className='h-4 w-4' />
      </button>
    </div>
  )
}
