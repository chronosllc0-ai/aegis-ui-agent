import { useState } from 'react'
import type { SteeringMode } from '../hooks/useWebSocket'
import { MessageQueue } from './MessageQueue'
import { SteeringControl } from './SteeringControl'

type InputBarProps = {
  mode: SteeringMode
  onModeChange: (mode: SteeringMode) => void
  onSend: (instruction: string, mode: SteeringMode) => void
  queuedMessages: string[]
  onDeleteQueueItem: (index: number) => void
}

export function InputBar({ mode, onModeChange, onSend, queuedMessages, onDeleteQueueItem }: InputBarProps) {
  const [value, setValue] = useState<string>('')
  const [queueOpen, setQueueOpen] = useState<boolean>(true)

  const submit = () => {
    const instruction = value.trim()
    if (!instruction) {
      return
    }
    onSend(instruction, mode)
    setValue('')
  }

  return (
    <section className='space-y-3 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='flex items-center justify-between'>
        <SteeringControl mode={mode} onChange={onModeChange} />
        <button type='button' className='rounded-md border border-[#2a2a2a] px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-800'>🎙️</button>
      </div>
      <div className='flex gap-2'>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit()
          }}
          placeholder='Type a new instruction, steer, interrupt, or queue next task...'
          className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none ring-blue-500/60 placeholder:text-zinc-500 focus:ring-2'
        />
        <button type='button' onClick={submit} className='rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400'>Send</button>
      </div>
      {queuedMessages.length > 0 && (
        <MessageQueue
          queuedMessages={queuedMessages}
          isOpen={queueOpen}
          onToggle={() => setQueueOpen((prev) => !prev)}
          onDelete={onDeleteQueueItem}
        />
      )}
    </section>
  )
}
