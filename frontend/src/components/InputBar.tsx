import { useEffect, useMemo, useRef, useState } from 'react'
import type { SteeringMode, TranscriptEntry } from '../hooks/useWebSocket'
import { apiUrl } from '../lib/api'
import { PROVIDERS, modelInfo, providerById, renderProviderIcon } from '../lib/models'
import { Icons } from './icons'
import { MessageQueue } from './MessageQueue'
import { PromptGallery } from './PromptGallery'
import { SuggestionChips } from './SuggestionChips'
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
  onDecomposePlan?: (prompt: string) => void
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

/* ── Arrow-up send icon ─────────────────────────────────────────────── */
function ArrowUpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox='0 0 24 24' fill='currentColor' className={className ?? 'h-4 w-4'} aria-hidden='true'>
      <path d='M12 4l-1.4 1.4 5.6 5.6H4v2h12.2l-5.6 5.6L12 20l8-8z' transform='rotate(-90 12 12)' />
    </svg>
  )
}

/* ── Provider + Model picker ────────────────────────────────────────── */
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
  const models = currentProvider.models

  return (
    <div className='flex min-w-0 items-center gap-1.5 overflow-hidden'>
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
      <label className='flex min-w-0 shrink items-center gap-1 rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'>
        <select
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          className='w-full min-w-0 max-w-[160px] rounded-sm bg-[#0f0f0f] px-1 py-0.5 text-xs text-zinc-100 outline-none'
          aria-label='Model'
        >
          {models.map((m) => (
            <option key={m.id} value={m.id} className='bg-[#0f0f0f] text-zinc-100'>
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
  onDecomposePlan,
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
  const [galleryOpen, setGalleryOpen] = useState(false)
  const [planMode, setPlanMode] = useState(false)
  const pendingExampleRef = useRef<string | null>(null)

  const effectiveValue = () => value.trim() || pendingExampleRef.current?.trim() || ''

  const submit = (overrideValue?: string) => {
    const raw = overrideValue ?? effectiveValue()
    if (!raw) return
    // Prepend /plan command when plan mode is active
    const instruction = planMode ? `/plan ${raw}` : raw
    if (planMode && onDecomposePlan) {
      onDecomposePlan(instruction)
    } else {
      onSend(instruction, mode)
    }
    if (!overrideValue) {
      setValue('')
      pendingExampleRef.current = null
    }
  }

  useEffect(() => {
    if (!examplePrompt) return
    const instruction = examplePrompt.trim()
    pendingExampleRef.current = instruction
    const timeout = window.setTimeout(() => {
      if (instruction) setValue(instruction)
      pendingExampleRef.current = null
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

  const modeStyling =
    mode === 'steer'
      ? 'border-blue-500/50 shadow-[0_0_30px_rgba(59,130,246,0.15)]'
      : mode === 'interrupt'
        ? 'border-orange-500/50'
        : 'border-[#2a2a2a]'

  const handleSuggestionSelect = async (templateId: string) => {
    try {
      const response = await fetch(apiUrl(`/api/gallery/${templateId}`), { credentials: 'include' })
      const data = await response.json()
      if (data?.ok && typeof data?.template?.prompt === 'string') setValue(data.template.prompt)
    } catch { /* silent */ }
  }

  const handleTemplateSelect = (prompt: string) => {
    setValue(prompt)
    setGalleryOpen(false)
  }

  const playTranscript = (text: string) => {
    if (!speechSupported) return
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
  }

  return (
    <section className={`space-y-2 rounded-xl border bg-[#1a1a1a] p-2 transition sm:space-y-3 sm:rounded-2xl sm:p-3 ${modeStyling}`}>
      {/* Top row: steering (when working) + model picker + voice */}
      <div className='flex flex-wrap items-center justify-between gap-1.5 sm:gap-2'>
        <div className='flex flex-wrap items-center gap-1.5 sm:gap-2'>
          {isWorking && (
            <SteeringControl mode={mode} queueCount={queuedMessages.length} onChange={onModeChange} />
          )}
          <div className='hidden sm:block'>
            <ModelPicker provider={provider} model={model} onProviderChange={onProviderChange} onModelChange={onModelChange} />
          </div>
        </div>
        <button
          type='button'
          onClick={onToggleVoice}
          disabled={voiceDisabled}
          aria-pressed={voiceActive}
          title={voiceButtonTitle}
          className={`rounded-md border border-[#2a2a2a] px-2 py-1.5 text-sm text-zinc-300 transition hover:bg-zinc-800 sm:px-3 sm:py-2 ${voiceActive ? 'animate-pulse border-blue-500/80 text-blue-200' : ''} ${voiceDisabled ? 'cursor-not-allowed opacity-60' : ''}`}
        >
          {Icons.mic({ className: 'h-4 w-4' })}
        </button>
      </div>

      {/* Model picker on mobile */}
      <div className='w-full overflow-hidden sm:hidden'>
        <ModelPicker provider={provider} model={model} onProviderChange={onProviderChange} onModelChange={onModelChange} />
      </div>

      <SuggestionChips onSelectSuggestion={(id) => void handleSuggestionSelect(id)} onOpenGallery={() => setGalleryOpen(true)} />

      {/* Main input row — matches Codex layout: [+] [Plan] [textarea] [↑] */}
      <div className='flex items-end gap-1.5 sm:gap-2'>
        {/* + button (future: attachment) */}
        <button
          type='button'
          title='Attach file (coming soon)'
          disabled
          className='flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#2a2a2a] text-zinc-500 cursor-not-allowed opacity-50 sm:h-10 sm:w-10'
        >
          <span className='text-lg font-light leading-none'>+</span>
        </button>

        {/* Plan toggle — inline, no popup */}
        {onDecomposePlan && (
          <button
            type='button'
            onClick={() => setPlanMode((p) => !p)}
            title={planMode ? 'Disable plan mode' : 'Enable plan mode — sends /plan command'}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide transition sm:px-4 sm:py-2 sm:text-sm ${
              planMode
                ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                : 'border-[#2a2a2a] text-zinc-400 hover:border-zinc-500 hover:text-zinc-200'
            }`}
          >
            Plan
          </button>
        )}

        {/* Textarea */}
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={1}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
            if (e.key === 'Escape') setValue('')
            if (e.key === 'Tab') {
              e.preventDefault()
              const idx = MODE_ORDER.indexOf(mode)
              onModeChange(MODE_ORDER[(idx + 1) % MODE_ORDER.length])
            }
          }}
          placeholder={planMode ? 'Describe a task to plan…' : 'Type an instruction…'}
          className='min-w-0 flex-1 resize-none rounded-2xl border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none ring-blue-500/60 placeholder:text-zinc-500 focus:ring-2'
        />

        {/* Arrow-up send button */}
        <button
          type='button'
          onClick={() => submit()}
          disabled={sending}
          title={planMode ? 'Send plan task' : 'Send'}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition sm:h-10 sm:w-10 ${
            planMode
              ? 'bg-blue-500 hover:bg-blue-400 text-white'
              : 'bg-white text-black hover:bg-zinc-200'
          } ${sending ? 'opacity-60 cursor-not-allowed' : ''}`}
        >
          {sending ? (
            <span className='inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent' />
          ) : (
            <svg viewBox='0 0 24 24' fill='currentColor' className='h-4 w-4' aria-hidden='true'>
              <path d='M12 20V7.83l5.59 5.59L19 12l-7-7-7 7 1.41 1.41L11 7.83V20h1z' />
            </svg>
          )}
        </button>
      </div>

      <p className='hidden text-xs text-zinc-600 sm:block'>Enter to send · Shift+Enter for newline · Esc to clear</p>

      {/* Transcripts */}
      {recentTranscripts.length > 0 && (
        <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-2 text-xs text-zinc-300'>
          <div className='mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-zinc-500'>
            <span>Transcript</span>
            <span>{speechSupported ? 'Playback ready' : 'Unavailable'}</span>
          </div>
          <div className='space-y-2'>
            {recentTranscripts.map((entry) => (
              <div key={entry.id} className='flex items-start justify-between gap-2 rounded-md border border-[#2a2a2a] bg-[#0f0f0f] px-2 py-1.5'>
                <div>
                  <p className='text-[11px] text-zinc-500'>{entry.timestamp}</p>
                  <p className='text-sm text-zinc-100'>{entry.text}</p>
                </div>
                <button type='button' onClick={() => playTranscript(entry.text)} disabled={!speechSupported} className={`rounded border border-[#2a2a2a] p-1 text-zinc-200 ${speechSupported ? 'hover:bg-zinc-800' : 'cursor-not-allowed opacity-50'}`} title='Play'>
                  {Icons.play({ className: 'h-4 w-4' })}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Queue */}
      {queuedMessages.length > 0 && (
        <MessageQueue queuedMessages={queuedMessages} isOpen={queueOpen} onToggle={() => setQueueOpen((p) => !p)} onDelete={onDeleteQueueItem} />
      )}

      {/* Prompt gallery modal */}
      {galleryOpen && (
        <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 sm:p-6'>
          <div className='h-[85vh] w-full max-w-6xl'>
            <PromptGallery onSelectTemplate={handleTemplateSelect} onClose={() => setGalleryOpen(false)} />
          </div>
        </div>
      )}
    </section>
  )
}
