// Credit rates per 1K tokens - mirrors backend/credit_rates.py.
// Fetched from /api/usage/rates on startup and cached client-side.

export type CostTier = 'budget' | 'mid' | 'standard' | 'premium' | 'ultra'

export type CreditRate = {
  input: number
  output: number
  tier: CostTier
}

export type CreditRates = Record<string, Record<string, CreditRate>>

// Tier UI config - colours use Tailwind classes, no emojis
export const TIER_CONFIG: Record<CostTier, { color: string; bg: string; text: string; label: string }> = {
  budget:   { color: '#22c55e', bg: 'bg-green-500/10',  text: 'text-green-400',  label: 'Budget' },
  mid:      { color: '#eab308', bg: 'bg-yellow-500/10', text: 'text-yellow-400', label: 'Mid' },
  standard: { color: '#3b82f6', bg: 'bg-blue-500/10',   text: 'text-blue-400',   label: 'Standard' },
  premium:  { color: '#f97316', bg: 'bg-orange-500/10', text: 'text-orange-400', label: 'Premium' },
  ultra:    { color: '#ef4444', bg: 'bg-red-500/10',    text: 'text-red-400',    label: 'Ultra' },
}

/** Estimate credit cost on the client (before sending). */
export function estimateCredits(
  rates: CreditRates,
  provider: string,
  model: string,
  inputTokens: number,
  outputTokens: number,
): number {
  const rate = rates[provider]?.[model] ?? { input: 1.0, output: 5.0 }
  const exact = (inputTokens / 1000) * rate.input + (outputTokens / 1000) * rate.output
  return Math.max(1, Math.ceil(exact))
}

/** Very rough token estimate from character count (for pre-send cost preview). */
export function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 3.5))
}

/** Get the tier for a model from cached rates. */
export function getTier(rates: CreditRates, provider: string, model: string): CostTier {
  return (rates[provider]?.[model]?.tier as CostTier) ?? 'standard'
}

/** Estimate credits for a typical message (~500 in, ~1500 out). */
export function estimateTypicalCredits(rates: CreditRates, provider: string, model: string): number {
  return estimateCredits(rates, provider, model, 500, 1500)
}
