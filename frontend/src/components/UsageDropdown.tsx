import { useState } from 'react'
import type { UsageBalance } from '../hooks/useUsage'
import type { ContextMeterState } from '../hooks/useContextMeter'
import { Icons } from './icons'

type UsageDropdownProps = {
  balance: UsageBalance | null
  context: ContextMeterState
  modelLabel: string
}

// ── Formatting helpers ──────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

// Phase 9: human labels for the eight runtime meter buckets. Anything
// the backend introduces later still renders — we fall back to the
// raw bucket name so a forward-compatible frontend doesn't hide new
// buckets behind a generic label.
const BUCKET_LABELS: Record<string, string> = {
  system_prompt: 'System prompt',
  active_tools: 'Active tools',
  checkpoints: 'Checkpoints',
  workspace_files: 'Workspace files',
  pinned_memories: 'Pinned memories',
  pending_tool_outputs: 'Pending tool outputs',
  chat_history: 'Chat history',
  current_user_message: 'Current message',
}

function bucketLabel(name: string): string {
  return BUCKET_LABELS[name] ?? name.replace(/_/g, ' ')
}

function formatCredits(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`
  return n.toLocaleString()
}

function planAllowanceLabel(allowance: number): string {
  return `${formatCredits(allowance)} credits`
}

// ── Bar color logic ─────────────────────────────────────────────────

function barColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 75) return 'bg-amber-500'
  if (percent >= 50) return 'bg-blue-500'
  return 'bg-cyan-500'
}

function barTrack(): string {
  return 'bg-[#2a2a2a]'
}

// ── Component ───────────────────────────────────────────────────────

export function UsageDropdown({ balance, context, modelLabel }: UsageDropdownProps) {
  const [expanded, setExpanded] = useState(false)

  const ctxPercent = Math.min(100, context.percent)
  const creditPercent = balance ? Math.min(100, balance.percent) : 0
  const creditUsed = balance?.used ?? 0
  const creditAllowance = balance?.allowance ?? 1000

  return (
    <div className='rounded-lg border border-[#2a2a2a] bg-[#141414] overflow-hidden'>
      {/* ── Header (always visible) ── */}
      <button
        type='button'
        onClick={() => setExpanded((p) => !p)}
        className='flex w-full items-center justify-between px-3 py-2.5 text-left transition hover:bg-[#1a1a1a]'
      >
        <span className='flex items-center gap-2 text-xs font-medium text-zinc-300'>
          {Icons.chevronRight({
            className: `h-3 w-3 shrink-0 text-zinc-500 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`,
          })}
          Usage
        </span>
        {/* Mini context indicator when collapsed */}
        {!expanded && (
          <span className='text-[10px] text-zinc-500'>
            {ctxPercent.toFixed(0)}%
          </span>
        )}
      </button>

      {/* ── Context meter (always visible below header) ── */}
      <div className='px-3 pb-2.5'>
        <div className='mb-1.5 flex items-center justify-between'>
          <span className='text-[10px] font-medium text-zinc-400'>Context</span>
          <span className='text-[10px] text-zinc-500'>
            {formatTokens(context.current.tokensUsed)} / {formatTokens(context.current.contextLimit)}
          </span>
        </div>
        <div className={`relative h-1.5 w-full overflow-hidden rounded-full ${barTrack()}`}>
          <div
            className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ease-out ${barColor(ctxPercent)} ${context.isCompacting ? 'animate-pulse' : ''}`}
            style={{ width: `${ctxPercent}%` }}
          />
        </div>
        <div className='mt-1 flex items-center justify-between'>
          <span className='truncate text-[9px] text-zinc-600'>{modelLabel}</span>
          {context.isCompacting && (
            <span className='text-[9px] text-amber-400 animate-pulse'>Compacting…</span>
          )}
        </div>
      </div>

      {/* ── Expanded: bucket breakdown (runtime meter only) + credits + plan info ── */}
      {expanded && (
        <div className='border-t border-[#2a2a2a] px-3 py-2.5 space-y-3'>
          {context.source === 'runtime' && context.buckets.length > 0 && (
            <div>
              <div className='mb-1.5 flex items-center justify-between'>
                <span className='text-[10px] font-medium text-zinc-400'>Context breakdown</span>
                <span className='text-[10px] text-zinc-500'>
                  projected {context.projectedPct.toFixed(1)}%
                </span>
              </div>
              <ul className='space-y-1'>
                {context.buckets
                  // Hide perfectly-empty buckets so the breakdown stays
                  // readable on a fresh session — they will reappear
                  // automatically when the bucket starts carrying data.
                  .filter((b) => b.tokens > 0)
                  .map((bucket) => {
                    const share = context.current.tokensUsed > 0
                      ? Math.min(100, (bucket.tokens / context.current.tokensUsed) * 100)
                      : 0
                    return (
                      <li key={bucket.name} className='flex items-center justify-between text-[10px]'>
                        <span className='truncate text-zinc-400'>{bucketLabel(bucket.name)}</span>
                        <span className='ml-2 shrink-0 text-zinc-500'>
                          {formatTokens(bucket.tokens)}
                          <span className='ml-1 text-zinc-600'>({share.toFixed(0)}%)</span>
                        </span>
                      </li>
                    )
                  })}
              </ul>
              <div className='mt-1.5 text-[9px] text-zinc-600'>
                Auto-compaction at {context.compactThresholdPct.toFixed(0)}% projected
              </div>
            </div>
          )}
          {/* Credits meter */}
          <div>
            <div className='mb-1.5 flex items-center justify-between'>
              <span className='text-[10px] font-medium text-zinc-400'>Credits</span>
              <span className='text-[10px] text-zinc-500'>
                {formatCredits(creditUsed)} of {planAllowanceLabel(creditAllowance)} used
              </span>
            </div>
            <div className={`relative h-1.5 w-full overflow-hidden rounded-full ${barTrack()}`}>
              <div
                className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ease-out ${barColor(creditPercent)}`}
                style={{ width: `${creditPercent}%` }}
              />
            </div>
          </div>

          {/* Plan badge */}
          {balance && (
            <div className='flex items-center justify-between'>
              <span className='rounded-full border border-[#2a2a2a] bg-[#111] px-2 py-0.5 text-[9px] uppercase tracking-wider text-zinc-500'>
                {balance.plan} plan
              </span>
              <span className='text-[9px] text-zinc-600'>
                {formatCredits(Math.max(0, creditAllowance - creditUsed))} remaining
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
