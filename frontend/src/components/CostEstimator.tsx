import { LuZap } from 'react-icons/lu'
import type { CreditRates, CostTier } from '../lib/creditRates'
import { estimateCredits, estimateTokens, getTier, TIER_CONFIG } from '../lib/creditRates'

type CostEstimatorProps = {
  text: string
  provider: string
  model: string
  rates: CreditRates | null
}

function TierDot({ tier }: { tier: CostTier }) {
  const config = TIER_CONFIG[tier]
  return (
    <span
      className='inline-block h-2 w-2 rounded-full'
      style={{ backgroundColor: config.color }}
      aria-label={`${config.label} tier`}
    />
  )
}

export function CostEstimator({ text, provider, model, rates }: CostEstimatorProps) {
  if (!rates || !text.trim()) return null

  const inputTokens = estimateTokens(text)
  // Assume a typical output ratio of ~3× input
  const estimatedOutput = inputTokens * 3
  const credits = estimateCredits(rates, provider, model, inputTokens, estimatedOutput)
  const tier = getTier(rates, provider, model)
  const config = TIER_CONFIG[tier]

  return (
    <div className='flex items-center gap-2 px-1 text-[11px] text-zinc-500'>
      <LuZap className='h-3 w-3 text-zinc-600' aria-hidden='true' />
      <span>
        ~{credits} credit{credits !== 1 ? 's' : ''}
      </span>
      <span className='flex items-center gap-1'>
        <TierDot tier={tier} />
        <span className={config.text}>{config.label}</span>
      </span>
    </div>
  )
}
