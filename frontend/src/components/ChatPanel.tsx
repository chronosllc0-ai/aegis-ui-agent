import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { LogEntry, SteeringMode } from '../hooks/useWebSocket'
import type { ServerMessage } from '../hooks/useConversations'
import { Icons } from './icons'
import { apiUrl } from '../lib/api'

// Inline SVG primitives — avoids react-icons subpath d.ts resolution issues with tsc bundler mode
type SvgProps = { className?: string }
function Svg({ className, children }: SvgProps & { children: ReactNode }) {
  return (
    <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8'
      strokeLinecap='round' strokeLinejoin='round'
      className={className ?? 'h-4 w-4'} aria-hidden='true'>
      {children}
    </svg>
  )
}
const IcoGlobe        = (p: SvgProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18' /></Svg>
const IcoMessage      = (p: SvgProps) => <Svg {...p}><path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' /></Svg>
const IcoPaperclip    = (p: SvgProps) => <Svg {...p}><path d='m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48' /></Svg>
const IcoSend         = (p: SvgProps) => <Svg {...p}><path d='m22 2-7 20-4-9-9-4z' /><path d='M22 2 11 13' /></Svg>
const IcoMic          = (p: SvgProps) => <Svg {...p}><rect x='9' y='3' width='6' height='11' rx='3' /><path d='M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6' /></Svg>
const IcoCopy         = (p: SvgProps) => <Svg {...p}><rect x='9' y='9' width='11' height='11' rx='2' /><rect x='4' y='4' width='11' height='11' rx='2' /></Svg>
const IcoCheck        = (p: SvgProps) => <Svg {...p}><path d='m5 12 4 4 10-10' /></Svg>
const IcoX            = (p: SvgProps) => <Svg {...p}><path d='M18 6 6 18M6 6l12 12' /></Svg>
const IcoChevronDown  = (p: SvgProps) => <Svg {...p}><path d='m6 9 6 6 6-6' /></Svg>
const IcoSearch       = (p: SvgProps) => <Svg {...p}><circle cx='11' cy='11' r='6' /><path d='m20 20-3.5-3.5' /></Svg>
const IcoFile         = (p: SvgProps) => <Svg {...p}><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' /><path d='M14 2v6h6' /></Svg>
const IcoCode         = (p: SvgProps) => <Svg {...p}><path d='m16 18 6-6-6-6M8 6l-6 6 6 6' /></Svg>
const IcoBrain        = (p: SvgProps) => <Svg {...p}><path d='M9 3a3 3 0 0 0-3 3 3 3 0 0 0-3 3 4 4 0 0 0 4 4v3a3 3 0 0 0 6 0v-3a4 4 0 0 0 4-4 3 3 0 0 0-3-3 3 3 0 0 0-5 0Z' /></Svg>

export interface ChatPanelProps {
  logs: LogEntry[]
  isWorking: boolean
  onSend: (instruction: string, mode: SteeringMode) => void
  onDecomposePlan: (prompt: string) => void
  connectionStatus: 'connecting' | 'connected' | 'disconnected'
  transcripts: string[]
  onSwitchToBrowser: () => void
  latestFrame: string | null
  /** Whether the Gemini Live mic stream is active (passed from App) */
  voiceActive?: boolean
  /** Toggle Gemini Live mic (passed from App) */
  onToggleVoice?: () => void
  /** True when mic hardware isn't available / not HTTPS */
  voiceDisabled?: boolean
  /** Currently selected task ID — used to persist/restore conversation */
  activeTaskId?: string | null
  /** Messages loaded from the server DB for the selected conversation */
  serverMessages?: ServerMessage[]
  /** Called when user clicks Stop to kill the running task */
  onStop?: () => void
}

// ─── Message shape ────────────────────────────────────────────────────────────
type ChatRole = 'user' | 'assistant' | 'tool' | 'approval' | 'subagent' | 'generating'

interface ChatMessage {
  id: string
  role: ChatRole
  text: string
  timestamp: string
  toolName?: string
  toolArgs?: string
  toolStatus?: 'in_progress' | 'completed' | 'failed'
  approvalId?: string
  planSteps?: string[]
  attachments?: AttachedFile[]
}

interface AttachedFile {
  name: string
  type: string
  dataUrl: string
}

// ─── Live connector type (mirrors ConnectorsTab.tsx) ─────────────────────────
interface ConnectorMeta {
  id: string
  name: string
  icon: string   // URL
  connected: boolean
  status: string
}

// ─── Generation canvas: animated placeholder while media is being created ────
function GeneratingCanvas({ label }: { label: string }) {
  return (
    <div className='my-2 overflow-hidden rounded-2xl border border-[#2a2a2a] bg-[#0d0d0d]'>
      <div className='relative h-48 w-full overflow-hidden'>
        {/* Animated gradient blobs mimicking ChatGPT image generation shimmer */}
        <div className='absolute inset-0 animate-pulse bg-gradient-to-br from-[#1a1020] via-[#1e1530] to-[#0d1020]' />
        <div className='absolute left-1/4 top-1/4 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-900/30 blur-3xl animate-[pulse_2s_ease-in-out_infinite]' />
        <div className='absolute right-1/4 bottom-1/4 h-24 w-24 translate-x-1/2 translate-y-1/2 rounded-full bg-blue-900/20 blur-3xl animate-[pulse_2.5s_ease-in-out_infinite_0.5s]' />
        <div className='absolute inset-0 flex flex-col items-center justify-center gap-2'>
          <div className='flex gap-1'>
            <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '0ms' }} />
            <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '150ms' }} />
            <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '300ms' }} />
          </div>
          <p className='text-xs text-zinc-500'>{label}</p>
        </div>
      </div>
    </div>
  )
}

// ─── Parse logs → chat messages ──────────────────────────────────────────────
function logsToMessages(logs: LogEntry[]): ChatMessage[] {
  return logs.map((entry) => {
    const isUser = entry.stepKind === 'navigate' && entry.elapsedSeconds === 0
    const isTool = entry.type === 'step' && !isUser
    const isError = entry.type === 'error'
    const isResult = entry.type === 'result'
    const isGenerating = (
      entry.type === 'step' &&
      typeof entry.message === 'string' &&
      /\b(generating|creating image|creating video|rendering|synthesizing)\b/i.test(entry.message)
    )

    if (isGenerating) {
      return {
        id: entry.id,
        role: 'generating' as ChatRole,
        text: entry.message,
        timestamp: entry.timestamp,
      }
    }
    if (isUser) {
      return {
        id: entry.id,
        role: 'user' as ChatRole,
        text: entry.message,
        timestamp: entry.timestamp,
      }
    }
    if (isTool) {
      return {
        id: entry.id,
        role: 'tool' as ChatRole,
        text: entry.message,
        toolName: entry.stepKind,
        toolStatus: entry.status === 'failed' ? 'failed' : entry.status === 'completed' ? 'completed' : 'in_progress',
        timestamp: entry.timestamp,
      }
    }
    if (isError) {
      return {
        id: entry.id,
        role: 'assistant' as ChatRole,
        text: `⚠️ ${entry.message}`,
        timestamp: entry.timestamp,
      }
    }
    if (isResult) {
      return {
        id: entry.id,
        role: 'assistant' as ChatRole,
        text: entry.message,
        timestamp: entry.timestamp,
      }
    }
    return {
      id: entry.id,
      role: 'assistant' as ChatRole,
      text: entry.message,
      timestamp: entry.timestamp,
    }
  })
}

// ─── Code block parser ────────────────────────────────────────────────────────
function parseCodeBlocks(text: string): Array<{ type: 'text' | 'code'; content: string; lang?: string }> {
  const parts: Array<{ type: 'text' | 'code'; content: string; lang?: string }> = []
  const regex = /```(\w*)\n?([\s\S]*?)```/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', content: text.slice(lastIndex, match.index) })
    }
    parts.push({ type: 'code', content: match[2].trim(), lang: match[1] || 'text' })
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    parts.push({ type: 'text', content: text.slice(lastIndex) })
  }
  return parts
}

// ─── Code card ────────────────────────────────────────────────────────────────
function CodeCard({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  return (
    <div className='my-2 rounded-xl border border-[#2a2a2a] bg-[#0d0d0d] overflow-hidden'>
      <div className='flex items-center justify-between px-3 py-1.5 border-b border-[#2a2a2a]'>
        <span className='text-[10px] font-mono font-medium text-zinc-500 uppercase tracking-wider'>{lang}</span>
        <div className='flex items-center gap-1.5'>
          <button
            type='button'
            onClick={copy}
            className='flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors'
          >
            {copied ? <IcoCheck className='h-3 w-3' /> : <IcoCopy className='h-3 w-3' />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <div className='relative'>
            <button
              type='button'
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              className='flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-zinc-600 cursor-not-allowed'
              disabled
            >
              <IcoCode className='h-3 w-3' />
              Run
            </button>
            {showTooltip && (
              <div className='absolute bottom-full right-0 mb-1.5 z-50 whitespace-nowrap rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-2.5 py-1.5 text-[10px] text-zinc-400 shadow-xl'>
                E2B Sandbox — coming soon
              </div>
            )}
          </div>
        </div>
      </div>
      <pre className='overflow-x-auto p-3 text-xs leading-5 text-zinc-200 font-mono'>{code}</pre>
    </div>
  )
}

// ─── Tool step icon map ───────────────────────────────────────────────────────
const TOOL_ICON: Record<string, React.ReactNode> = {
  analyze:  <Icons.search className='h-3.5 w-3.5' />,
  click:    <Icons.chevronRight className='h-3.5 w-3.5' />,
  type:     <Icons.edit className='h-3.5 w-3.5' />,
  scroll:   <Icons.chevronDown className='h-3.5 w-3.5' />,
  navigate: <Icons.globe className='h-3.5 w-3.5' />,
  other:    <Icons.workflows className='h-3.5 w-3.5' />,
}

const STATUS_BADGE: Record<string, string> = {
  in_progress: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  completed:   'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  failed:      'bg-red-500/15 text-red-300 border-red-500/30',
}

// ─── Individual message renderers ────────────────────────────────────────────
function UserBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className='flex justify-end mb-2'>
      <div className='max-w-[75%]'>
        {msg.attachments?.map((att) => (
          <div key={att.name} className='mb-1.5'>
            {att.type.startsWith('image/') ? (
              <img src={att.dataUrl} alt={att.name} className='rounded-lg max-h-40 object-cover border border-[#2a2a2a]' />
            ) : (
              <div className='flex items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2 text-xs md:text-sm text-zinc-300'>
                <IcoFile className='h-4 w-4 flex-shrink-0' />
                {att.name}
              </div>
            )}
          </div>
        ))}
        <div className='rounded-2xl rounded-tr-sm bg-blue-600 px-3.5 py-2.5 text-sm md:text-base text-white shadow-md'>
          {msg.text}
        </div>
        <p className='mt-0.5 text-right text-[10px] text-zinc-600'>{msg.timestamp}</p>
      </div>
    </div>
  )
}

function AssistantCard({ msg }: { msg: ChatMessage }) {
  const parts = useMemo(() => parseCodeBlocks(msg.text), [msg.text])
  return (
    <div className='flex gap-2.5 mb-2 max-w-[85%]'>
      <div className='mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[#2a2a2a]'>
        <IcoBrain className='h-3.5 w-3.5 text-zinc-300' />
      </div>
      <div className='min-w-0 flex-1'>
        <div className='rounded-2xl rounded-tl-sm border border-[#2a2a2a] bg-[#1a1a1a] px-3.5 py-2.5 text-sm md:text-base text-zinc-200 shadow-md'>
          {parts.map((part, i) =>
            part.type === 'code' ? (
              <CodeCard key={i} code={part.content} lang={part.lang ?? 'text'} />
            ) : (
              <span key={i} className='whitespace-pre-wrap'>{part.content}</span>
            )
          )}
        </div>
        <p className='mt-0.5 text-[10px] text-zinc-600'>{msg.timestamp}</p>
      </div>
    </div>
  )
}

function ToolCard({ msg }: { msg: ChatMessage }) {
  const [expanded, setExpanded] = useState(false)
  const icon = TOOL_ICON[msg.toolName ?? 'other'] ?? TOOL_ICON.other
  const badge = STATUS_BADGE[msg.toolStatus ?? 'in_progress']

  return (
    <div className='flex gap-2.5 mb-1.5'>
      <div className='mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-[#2a2a2a] bg-[#1a1a1a] text-zinc-400'>
        {icon}
      </div>
      <div className='min-w-0 flex-1'>
        <button
          type='button'
          onClick={() => setExpanded((v) => !v)}
          className='w-full rounded-xl border border-[#2a2a2a] bg-[#141414] px-3 py-2 text-left hover:bg-[#1a1a1a] transition-colors'
        >
          <div className='flex items-center justify-between gap-2'>
            <span className='truncate text-xs md:text-sm font-medium text-zinc-300'>{msg.text}</span>
            <div className='flex items-center gap-1.5 flex-shrink-0'>
              <span className={`rounded border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide ${badge}`}>
                {msg.toolStatus ?? 'running'}
              </span>
              <IcoChevronDown className={`h-3 w-3 text-zinc-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </div>
          </div>
          {expanded && msg.toolArgs && (
            <pre className='mt-2 overflow-x-auto rounded-lg bg-[#0d0d0d] p-2 text-[10px] text-zinc-400 font-mono'>
              {msg.toolArgs}
            </pre>
          )}
        </button>
        <p className='mt-0.5 ml-1 text-[10px] text-zinc-600'>{msg.timestamp}</p>
      </div>
    </div>
  )
}

function ApprovalCard({ msg, onApprove, onReject }: { msg: ChatMessage; onApprove: () => void; onReject: () => void }) {
  return (
    <div className='my-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4'>
      <p className='mb-1 text-xs font-semibold text-amber-300 uppercase tracking-wide'>Approval Required</p>
      <p className='mb-4 text-sm text-zinc-200'>{msg.text}</p>
      <div className='flex gap-2'>
        <button
          type='button'
          onClick={onApprove}
          className='flex-1 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 transition-colors'
        >
          Approve
        </button>
        <button
          type='button'
          onClick={onReject}
          className='flex-1 rounded-xl bg-red-600/20 border border-red-500/40 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-600/30 transition-colors'
        >
          Reject
        </button>
      </div>
    </div>
  )
}

function SubagentCard({ msg }: { msg: ChatMessage }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div className='my-3 rounded-2xl border border-violet-500/30 bg-violet-500/5 p-4 relative'>
      <button
        type='button'
        onClick={() => setDismissed(true)}
        className='absolute right-3 top-3 rounded-md p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'
      >
        <IcoX className='h-3.5 w-3.5' />
      </button>
      <div className='flex items-center gap-3 mb-3'>
        <div className='relative h-8 w-8 flex-shrink-0'>
          {/* Neural-network spinner */}
          <div className='absolute inset-0 rounded-full border-2 border-violet-500/30 animate-spin' style={{ animationDuration: '3s' }} />
          <div className='absolute inset-1 rounded-full border border-violet-400/50 animate-spin' style={{ animationDuration: '2s', animationDirection: 'reverse' }} />
          <IcoBrain className='absolute inset-0 m-auto h-3.5 w-3.5 text-violet-300' />
        </div>
        <div>
          <p className='text-sm font-semibold text-violet-300'>Aegis is orchestrating sub-agents…</p>
          <p className='text-xs text-zinc-500'>{msg.text}</p>
        </div>
      </div>
      {msg.planSteps && msg.planSteps.length > 0 && (
        <div className='space-y-1'>
          {msg.planSteps.map((step, i) => (
            <div key={i} className='flex items-center gap-2 text-xs text-zinc-400'>
              <div className='h-1.5 w-1.5 rounded-full bg-violet-500 animate-pulse' />
              {step}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Plus-menu modal (ChatGPT-style bottom sheet) ────────────────────────────
interface PlusMenuProps {
  onAttach: (accept: string, capture?: string) => void
  onConnector: (connector: ConnectorMeta) => void
  onClose: () => void
}

function PlusMenu({ onAttach, onConnector, onClose }: PlusMenuProps) {
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([])
  const [query, setQuery] = useState('')

  // Fetch live connectors from settings API
  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/connectors'), { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled && data.ok) setConnectors(data.connectors as ConnectorMeta[])
      })
      .catch(() => { /* silently ignore if not authed */ })
    return () => { cancelled = true }
  }, [])

  const filteredConnectors = connectors.filter((c) =>
    c.name.toLowerCase().includes(query.toLowerCase())
  )

  // Attachment rows (top section)
  const attachRows = [
    { id: 'camera',  label: 'Camera',  accept: 'image/*', capture: 'environment', icon: (
      <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
        <Svg className='h-5 w-5 text-zinc-200'><path d='M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z'/><circle cx='12' cy='13' r='4'/></Svg>
      </div>
    )},
    { id: 'photos',  label: 'Photos',  accept: 'image/*', capture: undefined, icon: (
      <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
        <Svg className='h-5 w-5 text-zinc-200'><rect x='3' y='3' width='18' height='18' rx='2'/><circle cx='8.5' cy='8.5' r='1.5'/><path d='M21 15l-5-5L5 21'/></Svg>
      </div>
    )},
    { id: 'files',   label: 'Files',   accept: '*/*', capture: undefined, icon: (
      <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
        <IcoPaperclip className='h-5 w-5 text-zinc-200' />
      </div>
    )},
    { id: 'videos',  label: 'Videos',  accept: 'video/*', capture: undefined, icon: (
      <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
        <Svg className='h-5 w-5 text-zinc-200'><polygon points='23 7 16 12 23 17 23 7'/><rect x='1' y='5' width='15' height='14' rx='2'/></Svg>
      </div>
    )},
  ]

  return (
    <>
      {/* Backdrop */}
      <div className='fixed inset-0 z-40 bg-black/60' onClick={onClose} />

      {/* Bottom sheet on mobile, floating panel on desktop */}
      <div className='fixed bottom-0 left-0 right-0 z-50 rounded-t-3xl bg-[#1c1c1c] pb-safe shadow-2xl sm:absolute sm:bottom-full sm:left-0 sm:mb-2 sm:rounded-2xl sm:w-72 sm:pb-0'>
        {/* Drag handle (mobile) */}
        <div className='flex justify-center pt-2 pb-1 sm:hidden'>
          <div className='h-1 w-10 rounded-full bg-zinc-700' />
        </div>

        {/* Attachment section */}
        <div className='px-1 pt-2'>
          {attachRows.map((row) => (
            <button
              key={row.id}
              type='button'
              onClick={() => { onAttach(row.accept, row.capture); onClose() }}
              className='flex w-full items-center gap-4 rounded-xl px-3 py-2.5 text-left hover:bg-[#2a2a2a] transition-colors'
            >
              {row.icon}
              <span className='text-sm font-medium text-zinc-200'>{row.label}</span>
            </button>
          ))}
        </div>

        {/* Divider + connectors section */}
        {connectors.length > 0 && (
          <>
            <div className='mx-4 my-2 border-t border-[#2a2a2a]' />
            <div className='px-3 pb-1'>
              <div className='mb-2 flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#111] px-3 py-1.5'>
                <IcoSearch className='h-3.5 w-3.5 flex-shrink-0 text-zinc-500' />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder='Search connectors…'
                  className='flex-1 bg-transparent text-xs text-zinc-300 outline-none placeholder:text-zinc-600'
                />
              </div>
              <div className='max-h-40 overflow-y-auto'>
                {filteredConnectors.map((conn) => (
                  <button
                    key={conn.id}
                    type='button'
                    onClick={() => { onConnector(conn); onClose() }}
                    className='flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left hover:bg-[#2a2a2a] transition-colors'
                  >
                    <div className='flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#2a2a2a]'>
                      <img src={conn.icon} alt={conn.name} className='h-5 w-5 rounded object-contain' onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                    </div>
                    <div className='min-w-0 flex-1'>
                      <span className='block truncate text-sm font-medium text-zinc-200'>{conn.name}</span>
                    </div>
                    {conn.connected && conn.status === 'active' && (
                      <span className='h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0' />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
        <div className='h-3 sm:h-2' />
      </div>
    </>
  )
}

// ─── Main ChatPanel ───────────────────────────────────────────────────────────
export function ChatPanel({
  logs,
  isWorking,
  onSend,
  onDecomposePlan,
  connectionStatus,
  onSwitchToBrowser,
  latestFrame,
  transcripts = [],
  voiceActive = false,
  onToggleVoice,
  voiceDisabled = false,
  activeTaskId,
  serverMessages = [],
  onStop,
}: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<AttachedFile[]>([])

  // ── Conversation persistence ─────────────────────────────────────────────────
  // Source of truth is the server DB (conversations / conversation_messages tables).
  // serverMessages prop is fetched by App.tsx via useConversations and passed here.
  // localStorage is kept only as a write-through display cache for the current session.
  const CHAT_KEY = (id: string) => `aegis.chat.${id}`
  const saveMsgs = (id: string | null | undefined, msgs: ChatMessage[]) => {
    if (!id) return
    try { localStorage.setItem(CHAT_KEY(id), JSON.stringify(msgs.slice(-200))) } catch { /* quota */ }
  }

  // sentMessages = messages shown in the UI (seeded from serverMessages on load,
  // extended optimistically as user sends).
  const [sentMessages, setSentMessages] = useState<ChatMessage[]>([])

  // When task changes or server messages arrive, rebuild from server data
  const prevTaskIdRef = useRef(activeTaskId)
  const prevServerLenRef = useRef(0)
  useEffect(() => {
    const taskChanged = prevTaskIdRef.current !== activeTaskId
    const serverArrived = prevServerLenRef.current === 0 && serverMessages.length > 0
    prevTaskIdRef.current = activeTaskId
    prevServerLenRef.current = serverMessages.length
    if (!taskChanged && !serverArrived) return
    if (serverMessages.length > 0) {
      setSentMessages(
        serverMessages.map((m) => ({
          id: m.id,
          role: (m.role === 'user' ? 'user' : 'assistant') as ChatRole,
          text: m.content,
          timestamp: m.created_at ? new Date(m.created_at).toLocaleTimeString() : new Date().toLocaleTimeString(),
        }))
      )
    } else if (taskChanged) {
      setSentMessages([])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTaskId, serverMessages.length])

  const [activeConnector, setActiveConnector] = useState<ConnectorMeta | null>(null)
  const [showPlusMenu, setShowPlusMenu] = useState(false)
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set())
  const [rejectedIds, setRejectedIds] = useState<Set<string>>(new Set())

  // ── Browser SpeechRecognition fallback ──────────────────────────────────────
  // Web Speech API types aren't in our tsconfig lib, so we use unknown casts.
  type AnySR = { continuous: boolean; interimResults: boolean; lang: string; start(): void; stop(): void; onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null }
  const srRef = useRef<AnySR | null>(null)
  const [srActive, setSrActive] = useState(false)

  const geminiLiveAvailable = connectionStatus === 'connected' && !voiceDisabled

  // Inject latest Gemini Live transcript into input when it arrives
  const prevTranscriptLen = useRef(transcripts.length)
  useEffect(() => {
    if (transcripts.length > prevTranscriptLen.current) {
      const latest = transcripts[transcripts.length - 1]
      if (latest) setInput((prev) => (prev ? `${prev} ${latest}` : latest))
    }
    prevTranscriptLen.current = transcripts.length
  }, [transcripts])

  const getSRCtor = (): (new () => AnySR) | null => {
    if (typeof window === 'undefined') return null
    const w = window as unknown as Record<string, unknown>
    return (w['SpeechRecognition'] ?? w['webkitSpeechRecognition'] ?? null) as (new () => AnySR) | null
  }

  const handleMicClick = useCallback(() => {
    if (geminiLiveAvailable && onToggleVoice) {
      // Primary: Gemini Live via WebSocket
      onToggleVoice()
      return
    }
    // Fallback: browser SpeechRecognition
    const SR = getSRCtor()
    if (!SR) return
    if (srActive && srRef.current) {
      srRef.current.stop()
      return
    }
    const sr = new SR()
    sr.continuous = false
    sr.interimResults = false
    sr.lang = 'en-US'
    sr.onresult = (e) => {
      const text = (e.results[0]?.[0]?.transcript as string | undefined) ?? ''
      if (text) setInput((prev) => (prev ? `${prev} ${text}` : text))
    }
    sr.onend = () => setSrActive(false)
    sr.onerror = () => setSrActive(false)
    srRef.current = sr
    setSrActive(true)
    sr.start()
  }, [geminiLiveAvailable, onToggleVoice, srActive])

  // Determine which mic state is visually "active"
  const micIsActive = voiceActive || srActive
  // Mic is available if Gemini Live path works OR browser SR exists
  const micAvailable = !voiceDisabled && (
    geminiLiveAvailable || !!getSRCtor()
  )

  const micTitle = micIsActive
    ? (voiceActive ? 'Stop Gemini Live voice input' : 'Stop recording')
    : voiceDisabled
      ? 'Microphone requires HTTPS or localhost'
      : geminiLiveAvailable
        ? 'Start Gemini 2.0 Flash Live voice input'
        : 'Start voice input (browser fallback)'

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Derive non-user messages from logs.
  // User messages are intentionally excluded here: they live in sentMessages so that
  // attachment data (never present in logs) is preserved. Logs *could* theoretically
  // produce a user-role entry (isUser heuristic) but that's filtered out to avoid
  // showing a duplicate plain-text bubble alongside the local bubble with attachments.
  const baseMessages = useMemo(() => logsToMessages(logs).filter((m) => m.role !== 'user'), [logs])

  // Prune sentMessages when logs grow to avoid unbounded memory: keep only the last
  // 500 sent messages (roughly one long session). Called in effect below.
  useEffect(() => {
    if (sentMessages.length > 500) {
      setSentMessages((prev) => prev.slice(-500))
    }
  }, [sentMessages.length])

  // Merge local sent messages + log-derived messages (agent responses).
  // sentMessages are prepended: they were sent before the agent responded.
  const allMessages = useMemo(() => {
    return [...sentMessages, ...baseMessages]
  }, [sentMessages, baseMessages])

  // Persist the full conversation (sent + agent responses) whenever it grows
  useEffect(() => {
    if (allMessages.length > 0) saveMsgs(activeTaskId, allMessages)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allMessages.length, activeTaskId])

  // Show browsing-pill when agent is working but we're on chat side
  const showBrowsePill = isWorking && latestFrame

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [allMessages.length])

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const maxHeight = 6 * 24 // ~6 lines
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
  }, [])

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    resizeTextarea()
  }

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed && attachments.length === 0) return
    // Prepend connector context if active
    const withContext = activeConnector ? `[${activeConnector.name}] ${trimmed}` : trimmed
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    // Save locally so attachments appear in chat immediately (logs never carry file data)
    const localMsg: ChatMessage = {
      id: `local-${crypto.randomUUID()}`,
      role: 'user',
      text: withContext || '(attachment)',
      timestamp: now,
      attachments: attachments.length > 0 ? [...attachments] : undefined,
    }
    setSentMessages((prev) => {
      const next = [...prev, localMsg]
      saveMsgs(activeTaskId, next)
      return next
    })
    if (withContext.startsWith('/plan ')) {
      onDecomposePlan(withContext.slice(6))
    } else {
      onSend(withContext || '(attachment)', 'steer')
    }
    setInput('')
    setAttachments([])
    setActiveConnector(null)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleConnectorSelect = (connector: ConnectorMeta) => {
    setActiveConnector(connector)
    window.setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const handleAttach = (accept: string, capture?: string) => {
    if (!fileInputRef.current) return
    fileInputRef.current.accept = accept
    if (capture) {
      fileInputRef.current.setAttribute('capture', capture)
    } else {
      fileInputRef.current.removeAttribute('capture')
    }
    fileInputRef.current.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    files.forEach((file) => {
      const reader = new FileReader()
      reader.onload = (ev) => {
        setAttachments((prev) => [...prev, {
          name: file.name,
          type: file.type,
          dataUrl: ev.target?.result as string,
        }])
      }
      reader.onerror = () => {
        console.error('Failed to read file:', file.name)
      }
      reader.readAsDataURL(file)
    })
    e.target.value = ''
  }

  const handleApprove = (msgId: string) => {
    setApprovedIds((prev) => new Set([...prev, msgId]))
    onSend('approved', 'steer')
  }

  const handleReject = (msgId: string) => {
    setRejectedIds((prev) => new Set([...prev, msgId]))
    onSend('rejected', 'steer')
  }

  const isDisabled = connectionStatus !== 'connected'

  return (
    <div className='flex h-full flex-col rounded-xl border border-[#2a2a2a] bg-[#111] overflow-hidden'>

      {/* ── Browsing pill ── */}
      {showBrowsePill && (
        <div className='flex justify-center pt-2 px-4'>
          <button
            type='button'
            onClick={onSwitchToBrowser}
            className='flex items-center gap-2 rounded-full border border-blue-500/40 bg-blue-500/10 px-4 py-1.5 text-xs font-medium text-blue-300 hover:bg-blue-500/20 transition-colors shadow-md'
          >
            <IcoGlobe className='h-3.5 w-3.5' />
            Agent is browsing — Switch to Browser
          </button>
        </div>
      )}

      {/* ── Messages ── */}
      <div className='flex-1 overflow-y-auto px-4 py-4 space-y-0.5'>
        {allMessages.length === 0 && (
          <div className='flex h-full flex-col items-center justify-center gap-4 text-center'>
            <div className='flex h-14 w-14 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]'>
              <IcoMessage className='h-6 w-6 text-zinc-500' />
            </div>
            <div>
              <p className='text-sm font-medium text-zinc-300'>Chat with Aegis</p>
              <p className='mt-1 text-xs text-zinc-600'>Send an instruction, attach files, or use a connector</p>
            </div>
            {/* Quick-start chips */}
            <div className='flex flex-wrap justify-center gap-2 max-w-xs'>
              {['Research a topic', 'Write a plan', 'Summarize a URL'].map((chip) => (
                <button
                  key={chip}
                  type='button'
                  onClick={() => setInput(chip + ' ')}
                  className='rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-1.5 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 transition-colors'
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {allMessages.map((msg) => {
          if (msg.role === 'user') return <UserBubble key={msg.id} msg={msg} />
          if (msg.role === 'generating') return (
            <GeneratingCanvas key={msg.id} label={msg.text || 'Creating…'} />
          )
          if (msg.role === 'tool') return <ToolCard key={msg.id} msg={msg} />
          if (msg.role === 'approval') {
            if (approvedIds.has(msg.id) || rejectedIds.has(msg.id)) {
              return (
                <div key={msg.id} className='my-2 rounded-xl border border-[#2a2a2a] bg-[#141414] px-3 py-2 text-xs text-zinc-500 flex items-center gap-2'>
                  {approvedIds.has(msg.id) ? <IcoCheck className='h-3 w-3 text-emerald-400' /> : <IcoX className='h-3 w-3 text-red-400' />}
                  {approvedIds.has(msg.id) ? 'Approved' : 'Rejected'} — {msg.text}
                </div>
              )
            }
            return (
              <ApprovalCard
                key={msg.id}
                msg={msg}
                onApprove={() => handleApprove(msg.id)}
                onReject={() => handleReject(msg.id)}
              />
            )
          }
          if (msg.role === 'subagent') return <SubagentCard key={msg.id} msg={msg} />
          return <AssistantCard key={msg.id} msg={msg} />
        })}

        {/* Working indicator */}
        {isWorking && (
          <div className='flex gap-2.5 mb-2'>
            <div className='mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[#2a2a2a]'>
              <IcoBrain className='h-3.5 w-3.5 text-zinc-300 animate-pulse' />
            </div>
            <div className='rounded-2xl rounded-tl-sm border border-[#2a2a2a] bg-[#1a1a1a] px-3.5 py-2.5'>
              <div className='flex gap-1'>
                <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '0ms' }} />
                <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '150ms' }} />
                <span className='h-1.5 w-1.5 rounded-full bg-zinc-500 animate-bounce' style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Attachment previews ── */}
      {attachments.length > 0 && (
        <div className='flex gap-2 overflow-x-auto px-4 py-2 border-t border-[#2a2a2a]'>
          {attachments.map((att, i) => (
            <div key={i} className='relative flex-shrink-0'>
              {att.type.startsWith('image/') ? (
                <img src={att.dataUrl} alt={att.name} className='h-16 w-16 rounded-lg object-cover border border-[#2a2a2a]' />
              ) : (
                <div className='flex h-16 w-24 flex-col items-center justify-center gap-1 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] text-center p-1'>
                  <IcoFile className='h-5 w-5 text-zinc-400' />
                  <span className='truncate w-full text-[9px] text-zinc-500 px-1'>{att.name}</span>
                </div>
              )}
              <button
                type='button'
                onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                className='absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-zinc-700 text-white hover:bg-zinc-600'
              >
                <IcoX className='h-2.5 w-2.5' />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Input bar ── */}
      <div className='relative border-t border-[#2a2a2a] bg-[#141414] px-3 py-2.5'>
        {/* Plus menu */}
        {showPlusMenu && (
          <PlusMenu
            onAttach={handleAttach}
            onConnector={handleConnectorSelect}
            onClose={() => setShowPlusMenu(false)}
          />
        )}

        {/* Connector chip + textarea wrapper */}
        <div className='flex items-end gap-2'>
          {/* + button */}
          <button
            type='button'
            onClick={() => setShowPlusMenu((v) => !v)}
            disabled={isDisabled}
            className='mb-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-40 transition-colors'
            aria-label='Open menu'
          >
            <Icons.plus className='h-4 w-4' />
          </button>

          {/* Input column: connector chip stacked above textarea */}
          <div className='flex-1 min-w-0'>
            {/* Connector chip (shown when a connector is active) */}
            {activeConnector && (
              <div className='mb-1.5 flex items-center gap-1.5 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-1.5'>
                <img
                  src={activeConnector.icon}
                  alt={activeConnector.name}
                  className='h-4 w-4 rounded object-contain flex-shrink-0'
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
                <span className='flex-1 text-sm font-medium text-blue-300 truncate'>{activeConnector.name}</span>
                <button
                  type='button'
                  onClick={() => setActiveConnector(null)}
                  className='flex-shrink-0 rounded p-0.5 text-zinc-500 hover:text-zinc-200 transition-colors'
                  aria-label='Remove connector'
                >
                  <IcoX className='h-3.5 w-3.5' />
                </button>
              </div>
            )}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={
                activeConnector
                  ? `Ask about ${activeConnector.name}…`
                  : isDisabled
                  ? 'Connecting…'
                  : 'Message Aegis…'
              }
              disabled={isDisabled}
              rows={1}
              className='w-full resize-none overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2 text-sm md:text-base text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-blue-500/60 disabled:opacity-40 transition-colors leading-6'
              style={{ minHeight: '36px' }}
            />
          </div>

          {/* Voice — Gemini Live primary, browser SpeechRecognition fallback */}
          <button
            type='button'
            onClick={handleMicClick}
            disabled={!micAvailable}
            title={micTitle}
            aria-pressed={micIsActive}
            className={`mb-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border transition-colors ${
              micIsActive
                ? 'animate-pulse border-blue-500/80 bg-blue-500/10 text-blue-300'
                : 'border-[#2a2a2a] bg-[#1a1a1a] text-zinc-400 hover:border-zinc-600 hover:text-zinc-200'
            } disabled:cursor-not-allowed disabled:opacity-40`}
            aria-label='Voice input'
          >
            <IcoMic className='h-4 w-4' />
          </button>
          {/* Send / Stop — stop shown while agent is working and no text typed */}
          {isWorking && !input.trim() && attachments.length === 0 ? (
            <button
              type='button'
              onClick={() => onStop?.()}
              className='mb-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-red-500/40 bg-red-500/10 text-red-300 transition-colors hover:bg-red-500/20'
              aria-label='Stop task'
              title='Stop current task'
            >
              {/* Spinning ring + stop square */}
              <span className='relative flex h-4 w-4 items-center justify-center'>
                <span className='absolute inset-0 animate-spin rounded-full border-2 border-red-400/60 border-t-transparent' />
                <span className='h-1.5 w-1.5 rounded-sm bg-red-300' />
              </span>
            </button>
          ) : (
            <button
              type='button'
              onClick={handleSend}
              disabled={isDisabled || (!input.trim() && attachments.length === 0 && !activeConnector)}
              className='mb-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 transition-colors'
              aria-label='Send message'
            >
              <IcoSend className='h-4 w-4' />
            </button>
          )}
        </div>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type='file'
          multiple
          className='hidden'
          onChange={handleFileChange}
        />

        {/* Connection status indicator */}
        {connectionStatus !== 'connected' && (
          <p className='mt-1.5 text-center text-[10px] text-zinc-600'>
            {connectionStatus === 'connecting' ? 'Reconnecting to agent…' : 'Disconnected — check your connection'}
          </p>
        )}
      </div>
    </div>
  )
}
