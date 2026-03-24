import { useEffect, useMemo, useState } from 'react'
import type { SteeringMode, TranscriptEntry } from '../hooks/useWebSocket'
import { PROVIDERS, modelInfo, providerById, renderProviderIcon } from '../lib/models'
import { Icons } from './icons'
import { MessageQueue } from './MessageQueue'
import { SteeringControl } from './SteeringControl'

type InputBarProps = {
  mode: SteeringMode
  voiceActive: boolean
  voiceDisabled?: boolean
  voiceError?: string | null
  isConnected?: boolean
  isWorking?: boolean
  onToggleVoice: () => void
  sending: boolean
  onModeChange: (mode: SteeringMode) => void
  onSend: (instruction: string, mode: SteeringMode) => void
  provider: string
  model: string
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
  queuedMessages: string[]
  onDeleteQueueItem: (index: number) => void
  examplePrompt?: string | null
  onExampleHandled?: () => void
  transcripts?: TranscriptEntry[]
}

const MODE_ORDER: SteeringMode[] = ['steer', 'interrupt', 'queue']

/* ── Provider + Model picker (inline in the InputBar) ──────────────── */

function ModelPicker({
  provider,
  model,
  onProviderChange,
  onModelChange,
}: {
  provider: string
  model: string
  onProviderChange: (id: string) => void
  onModelChange: (id: string) => void
}) {
  const currentProvider = providerById(provider) ?? PROVIDERS[0]
  const currentModel = modelInfo(model)
  const models = currentProvider.models

  return (
    <div className='flex min-w-0 items-center gap-1.5 overflow-hidden'>
      {/* Provider selector */}
      <label className='flex min-w-0 shrink items-center gap-1 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'>
        <span className='flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-xs'>
          {renderProviderIcon(currentProvider)}
        </span>
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
          className='w-full min-w-0 max-w-[110px] rounded-sm bg-[#0f0f0f] px-1 py-0.5 text-xs text-zinc-100 outline-none'
          aria-label='Provider'
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id} className='bg-[#0f0f0f] text-zinc-100'>
              {p.displayName}
            </option>
          ))}
        </select>
      </label>

      {/* Model selector */}
      <label className='flex min-w-0 shrink items-center gap-1 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'>
        <select
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          title={currentModel?.description ?? model}
          className='w-full min-w-0 max-w-[160px] rounded-sm bg-[#0f0f0f] px-1 py-0.5 text-xs text-zinc-100 outline-none'
          aria-label='Model'
        >
          {models.map((m) => (
            <option key={m.id} value={m.id} title={m.description} className='bg-[#0f0f0f] text-zinc-100'>
              {m.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}

export function InputBar({
  mode,
  voiceActive,
  voiceDisabled = false,
  voiceError = null,
  isConnected = false,
  isWorking = false,
  onToggleVoice,
  sending,
  onModeChange,
  onSend,
  provider,
  model,
  onProviderChange,
  onModelChange,
  queuedMessages,
  onDeleteQueueItem,
  examplePrompt,
  onExampleHandled,
  transcripts = [],
}: InputBarProps) {
  const [value, setValue] = useState('')
  const [queueOpen, setQueueOpen] = useState(true)

  const submit = (overrideValue?: string) => {
    const instruction = (overrideValue ?? value).trim()
    if (!instruction) return
    onSend(instruction, mode)
    if (!overrideValue) setValue('')
  }

  useEffect(() => {
    if (!examplePrompt) return
    const instruction = examplePrompt.trim()
    const timeout = window.setTimeout(() => {
      if (instruction) setValue(instruction)
      onExampleHandled?.()
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [examplePrompt, onExampleHandled])

  const recentTranscripts = useMemo(() => transcripts.slice(-3).reverse(), [transcripts])
  const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window
  let voiceButtonTitle = 'Start voice input'
  if (voiceActive) voiceButtonTitle = 'Stop voice input'
  if (!isConnected) voiceButtonTitle = 'Connect to backend first'
  if (voiceDisabled && isConnected) voiceButtonTitle = 'Microphone requires HTTPS or localhost'
  if (voiceError) voiceButtonTitle = voiceError

  const playTranscript = (text: string) => {
    if (!speechSupported) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    window.speechSynthesis.speak(utterance)
  }

  const modeStyling =
    mode === 'steer'
      ? 'border-blue-500/50 shadow-[0_0_30px_rgba(59,130,246,0.15)]'
      : mode === 'interrupt'
        ? 'border-orange-500/50'
        : 'border-[#2a2a2a]'

  return (
    <section className={`space-y-2 rounded-xl border bg-[#1a1a1a] p-2 transition sm:space-y-3 sm:rounded-2xl sm:p-3 ${modeStyling}`}>
      <div className='flex flex-wrap items-center justify-between gap-1.5 sm:gap-2'>
        <div className='flex flex-wrap items-center gap-1.5 sm:gap-2'>
          {/* Steering bar: only visible when agent is actively working */}
          {isWorking && (
            <SteeringControl mode={mode} queueCount={queuedMessages.length} onChange={onModeChange} />
          )}
          <div className='hidden sm:block'>
            <ModelPicker
              provider={provider}
              model={model}
              onProviderChange={onProviderChange}
              onModelChange={onModelChange}
            />
          </div>
        </div>
        <button
          type='button'
          onClick={onToggleVoice}
          disabled={voiceDisabled}
          aria-pressed={voiceActive}
          title={voiceButtonTitle}
          className={`rounded-md border border-[#2a2a2a] px-2 py-1.5 text-sm text-zinc-300 transition hover:bg-zinc-800 sm:px-3 sm:py-2 ${voiceActive ? 'animate-pulse border-blue-500/80 text-blue-200' : ''} ${voiceDisabled ? 'cursor-not-allowed opacity-60' : ''}`}
          aria-label='Voice input'
        >
          {Icons.mic({ className: 'h-4 w-4' })}
        </button>
      </div>
      {/* Model picker shown below controls on mobile */}
      <div className='w-full overflow-hidden sm:hidden'>
        <ModelPicker
          provider={provider}
          model={model}
          onProviderChange={onProviderChange}
          onModelChange={onModelChange}
        />
      </div>
      <div className='flex gap-1.5 sm:gap-2'>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={1}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
            if (event.key === 'Escape') setValue('')
            if (event.key === 'Tab') {
              event.preventDefault()
              const idx = MODE_ORDER.indexOf(mode)
              onModeChange(MODE_ORDER[(idx + 1) % MODE_ORDER.length])
            }
          }}
          placeholder='Type an instruction...'
          className='w-full resize-y rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1.5 text-xs text-zinc-100 outline-none ring-blue-500/60 placeholder:text-zinc-500 focus:ring-2 sm:px-3 sm:py-2 sm:text-sm'
        />
        <button type='button' onClick={() => submit()} className='rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-400 sm:px-4 sm:py-2 sm:text-sm'>
          {sending ? <span className='inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white' /> : 'Send'}
        </button>
      </div>
      <p className='hidden text-xs text-zinc-500 sm:block'>Enter to send - Esc to clear - Tab to switch mode - Shift+Enter for newline</p>
      {recentTranscripts.length > 0 && (
        <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-2 text-xs text-zinc-300'>
          <div className='mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-zinc-500'>
            <span>Transcript</span>
            <span>{speechSupported ? 'Playback ready' : 'Playback unsupported'}</span>
          </div>
          <div className='space-y-2'>
            {recentTranscripts.map((entry) => (
              <div key={entry.id} className='flex items-start justify-between gap-2 rounded-md border border-[#2a2a2a] bg-[#0f0f0f] px-2 py-1.5'>
                <div>
                  <p className='text-[11px] text-zinc-500'>{entry.timestamp}</p>
                  <p className='text-sm text-zinc-100'>{entry.text}</p>
                </div>
                <button
                  type='button'
                  onClick={() => playTranscript(entry.text)}
                  disabled={!speechSupported}
                  className={`rounded border border-[#2a2a2a] p-1 text-zinc-200 ${speechSupported ? 'hover:bg-zinc-800' : 'cursor-not-allowed opacity-50'}`}
                  title={speechSupported ? 'Play transcript' : 'Speech synthesis unavailable'}
                >
                  {Icons.play({ className: 'h-4 w-4' })}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {queuedMessages.length > 0 && (
        <MessageQueue queuedMessages={queuedMessages} isOpen={queueOpen} onToggle={() => setQueueOpen((prev) => !prev)} onDelete={onDeleteQueueItem} />
      )}
    </section>
  )
}
