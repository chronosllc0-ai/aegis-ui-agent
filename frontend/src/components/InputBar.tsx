import { useEffect, useMemo, useState } from 'react'
import type { SteeringMode, TranscriptEntry } from '../hooks/useWebSocket'
import type { CreditRates } from '../lib/creditRates'
import { estimateTypicalCredits, getTier, TIER_CONFIG } from '../lib/creditRates'
import { PROVIDERS, modelInfo, providerById, renderProviderIcon } from '../lib/models'
import { Icons } from './icons'
import { MessageQueue } from './MessageQueue'
import { SteeringControl } from './SteeringControl'

type InputBarProps = {
  mode: SteeringMode
  voiceActive: boolean
  voiceDisabled?: boolean
  voiceError?: string | null
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
  rates?: CreditRates | null
}

const MODE_ORDER: SteeringMode[] = ['steer', 'interrupt', 'queue']

/* ── Provider + Model picker (inline in the InputBar) ──────────────── */

function ModelPicker({
  provider,
  model,
  onProviderChange,
  onModelChange,
  rates,
}: {
  provider: string
  model: string
  onProviderChange: (id: string) => void
  onModelChange: (id: string) => void
  rates?: CreditRates | null
}) {
  const currentProvider = providerById(provider) ?? PROVIDERS[0]
  const currentModel = modelInfo(model)
  const models = currentProvider.models

  // Cost tier badge for the currently selected model
  const currentTier = rates ? getTier(rates, provider, model) : null
  const tierConfig = currentTier ? TIER_CONFIG[currentTier] : null
  const typicalCredits = rates ? estimateTypicalCredits(rates, provider, model) : null

  return (
    <div className='flex items-center gap-1.5'>
      {/* Provider selector */}
      <label className='flex items-center gap-1.5 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'>
        <span className='flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-xs'>
          {renderProviderIcon(currentProvider)}
        </span>
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value)}
          className='rounded-sm bg-[#0f0f0f] px-1 py-0.5 text-xs text-zinc-100 outline-none'
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
      <label className='flex items-center gap-1.5 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'>
        <select
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          title={currentModel?.description ?? model}
          className='max-w-[180px] rounded-sm bg-[#0f0f0f] px-1 py-0.5 text-xs text-zinc-100 outline-none'
          aria-label='Model'
        >
          {models.map((m) => {
            const t = rates ? getTier(rates, provider, m.id) : null
            const tc = t ? TIER_CONFIG[t] : null
            const cr = rates ? estimateTypicalCredits(rates, provider, m.id) : null
            const suffix = tc && cr != null ? ` · ${tc.label} ~${cr} cr` : ''
            return (
              <option key={m.id} value={m.id} title={m.description} className='bg-[#0f0f0f] text-zinc-100'>
                {m.label}{suffix}
              </option>
            )
          })}
        </select>
      </label>

      {/* Tier badge for current model */}
      {tierConfig && typicalCredits != null && (
        <span
          className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] ${tierConfig.bg} ${tierConfig.text}`}
          title={`${tierConfig.label} tier — ~${typicalCredits} credits per typical message`}
        >
          <span className='inline-block h-1.5 w-1.5 rounded-full' style={{ backgroundColor: tierConfig.color }} />
          ~{typicalCredits} cr
        </span>
      )}
    </div>
  )
}

export function InputBar({
  mode,
  voiceActive,
  voiceDisabled = false,
  voiceError = null,
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
  rates,
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
  if (voiceDisabled) voiceButtonTitle = 'Voice input unavailable'
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
    <section className={`space-y-3 rounded-2xl border bg-[#1a1a1a] p-3 transition ${modeStyling}`}>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex flex-wrap items-center gap-2'>
          <SteeringControl mode={mode} queueCount={queuedMessages.length} onChange={onModeChange} />
          <ModelPicker
            provider={provider}
            model={model}
            onProviderChange={onProviderChange}
            onModelChange={onModelChange}
            rates={rates}
          />
        </div>
        <button
          type='button'
          onClick={onToggleVoice}
          disabled={voiceDisabled}
          aria-pressed={voiceActive}
          title={voiceButtonTitle}
          className={`rounded-md border border-[#2a2a2a] px-3 py-2 text-sm text-zinc-300 transition hover:bg-zinc-800 ${voiceActive ? 'animate-pulse border-blue-500/80 text-blue-200' : ''} ${voiceDisabled ? 'cursor-not-allowed opacity-60' : ''}`}
          aria-label='Voice input'
        >
          {Icons.mic({ className: 'h-4 w-4' })}
        </button>
      </div>
      <div className='flex gap-2'>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={2}
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
          placeholder='Type a new instruction, steer, interrupt, or queue next task...'
          className='w-full resize-y rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none ring-blue-500/60 placeholder:text-zinc-500 focus:ring-2'
        />
        <button type='button' onClick={() => submit()} className='rounded-lg bg-blue-500 px-4 py-2 text-sm font-medium text-white hover:bg-blue-400'>
          {sending ? <span className='inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white' /> : 'Send'}
        </button>
      </div>
      <p className='text-xs text-zinc-500'>Enter to send - Esc to clear - Tab to switch mode - Shift+Enter for newline</p>
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
