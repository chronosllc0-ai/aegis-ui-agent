/**
 * SubAgentPanel – Codex-style full-width background agents bar.
 *
 * • Sits directly above the input bar, spanning its full width.
 * • Shows "N background agents (@ to tag agents)" with a chevron toggle.
 * • Expands upward to reveal agent rows: colored shimmer name + live status.
 * • Clicking an agent name shows the exact model it uses.
 * • "Open" button on each row opens the sub-agent's chat thread.
 */

import { useMemo, useState } from 'react'
import type { SubAgentInfo, SubAgentStep } from '../hooks/useWebSocket'

interface SubAgentPanelProps {
  agents: SubAgentInfo[]
  steps: Record<string, SubAgentStep[]>
  onCancel: (sub_id: string) => void
  onMessage: (sub_id: string, message: string) => void
  onOpenThread?: (sub_id: string) => void
}

// Unique warm colors for agent names (cycles if > palette length)
const NAME_COLORS = [
  'text-orange-400',
  'text-green-400',
  'text-sky-400',
  'text-violet-400',
  'text-rose-400',
  'text-amber-400',
  'text-teal-400',
]

function agentNameColor(index: number): string {
  return NAME_COLORS[index % NAME_COLORS.length]
}

// Derive a short human-readable status string from the latest step
function liveStatusText(agent: SubAgentInfo, steps: SubAgentStep[]): string {
  if (agent.status === 'spawning') return 'is starting up'
  if (agent.status === 'completed') return 'finished'
  if (agent.status === 'failed') return 'encountered an error'
  if (agent.status === 'cancelled') return 'was cancelled'

  // running — infer from last step content
  const lastStep = steps[steps.length - 1]
  if (!lastStep) return 'is awaiting instruction'

  const content = lastStep.step?.content ?? ''
  const type = lastStep.step?.type ?? ''

  if (type === 'thinking' || content.toLowerCase().startsWith('thinking')) return 'is thinking'
  if (type === 'tool_call' || content.startsWith('[')) {
    // Extract tool name
    const match = content.match(/^\[([^\]]+)\]/)
    if (match) return `is running ${match[1].replace(/_/g, ' ')}`
  }
  if (content.toLowerCase().includes('edit') || content.toLowerCase().includes('writ')) return 'is editing a file'
  if (content.toLowerCase().includes('read') || content.toLowerCase().includes('fetch')) return 'is reading files'
  if (content.toLowerCase().includes('search')) return 'is searching'
  if (content) return content.slice(0, 48) + (content.length > 48 ? '…' : '')
  return 'is working'
}

export function SubAgentPanel({ agents, steps, onCancel, onMessage, onOpenThread }: SubAgentPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [hoveredModel, setHoveredModel] = useState<string | null>(null) // sub_id of hovered name
  void onCancel

  const handleSteer = (subId: string): void => {
    const message = window.prompt('Steer sub-agent message')
    if (!message) return
    const trimmed = message.trim()
    if (!trimmed) return
    onMessage(subId, trimmed)
  }

  const activeCount = useMemo(
    () => agents.filter((a) => a.status === 'spawning' || a.status === 'running').length,
    [agents],
  )

  if (agents.length === 0) return null

  return (
    <div className='w-full'>
      {/* ── Expanded agent rows ─────────────────────────────────────────── */}
      {expanded && (
        <div className='mb-1 w-full rounded-xl border border-[#2a2a2a] bg-[#141414] overflow-hidden'>
          {agents.map((agent, idx) => {
            const agentSteps = steps[agent.sub_id] ?? []
            const isLive = agent.status === 'spawning' || agent.status === 'running'
            const nameColor = agentNameColor(idx)
            const statusStr = liveStatusText(agent, agentSteps)

            return (
              <div
                key={agent.sub_id}
                className='flex items-center gap-3 border-b border-[#1e1e1e] px-3 py-2 last:border-b-0'
              >
                {/* Agent name — shimmer when live, tooltip shows exact model */}
                <div className='relative flex-shrink-0'>
                  <button
                    type='button'
                    onMouseEnter={() => setHoveredModel(agent.sub_id)}
                    onMouseLeave={() => setHoveredModel(null)}
                    className='text-left'
                  >
                    <span
                      className={`text-xs font-semibold ${nameColor} ${isLive ? 'agent-name-shimmer' : ''}`}
                    >
                      {/* Derive short display name from instruction */}
                      {agent.instruction.split(' ').slice(0, 2).join(' ').slice(0, 18) || `Agent ${idx + 1}`}
                    </span>
                  </button>

                  {/* Model tooltip */}
                  {hoveredModel === agent.sub_id && (
                    <div className='absolute bottom-full left-0 mb-1 z-50 whitespace-nowrap rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-2.5 py-1.5 text-[11px] text-zinc-300 shadow-lg'>
                      {agent.model}
                    </div>
                  )}
                </div>

                {/* Live status stream */}
                <p className={`flex-1 truncate text-[11px] ${isLive ? 'text-zinc-400' : 'text-zinc-600'}`}>
                  {statusStr}
                </p>

                {/* Open thread button */}
                <button
                  type='button'
                  onClick={() => onOpenThread?.(agent.sub_id)}
                  className='flex-shrink-0 text-[11px] font-medium text-zinc-400 hover:text-zinc-200 transition-colors'
                >
                  Open
                </button>
                {isLive && (
                  <button
                    type='button'
                    onClick={() => handleSteer(agent.sub_id)}
                    className='flex-shrink-0 text-[11px] font-medium text-blue-300 hover:text-blue-200 transition-colors'
                  >
                    Steer
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Summary bar ─────────────────────────────────────────────────── */}
      <div className='flex w-full items-center rounded-xl border border-[#2a2a2a] bg-[#141414] px-3 py-2'>
        {/* Checkbox-style indicator */}
        <span className='mr-2 flex-shrink-0 text-zinc-500'>
          <svg className='h-3.5 w-3.5' viewBox='0 0 16 16' fill='none'>
            <rect x='1.5' y='1.5' width='13' height='13' rx='3' stroke='currentColor' strokeWidth='1.5'/>
            {activeCount > 0 && <path d='M4.5 8l2.5 2.5 4.5-4.5' stroke='#60a5fa' strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round'/>}
          </svg>
        </span>

        {/* Label with colored names preview */}
        <span className='flex-1 truncate text-[11px] text-zinc-400'>
          {agents.length} background agent{agents.length !== 1 ? 's' : ''}{' '}
          <span className='text-zinc-600'>(@ to tag agents)</span>
        </span>

        {/* Settings + chevron */}
        <div className='flex items-center gap-3 flex-shrink-0'>
          <span className='text-[11px] text-zinc-500'>Settings</span>
          <span className='text-[11px] text-zinc-500'>
            {activeCount > 0 && (
              <span className='mr-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-500/20 text-[9px] text-blue-300'>
                {activeCount}
              </span>
            )}
          </span>
          <button
            type='button'
            onClick={() => setExpanded((v) => !v)}
            className='flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors'
          >
            <svg
              className={`h-3 w-3 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
              viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'
            >
              <path d='m18 15-6-6-6 6'/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
