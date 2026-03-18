import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'
import type { CreditRates } from '../lib/creditRates'

export type UsageBalance = {
  plan: 'free' | 'pro' | 'team'
  used: number
  allowance: number
  percent: number
  overage?: number
  remaining?: number
  spending_cap?: number | null
  cycle_end?: string | null
}

export type StreamingState = {
  outputTokensSoFar: number
  estimatedCredits: number
}

export type UsageState = {
  balance: UsageBalance | null
  sessionCredits: number
  sessionMessages: number
  streaming: StreamingState
  rates: CreditRates | null
  loading: boolean
}

const INITIAL_STATE: UsageState = {
  balance: null,
  sessionCredits: 0,
  sessionMessages: 0,
  streaming: { outputTokensSoFar: 0, estimatedCredits: 0 },
  rates: null,
  loading: true,
}

export function useUsage() {
  const [state, setState] = useState<UsageState>(INITIAL_STATE)

  // Fetch balance + rates on mount
  useEffect(() => {
    let active = true
    Promise.all([
      fetch(apiUrl('/api/usage/balance'), { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(apiUrl('/api/usage/rates'), { credentials: 'include' })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]).then(([balanceData, ratesData]) => {
      if (!active) return
      setState((prev) => ({
        ...prev,
        balance: balanceData ?? prev.balance,
        rates: ratesData?.rates ?? prev.rates,
        loading: false,
      }))
    })
    return () => { active = false }
  }, [])

  /** Handle incoming WebSocket usage messages. */
  const handleUsageMessage = useCallback((msg: Record<string, unknown>) => {
    const type = msg.type as string | undefined
    if (type === 'usage') {
      setState((prev) => ({
        ...prev,
        balance: (msg.balance as UsageBalance) ?? prev.balance,
        sessionCredits: prev.sessionCredits + ((msg.credits_used as number) ?? 0),
        sessionMessages: prev.sessionMessages + 1,
        streaming: { outputTokensSoFar: 0, estimatedCredits: 0 },
      }))
    } else if (type === 'usage_tick') {
      setState((prev) => ({
        ...prev,
        streaming: {
          outputTokensSoFar: (msg.output_tokens_so_far as number) ?? prev.streaming.outputTokensSoFar,
          estimatedCredits: (msg.estimated_credits as number) ?? prev.streaming.estimatedCredits,
        },
      }))
    }
  }, [])

  /** Reset session-level counters (e.g. on new session). */
  const resetSession = useCallback(() => {
    setState((prev) => ({ ...prev, sessionCredits: 0, sessionMessages: 0 }))
  }, [])

  /** Force re-fetch balance from the API. */
  const refreshBalance = useCallback(() => {
    fetch(apiUrl('/api/usage/balance'), { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setState((prev) => ({ ...prev, balance: data }))
      })
      .catch(() => {})
  }, [])

  return { ...state, handleUsageMessage, resetSession, refreshBalance }
}
