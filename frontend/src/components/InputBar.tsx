import { useEffect, useState } from 'react'
import { useState } from 'react'
import type { SteeringMode } from '../hooks/useWebSocket'
import { MessageQueue } from './MessageQueue'
import { SteeringControl } from './SteeringControl'

type InputBarProps = {
  mode: SteeringMode
  voiceActive: boolean
  sending: boolean
  onModeChange: (mode: SteeringMode) => void
  onSend: (instruction: string, mode: SteeringMode) => void
  queuedMessages: string[]
  onDeleteQueueItem: (index: number) => void
  examplePrompt?: string | null
  onExampleHandled?: () => void
}

const MODE_ORDER: SteeringMode[] = ['steer', 'interrupt', 'queue']

export function InputBar({
  mode,
  voiceActive,
  sending,
  onModeChange,
  onSend,
  queuedMessages,
  onDeleteQueueItem,
  examplePrompt,
  onExampleHandled,
}: InputBarProps) {
  const [value, setValue] = useState<string>('')
  const [queueOpen, setQueueOpen] = useState<boolean>(true)

  const submit = (overrideValue?: string) => {
    const instruction = (overrideValue ?? value).trim()
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
    if (!overrideValue) {
      setValue('')
    }
  }



  useEffect(() => {
    if (!examplePrompt) {
      return
    }
    setValue(examplePrompt)
    onSend(examplePrompt, mode)
    setValue('')
    onExampleHandled?.()
  }, [examplePrompt, mode, onExampleHandled, onSend])

  const modeStyling =
    mode === 'steer'
      ? 'border-blue-500/50 shadow-[0_0_30px_rgba(59,130,246,0.15)]'
      : mode === 'interrupt'
        ? 'border-orange-500/50'
        : 'border-[#2a2a2a]'

  return (
    <section className={`space-y-3 rounded-xl border bg-[#1a1a1a] p-3 transition ${modeStyling}`}>
      <div className='flex items-center justify-between'>
        <SteeringControl mode={mode} queueCount={queuedMessages.length} onChange={onModeChange} />
        <button
          type='button'
          className={`rounded-md border border-[#2a2a2a] px-3 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800 ${voiceActive ? 'animate-pulse border-blue-500/80 text-blue-200' : ''}`}
        >
          🎙️
        </button>
      </div>
      <div className='flex gap-2'>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
            if (event.key === 'Escape') {
              setValue('')
            }
            if (event.key === 'Tab') {
              event.preventDefault()
              const idx = MODE_ORDER.indexOf(mode)
              onModeChange(MODE_ORDER[(idx + 1) % MODE_ORDER.length])
            }
          }}
          rows={2}
          placeholder='Type a new instruction, steer, interrupt, or queue next task...'
          className='w-full resize-y rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none ring-blue-500/60 placeholder:text-zinc-500 focus:ring-2'
        />
        <button type='button' onClick={() => submit()} className='rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400'>
          {sending ? <span className='inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white' /> : 'Send'}
        </button>
      </div>
      <p className='text-xs text-zinc-500'>Enter to send · Esc to clear · Tab to switch mode · Shift+Enter for newline</p>
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
