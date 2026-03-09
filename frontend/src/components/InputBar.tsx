import { useState } from 'react'
import type { SteeringMode } from '../hooks/useWebSocket'

type InputBarProps = {
  mode: SteeringMode
  sending: boolean
  onModeChange: (mode: SteeringMode) => void
  onSend: (instruction: string, mode: SteeringMode) => void
  queuedMessages: string[]
}

export function InputBar({ mode, sending, onModeChange, onSend, queuedMessages }: InputBarProps) {
  const [value, setValue] = useState('')

  const submit = () => {
    const instruction = value.trim()
    if (!instruction) return
    onSend(instruction, mode)
    setValue('')
  }

  return (
    <section className='space-y-3 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='flex items-center gap-2'>
        {(['steer', 'interrupt', 'queue'] as const).map((item) => (
          <button
            key={item}
            type='button'
            onClick={() => onModeChange(item)}
            className={`rounded px-3 py-1 text-xs capitalize ${mode === item ? 'bg-blue-500 text-white' : 'border border-[#2a2a2a] text-zinc-300'}`}
          >
            {item}
          </button>
        ))}
        <span className='ml-auto text-xs text-zinc-400'>Queued: {queuedMessages.length}</span>
      </div>
      <div className='flex gap-2'>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && submit()}
          className='w-full rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm'
          placeholder='Type a task or steering instruction...'
        />
        <button type='button' onClick={submit} className='rounded bg-blue-600 px-4 text-sm'>
          {sending ? '...' : 'Send'}
        </button>
      </div>
    </section>
  )
}
