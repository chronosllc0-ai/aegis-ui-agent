/**
 * SubAgentPanel - "N background agents" pill above the input bar.
 *
 * Shows a compact pill when sub-agents are active. Clicking it opens a
 * slide-up drawer listing each sub-agent's live steps and status.
 */

import { useState } from 'react'
import type { SubAgentInfo, SubAgentStep } from '../hooks/useWebSocket'

interface SubAgentPanelProps {
  agents: SubAgentInfo[]
  steps: Record<string, SubAgentStep[]>
  onCancel: (sub_id: string) => void
  onMessage: (sub_id: string, message: string) => void
}

const STATUS_COLORS: Record<SubAgentInfo['status'], string> = {
  spawning: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  running: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  completed: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  failed: 'bg-red-500/20 text-red-300 border-red-500/30',
  cancelled: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30',
}

const STATUS_LABEL: Record<SubAgentInfo['status'], string> = {
  spawning: 'Starting',
  running: 'Running',
  completed: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

function SpinnerIcon() {
  return (
    <svg className='h-3 w-3 animate-spin text-blue-400' viewBox='0 0 24 24' fill='none'>
      <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
      <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z' />
    </svg>
  )
}

export function SubAgentPanel({ agents, steps, onCancel, onMessage }: SubAgentPanelProps) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [steerInput, setSteerInput] = useState('')

  const activeCount = agents.filter((a) => a.status === 'spawning' || a.status === 'running').length
  const totalCount = agents.length

  if (totalCount === 0) return null

  const selectedAgent = agents.find((a) => a.sub_id === selected) ?? agents[0]
  const selectedSteps = steps[selectedAgent?.sub_id ?? ''] ?? []

  function handleSteer(e: React.FormEvent) {
    e.preventDefault()
    if (!steerInput.trim() || !selectedAgent) return
    onMessage(selectedAgent.sub_id, steerInput.trim())
    setSteerInput('')
  }

  return (
    <>
      {/* ── Pill trigger ── */}
      <button
        type='button'
        onClick={() => setOpen(true)}
        className='flex items-center gap-2 rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-[#222] hover:text-zinc-100'
      >
        {activeCount > 0 && <SpinnerIcon />}
        {/* Agent count icon */}
        <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-3.5 w-3.5 text-zinc-400'>
          <path d='M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2' /><circle cx='9' cy='7' r='4' />
          <path d='M23 21v-2a4 4 0 0 0-3-3.87' /><path d='M16 3.13a4 4 0 0 1 0 7.75' />
        </svg>
        {activeCount > 0 ? (
          <span>{activeCount} background agent{activeCount !== 1 ? 's' : ''}</span>
        ) : (
          <span>{totalCount} agent{totalCount !== 1 ? 's' : ''} finished</span>
        )}
      </button>

      {/* ── Slide-up drawer backdrop ── */}
      {open && (
        <div
          className='fixed inset-0 z-40 bg-black/60'
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Slide-up drawer ── */}
      <div
        className={`fixed bottom-0 left-0 right-0 z-50 flex flex-col rounded-t-2xl border-t border-[#2a2a2a] bg-[#141414] transition-transform duration-300 ease-out ${open ? 'translate-y-0' : 'translate-y-full'}`}
        style={{ maxHeight: '70vh' }}
      >
        {/* Header */}
        <div className='flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3'>
          <div className='flex items-center gap-2'>
            <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4 text-zinc-400'>
              <path d='M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2' /><circle cx='9' cy='7' r='4' />
              <path d='M23 21v-2a4 4 0 0 0-3-3.87' /><path d='M16 3.13a4 4 0 0 1 0 7.75' />
            </svg>
            <span className='text-sm font-semibold text-zinc-200'>Background Agents</span>
          </div>
          <button type='button' onClick={() => setOpen(false)} className='rounded-lg p-1 text-zinc-500 hover:text-zinc-300'>
            <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round' className='h-4 w-4'>
              <path d='M18 6 6 18M6 6l12 12' />
            </svg>
          </button>
        </div>

        <div className='flex min-h-0 flex-1 overflow-hidden'>
          {/* Agent list sidebar */}
          <div className='flex w-48 shrink-0 flex-col gap-1 overflow-y-auto border-r border-[#2a2a2a] p-2'>
            {agents.map((agent) => (
              <button
                key={agent.sub_id}
                type='button'
                onClick={() => setSelected(agent.sub_id)}
                className={`rounded-lg px-2 py-2 text-left transition-colors ${selected === agent.sub_id || (!selected && agent === agents[0]) ? 'bg-[#2a2a2a]' : 'hover:bg-[#1e1e1e]'}`}
              >
                <div className='flex items-center gap-1.5'>
                  {(agent.status === 'spawning' || agent.status === 'running') && <SpinnerIcon />}
                  <span className='truncate text-xs font-medium text-zinc-200'>{agent.instruction.slice(0, 40)}{agent.instruction.length > 40 ? '…' : ''}</span>
                </div>
                <div className='mt-1 flex items-center gap-1.5'>
                  <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_COLORS[agent.status]}`}>
                    {STATUS_LABEL[agent.status]}
                  </span>
                  <span className='text-[10px] text-zinc-600'>{agent.step_count} step{agent.step_count !== 1 ? 's' : ''}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Step stream + steer input */}
          <div className='flex min-w-0 flex-1 flex-col'>
            {selectedAgent && (
              <>
                {/* Agent header */}
                <div className='flex items-center justify-between border-b border-[#2a2a2a] px-4 py-2'>
                  <div className='min-w-0 flex-1'>
                    <p className='truncate text-xs font-medium text-zinc-200'>{selectedAgent.instruction}</p>
                    <p className='text-[10px] text-zinc-500'>Model: {selectedAgent.model}</p>
                  </div>
                  {(selectedAgent.status === 'spawning' || selectedAgent.status === 'running') && (
                    <button
                      type='button'
                      onClick={() => onCancel(selectedAgent.sub_id)}
                      className='ml-3 rounded-lg border border-red-500/30 px-2 py-1 text-[11px] font-medium text-red-400 hover:bg-red-500/10 transition-colors'
                    >
                      Cancel
                    </button>
                  )}
                </div>

                {/* Steps */}
                <div className='flex-1 overflow-y-auto p-3 space-y-1.5'>
                  {selectedSteps.length === 0 ? (
                    <div className='flex items-center gap-2 text-xs text-zinc-600'>
                      {selectedAgent.status === 'spawning' ? (
                        <><SpinnerIcon /><span>Starting up…</span></>
                      ) : (
                        <span>No steps yet.</span>
                      )}
                    </div>
                  ) : (
                    selectedSteps.map((s, i) => (
                      <div key={i} className='flex items-start gap-2'>
                        <span className='mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[#2a2a2a] text-[9px] font-medium text-zinc-500'>
                          {s.step_index + 1}
                        </span>
                        <span className='text-xs text-zinc-400'>{s.step.content}</span>
                      </div>
                    ))
                  )}
                </div>

                {/* Steer input */}
                {(selectedAgent.status === 'spawning' || selectedAgent.status === 'running') && (
                  <form onSubmit={handleSteer} className='flex items-center gap-2 border-t border-[#2a2a2a] p-2'>
                    <input
                      value={steerInput}
                      onChange={(e) => setSteerInput(e.target.value)}
                      placeholder='Send a steering note…'
                      className='flex-1 rounded-lg bg-[#1e1e1e] px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:ring-1 focus:ring-[#3a3a3a]'
                    />
                    <button
                      type='submit'
                      disabled={!steerInput.trim()}
                      className='rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40 hover:bg-blue-500 transition-colors'
                    >
                      Send
                    </button>
                  </form>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
