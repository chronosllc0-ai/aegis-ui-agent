/**
 * SubAgentPanel - compact dropdown control for thread-scoped background agents.
 */

import { useMemo, useState } from 'react'
import type { SubAgentInfo, SubAgentStep } from '../hooks/useWebSocket'

interface SubAgentPanelProps {
  agents: SubAgentInfo[]
  steps: Record<string, SubAgentStep[]>
  onCancel: (sub_id: string) => void
  onMessage: (sub_id: string, message: string) => void
}

const STATUS_DOT: Record<SubAgentInfo['status'], string> = {
  spawning: 'bg-amber-400',
  running: 'bg-blue-400 animate-pulse',
  completed: 'bg-emerald-400',
  failed: 'bg-red-400',
  cancelled: 'bg-zinc-500',
}

export function SubAgentPanel({ agents, steps, onCancel, onMessage }: SubAgentPanelProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})

  const activeCount = useMemo(
    () => agents.filter((a) => a.status === 'spawning' || a.status === 'running').length,
    [agents],
  )

  if (agents.length === 0) return null

  return (
    <div className='relative'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className='inline-flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#171717] px-3 py-1.5 text-xs text-zinc-300 hover:bg-[#202020]'
      >
        <span className='inline-flex h-4 w-4 items-center justify-center rounded-full border border-zinc-600 text-[10px]'>
          {agents.length}
        </span>
        <span>{agents.length} background agent{agents.length !== 1 ? 's' : ''}</span>
        {activeCount > 0 && <span className='rounded-full bg-blue-500/20 px-1.5 py-0.5 text-[10px] text-blue-300'>{activeCount} active</span>}
        <span className='text-[11px] text-zinc-500'>Open</span>
      </button>

      {open && (
        <div className='absolute bottom-[calc(100%+8px)] left-0 z-40 w-[min(92vw,560px)] rounded-2xl border border-[#2a2a2a] bg-[#141414] p-3 shadow-2xl'>
          <div className='mb-2 flex items-center justify-between'>
            <p className='text-xs font-semibold text-zinc-200'>Background agents (thread scoped)</p>
            <button type='button' onClick={() => setOpen(false)} className='text-xs text-zinc-500 hover:text-zinc-300'>Close</button>
          </div>
          <div className='max-h-72 space-y-2 overflow-y-auto pr-1'>
            {agents.map((agent) => {
              const recent = steps[agent.sub_id] ?? []
              const isLive = agent.status === 'spawning' || agent.status === 'running'
              return (
                <div key={agent.sub_id} className='rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-2'>
                  <div className='mb-1 flex items-start justify-between gap-2'>
                    <div className='min-w-0'>
                      <p className='truncate text-xs font-medium text-zinc-200'>{agent.instruction}</p>
                      <p className='text-[10px] text-zinc-500'>Model: {agent.model}</p>
                    </div>
                    <div className='flex items-center gap-1'>
                      <span className={`h-2 w-2 rounded-full ${STATUS_DOT[agent.status]}`} />
                      <span className='text-[10px] text-zinc-500'>{agent.status}</span>
                      {isLive && (
                        <button
                          type='button'
                          onClick={() => onCancel(agent.sub_id)}
                          className='ml-1 rounded-md border border-red-500/30 px-1.5 py-0.5 text-[10px] text-red-300 hover:bg-red-500/10'
                        >
                          Stop
                        </button>
                      )}
                    </div>
                  </div>
                  {recent.length > 0 ? (
                    <p className='truncate text-[10px] text-zinc-400'>{recent[recent.length - 1]?.step?.content ?? 'Working…'}</p>
                  ) : (
                    <p className='text-[10px] text-zinc-600'>Awaiting first update…</p>
                  )}
                  {isLive && (
                    <div className='mt-2 flex gap-1'>
                      <input
                        value={draft[agent.sub_id] ?? ''}
                        onChange={(e) => setDraft((prev) => ({ ...prev, [agent.sub_id]: e.target.value }))}
                        placeholder='Message subagent…'
                        className='flex-1 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-[11px] text-zinc-200 outline-none'
                      />
                      <button
                        type='button'
                        onClick={() => {
                          const msg = (draft[agent.sub_id] ?? '').trim()
                          if (!msg) return
                          onMessage(agent.sub_id, msg)
                          setDraft((prev) => ({ ...prev, [agent.sub_id]: '' }))
                        }}
                        className='rounded-md bg-blue-600 px-2 py-1 text-[11px] text-white hover:bg-blue-500'
                      >
                        Send
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
