import { LuActivity, LuTrendingUp, LuZap } from 'react-icons/lu'
import type { UsageBalance, StreamingState } from '../hooks/useUsage'

type UsageMeterBarProps = {
  balance: UsageBalance | null
  sessionCredits: number
  sessionMessages: number
  streaming: StreamingState
}

function meterColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 75) return 'bg-orange-500'
  if (percent >= 50) return 'bg-yellow-500'
  return 'bg-emerald-500'
}

function meterGlow(percent: number): string {
  if (percent >= 90) return 'shadow-[0_0_8px_rgba(239,68,68,0.5)]'
  if (percent >= 75) return 'shadow-[0_0_8px_rgba(249,115,22,0.4)]'
  return ''
}

function formatNumber(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString()
}

export function UsageMeterBar({ balance, sessionCredits, sessionMessages, streaming }: UsageMeterBarProps) {
  if (!balance) return null

  const percent = Math.min(100, balance.percent)
  const remaining = Math.max(0, balance.allowance - balance.used)
  const isStreaming = streaming.outputTokensSoFar > 0

  return (
    <div className='flex items-center gap-3 rounded-lg border border-[#2a2a2a] bg-[#171717] px-3 py-1.5 text-xs'>
      {/* Progress bar */}
      <div className='flex min-w-[120px] items-center gap-2'>
        <LuZap className='h-3.5 w-3.5 shrink-0 text-blue-400' aria-hidden='true' />
        <div className='relative h-2 w-full min-w-[80px] overflow-hidden rounded-full bg-[#2a2a2a]'>
          <div
            className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${meterColor(percent)} ${meterGlow(percent)}`}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <span className='whitespace-nowrap text-zinc-400'>
        {percent.toFixed(1)}% &middot; {formatNumber(remaining)} left
      </span>

      {/* Session counter */}
      {sessionMessages > 0 && (
        <span className='flex items-center gap-1 whitespace-nowrap text-zinc-500'>
          <LuTrendingUp className='h-3 w-3' aria-hidden='true' />
          {formatNumber(sessionCredits)} cr / {sessionMessages} msg
        </span>
      )}

      {/* Streaming indicator */}
      {isStreaming && (
        <span className='flex items-center gap-1 whitespace-nowrap text-blue-400 animate-pulse'>
          <LuActivity className='h-3 w-3' aria-hidden='true' />
          {streaming.outputTokensSoFar} tok
        </span>
      )}

      {/* Plan badge */}
      <span className='rounded-full border border-[#2a2a2a] bg-[#111] px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500'>
        {balance.plan}
      </span>
    </div>
  )
}
