import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { LogEntry, SteeringMode } from '../hooks/useWebSocket'
import type { ServerMessage } from '../hooks/useConversations'
import { Icons } from './icons'
import { apiUrl } from '../lib/api'
import { normalizeAskUserInputOptions } from '../lib/askUserInput'

// ─── SVG primitives ───────────────────────────────────────────────────────────
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
const IcoGlobe       = (p: SvgProps) => <Svg {...p}><circle cx='12' cy='12' r='9' /><path d='M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18' /></Svg>
const IcoMessage     = (p: SvgProps) => <Svg {...p}><path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' /></Svg>
const IcoPaperclip   = (p: SvgProps) => <Svg {...p}><path d='m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48' /></Svg>
const IcoArrowUp     = (p: SvgProps) => <Svg {...p}><path d='M12 19V5M5 12l7-7 7 7' /></Svg>
const IcoMic         = (p: SvgProps) => <Svg {...p}><rect x='9' y='3' width='6' height='11' rx='3' /><path d='M6 11a6 6 0 0 0 12 0M12 17v4M9 21h6' /></Svg>
const IcoCopy        = (p: SvgProps) => <Svg {...p}><rect x='9' y='9' width='11' height='11' rx='2' /><rect x='4' y='4' width='11' height='11' rx='2' /></Svg>
const IcoCheck       = (p: SvgProps) => <Svg {...p}><path d='m5 12 4 4 10-10' /></Svg>
const IcoX           = (p: SvgProps) => <Svg {...p}><path d='M18 6 6 18M6 6l12 12' /></Svg>
const IcoChevronRight = (p: SvgProps) => <Svg {...p}><path d='m9 18 6-6-6-6' /></Svg>
const IcoSearch      = (p: SvgProps) => <Svg {...p}><circle cx='11' cy='11' r='6' /><path d='m20 20-3.5-3.5' /></Svg>
const IcoFile        = (p: SvgProps) => <Svg {...p}><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' /><path d='M14 2v6h6' /></Svg>
const IcoTerminal    = (p: SvgProps) => <Svg {...p}><polyline points='4 17 10 11 4 5'/><line x1='12' y1='19' x2='20' y2='19'/></Svg>
const IcoPlan        = (p: SvgProps) => <Svg {...p}><rect x='3' y='3' width='18' height='18' rx='2'/><path d='M9 9h6M9 12h6M9 15h4'/></Svg>
const IcoSparkle     = (p: SvgProps) => <Svg {...p}><path d='M12 3v1M12 20v1M3 12h1M20 12h1M5.6 5.6l.7.7M17.7 17.7l.7.7M17.7 6.3l-.7.7M5.6 18.4l.7-.7M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z'/></Svg>

export interface ChatPanelProps {
  logs: LogEntry[]
  isWorking: boolean
  onSend: (instruction: string, mode: SteeringMode, metadata?: Record<string, unknown>) => void
  onDecomposePlan: (prompt: string) => void
  connectionStatus: 'connecting' | 'connected' | 'disconnected'
  transcripts: string[]
  onSwitchToBrowser: () => void
  latestFrame: string | null
  voiceActive?: boolean
  onToggleVoice?: () => void
  voiceDisabled?: boolean
  activeTaskId?: string | null
  serverMessages?: ServerMessage[]
  onStop?: () => void
  onUserInputResponse?: (answer: string, requestId: string) => void
  onPlanConfirm?: (requestId: string) => void
  onPlanReject?: (requestId: string) => void
  reasoningMap?: Record<string, string>
  enableReasoning?: boolean
  onToggleReasoning?: (enabled: boolean) => void
  reasoningEffort?: 'medium' | 'high' | 'extended' | 'adaptive'
  onChangeReasoningEffort?: (effort: 'medium' | 'high' | 'extended' | 'adaptive') => void
  currentModelSupportsReasoning?: boolean
  /** Current task context meter snapshot (persisted with outgoing user messages) */
  contextSnapshot?: {
    tokensUsed: number
    contextLimit: number
    modelId: string
    isCompacting: boolean
  }
  /** Display name of the logged-in user for personalised CTA */
  userName?: string
  /** Mentionable sub-agent handles (used for @ picker in composer) */
  subAgentNames?: string[]
  browseHandoffPromptVisible?: boolean
  onDismissBrowsePrompt?: () => void
}

// ─── Message shape ─────────────────────────────────────────────────────────────
type ChatRole = 'user' | 'assistant' | 'tool' | 'approval' | 'subagent' | 'generating' | 'user_input' | 'task_summary' | 'plan_confirm' | 'thinking'

interface ChatMessage {
  id: string
  role: ChatRole
  text: string
  timestamp?: string
  toolName?: string
  toolArgs?: string
  toolResult?: string
  toolStatus?: 'in_progress' | 'completed' | 'failed'
  subagentId?: string
  subagentStatus?: string
  attachments?: AttachedFile[]
  question?: string
  options?: string[]
  requestId?: string
  stepId?: string
}



interface AttachedFile {
  name: string
  type: string
  dataUrl: string
}

// ─── Live connector type ───────────────────────────────────────────────────────
interface ConnectorMeta {
  id: string
  name: string
  icon: string
  connected: boolean
  status: string
}

// ─── Log parsing ──────────────────────────────────────────────────────────────
const RE_MODEL_RESPONSE  = /^Model response/i
const RE_TOOL_CALL       = /^\[[\w_]+\]/
const RE_GENERATION_TOOL = /^\[(create_image|generate_image|create_video|generate_video|render_image|text_to_image|image_gen)\]/i

/**
 * Browser-execution tool names that belong exclusively in the ActionLog.
 * Non-browser tools (search, code, file ops, APIs, etc.) still surface in chat
 * as collapsible ShellCards so the user has visibility into non-browser work.
 */
const BROWSER_TOOL_NAMES = new Set([
  'navigate_browser', 'navigate', 'go_to_url', 'open_url', 'load_url',
  'click_element', 'click', 'left_click', 'right_click', 'double_click',
  'type_text', 'type', 'input_text', 'fill_input', 'clear_and_type',
  'scroll_page', 'scroll', 'scroll_down', 'scroll_up', 'scroll_to_element',
  'hover_element', 'hover', 'mouse_move',
  'press_key', 'key_press', 'keyboard_press',
  'take_screenshot', 'screenshot',
  'extract_text', 'get_page_text', 'get_inner_text',
  'get_element', 'find_element', 'wait_for_element', 'wait_for_selector',
  'select_option', 'check_checkbox', 'uncheck_checkbox',
  'get_page_html', 'get_dom', 'evaluate_js', 'execute_script',
  'drag_and_drop', 'upload_file_to_browser',
])

/**
 * Internal agent meta-tools that are pure housekeeping — never shown as
 * cards in the chat panel. The isWorking shimmer already signals activity.
 */
const SILENT_TOOL_NAMES = new Set([
  'thinking', 'think', 'internal_think',
  'wait', 'sleep', 'pause', 'noop', 'no_op',
  'set_next_step', 'plan_step', 'record_thought',
])

/**
 * Returns true if this log entry should be hidden from the chat conversation.
 *
 * Rules:
 *   1. Raw browser stepKinds (click / type / scroll) → ActionLog only.
 *   2. Navigate entries with elapsedSeconds > 0 → ActionLog only.
 *   3. Tool calls in BROWSER_TOOL_NAMES → ActionLog only.
 *   4. Tool calls in SILENT_TOOL_NAMES → hidden entirely (internal housekeeping).
 *
 * Non-browser, non-silent tool calls (web_search, run_code, read_file…)
 * pass through and render as ShellCards in chat.
 */
function isBrowserOnlyEntry(entry: LogEntry, msg: string): boolean {
  if (entry.stepKind === 'click' || entry.stepKind === 'type' || entry.stepKind === 'scroll') return true
  if (entry.stepKind === 'navigate' && entry.elapsedSeconds > 0) return true

  if (RE_TOOL_CALL.test(msg)) {
    const match = msg.match(/^\[([\w_]+)\]/)
    const toolName = match?.[1]?.toLowerCase()
    if (toolName && (BROWSER_TOOL_NAMES.has(toolName) || SILENT_TOOL_NAMES.has(toolName))) return true
  }

  return false
}

function logsToMessages(logs: LogEntry[]): ChatMessage[] {
  const msgs: ChatMessage[] = []
  for (const entry of logs) {
    const msg = typeof entry.message === 'string' ? entry.message : String(entry.message ?? '')

    // ── Browser-execution steps: ActionLog only, never in chat ──────────────
    if (isBrowserOnlyEntry(entry, msg)) continue

    if (entry.type === 'reasoning_start' || entry.type === 'reasoning') {
      const stepId = entry.stepId
      if (stepId && !msgs.find((m) => m.role === 'thinking' && m.stepId === stepId)) {
        msgs.push({ id: `thinking-${stepId}`, role: 'thinking', text: msg, stepId })
      }
      continue
    }

    if (msg.includes('[ask_user_input]')) {
      try {
        const jsonStr = msg.replace('[ask_user_input]', '').trim()
        const parsed = JSON.parse(jsonStr)
        msgs.push({
          id: entry.id,
          role: 'user_input',
          text: parsed.question ?? jsonStr,
          question: parsed.question,
          options: normalizeAskUserInputOptions(parsed.options),
          requestId: parsed.request_id,
        })
      } catch {
        msgs.push({ id: entry.id, role: 'user_input', text: msg.replace('[ask_user_input]', '').trim(), options: [] })
      }
      continue
    }

    if (msg.includes('[summarize_task]')) {
      msgs.push({ id: entry.id, role: 'task_summary', text: msg.replace('[summarize_task]', '').trim() })
      continue
    }

    if (msg.includes('[confirm_plan]')) {
      try {
        const jsonStr = msg.replace('[confirm_plan]', '').trim()
        const parsed = JSON.parse(jsonStr)
        msgs.push({ id: entry.id, role: 'plan_confirm', text: parsed.plan ?? jsonStr, requestId: parsed.request_id })
      } catch {
        msgs.push({ id: entry.id, role: 'plan_confirm', text: msg.replace('[confirm_plan]', '').trim() })
      }
      continue
    }

    const isUser       = entry.stepKind === 'navigate' && entry.elapsedSeconds === 0
    const isGenerating = entry.type === 'step' && RE_GENERATION_TOOL.test(msg)
    const isApproval   = entry.type === 'interrupt'
    const isModelResponse = entry.type === 'step' && RE_MODEL_RESPONSE.test(msg)
    const isToolCall   = entry.type === 'step' && !isUser && !isModelResponse && RE_TOOL_CALL.test(msg)
    const isStepText   = entry.type === 'step' && !isUser && !isGenerating && !isModelResponse && !isToolCall

    const displayText  = isModelResponse
      ? msg.replace(/^Model response[:\s]*/i, '').trim()
      : msg

    if (isApproval) {
      msgs.push({ id: entry.id, role: 'approval', text: displayText })
      continue
    }
    if (isGenerating) {
      msgs.push({ id: entry.id, role: 'generating', text: displayText })
      continue
    }
    if (isModelResponse) {
      msgs.push({ id: entry.id, role: 'assistant', text: displayText })
      continue
    }
    if (isToolCall) {
      const toolMatch = msg.match(/^\[([\w_]+)\]/)
      const toolName  = toolMatch?.[1] ?? entry.stepKind
      if (toolName.toLowerCase() === 'thinking') {
        msgs.push({ id: entry.id, role: 'thinking', text: msg.replace(/^\[[\w_]+\]\s*/, '').trim() || 'Thinking', stepId: entry.stepId })
        continue
      }
      const argsRaw   = msg.replace(/^\[[\w_]+\]\s*/, '').trim()
      let argsDisplay = argsRaw
      let result: string | undefined
      if (argsRaw.includes('→')) {
        const [a, r] = argsRaw.split('→')
        argsDisplay = a.trim()
        result      = r?.trim()
      }
      msgs.push({
        id: entry.id,
        role: 'tool',
        text: displayText,
        toolName,
        toolArgs: argsDisplay || undefined,
        toolResult: result,
        toolStatus: entry.type === 'error' ? 'failed' : 'in_progress',
      })
      continue
    }
    if (isStepText || entry.type === 'result' || entry.type === 'error') {
      const role: ChatRole = isUser ? 'user' : 'assistant'
      msgs.push({ id: entry.id, role, text: displayText, timestamp: role === 'user' ? entry.timestamp : undefined })
      continue
    }
  }

  // Post-process: mark tool steps as completed if followed by later messages
  for (let i = 0; i < msgs.length; i++) {
    if (msgs[i].role === 'tool' && msgs[i].toolStatus === 'in_progress') {
      const hasSuccessor = i < msgs.length - 1
      if (hasSuccessor) msgs[i] = { ...msgs[i], toolStatus: 'completed' }
    }
  }
  return msgs
}

// ─── Code block parser ────────────────────────────────────────────────────────
function parseCodeBlocks(text: string): Array<{ type: 'text' | 'code'; content: string; lang?: string }> {
  const parts: Array<{ type: 'text' | 'code'; content: string; lang?: string }> = []
  const regex = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: 'text', content: text.slice(last, m.index) })
    parts.push({ type: 'code', content: m[2].trim(), lang: m[1] || 'text' })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ type: 'text', content: text.slice(last) })
  return parts
}

// ─── CodeCard ────────────────────────────────────────────────────────────────
function CodeCard({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* ignore */ }
  }

  return (
    <div className='my-2 overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#0d0d0d]'>
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2'>
        <span className='font-mono text-[11px] font-medium text-zinc-400 uppercase tracking-wider'>{lang}</span>
        <div className='flex items-center gap-2'>
          <div className='relative'>
            <button
              type='button'
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              className='flex items-center gap-1 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-200 transition-colors'
            >
              <IcoTerminal className='h-3 w-3' />
              <span>Run in Sandbox</span>
            </button>
            {showTooltip && (
              <div className='absolute right-0 top-full mt-1 z-10 whitespace-nowrap rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-2.5 py-1.5 text-[11px] text-zinc-400 shadow-lg'>
                E2B Sandbox — coming soon
              </div>
            )}
          </div>
          <button
            type='button'
            onClick={copy}
            className='flex items-center gap-1 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-200 transition-colors'
          >
            {copied ? <IcoCheck className='h-3 w-3 text-emerald-400' /> : <IcoCopy className='h-3 w-3' />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
      <pre className='overflow-x-auto px-4 py-3 font-mono text-[12px] leading-relaxed text-zinc-300 whitespace-pre'>
        <code>{code}</code>
      </pre>
    </div>
  )
}

// ─── GeneratingCanvas ─────────────────────────────────────────────────────────
function GeneratingCanvas({ label }: { label: string }) {
  return (
    <div className='my-2 flex items-center gap-3 rounded-xl border border-[#2a2a2a] bg-[#141414] p-4'>
      <div className='flex gap-0.5'>
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className='h-5 w-1 rounded-full bg-violet-400 animate-pulse' style={{ animationDelay: `${i * 120}ms` }} />
        ))}
      </div>
      <span className='text-sm text-zinc-400'>{label}</span>
    </div>
  )
}

// ─── UserBubble — dark style (no blue) ────────────────────────────────────────
function UserBubble({ msg }: { msg: ChatMessage }) {
  return (
    <div className='flex justify-end px-1 py-1'>
      <div className='max-w-[82%] space-y-1.5'>
        {msg.attachments?.map((att, i) =>
          att.type.startsWith('image/') ? (
            <img key={i} src={att.dataUrl} alt={att.name} className='max-h-48 rounded-xl object-cover border border-[#2a2a2a]' />
          ) : (
            <div key={i} className='flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2'>
              <IcoFile className='h-4 w-4 flex-shrink-0 text-zinc-400' />
              <span className='text-xs text-zinc-300 truncate'>{att.name}</span>
            </div>
          )
        )}
        {msg.text && msg.text !== '(attachment)' && (
          <div className='rounded-2xl rounded-br-sm bg-[#252525] border border-[#333] px-4 py-2.5'>
            <p className='text-sm leading-relaxed text-zinc-100 whitespace-pre-wrap break-words'>{msg.text}</p>
          </div>
        )}
        {msg.timestamp && (
          <p className='text-right text-[10px] text-zinc-600 pr-1'>{msg.timestamp}</p>
        )}
      </div>
    </div>
  )
}

// ─── AssistantCard ────────────────────────────────────────────────────────────
function AssistantCard({ msg }: { msg: ChatMessage }) {
  const parts = useMemo(() => parseCodeBlocks(msg.text), [msg.text])
  return (
    <div className='mb-3 max-w-[92%]'>
      <div className='min-w-0 text-sm md:text-xl text-zinc-200 break-words'>
        {parts.map((part, i) =>
          part.type === 'code' ? (
            <CodeCard key={i} code={part.content} lang={part.lang ?? 'text'} />
          ) : (
            <span key={i} className='whitespace-pre-wrap'>{part.content}</span>
          )
        )}
      </div>
    </div>
  )
}

// ─── ShellCard — Cursor-style terminal block that collapses to accordion ───────
interface ShellCardProps {
  msg: ChatMessage
  isRunning?: boolean
}

function ShellCard({ msg, isRunning }: ShellCardProps) {
  const [expanded, setExpanded] = useState(isRunning ?? false)
  const outputRef = useRef<HTMLPreElement>(null)

  const toolLabel = (msg.toolName ?? 'shell').replace(/_/g, ' ')
  const command   = msg.toolArgs ?? msg.text.replace(/^\[[\w_]+\]\s*/, '')
  const result    = msg.toolResult
  const status    = msg.toolStatus ?? 'in_progress'

  // Auto-expand when run starts, then collapse to one-line summary when run ends.
  const prevRunning = useRef(isRunning)
  useEffect(() => {
    if (prevRunning.current === isRunning) return
    if (isRunning) setExpanded(true)
    if (!isRunning && prevRunning.current) setExpanded(false)
    prevRunning.current = isRunning
  }, [isRunning])

  // Auto-scroll output while running
  useEffect(() => {
    if (expanded && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  })

  const statusColor = status === 'completed'
    ? 'text-emerald-400'
    : status === 'failed'
      ? 'text-red-400'
      : 'text-amber-400'

  const statusDot = status === 'completed'
    ? <span className='h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0' />
    : status === 'failed'
      ? <span className='h-1.5 w-1.5 rounded-full bg-red-400 flex-shrink-0' />
      : <span className='h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse flex-shrink-0' />

  if (!expanded) {
    // Collapsed: single-line accordion row (like Cursor's "Ran Get-Content ..." lines)
    return (
      <button
        type='button'
        onClick={() => setExpanded(true)}
        className='flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-colors hover:bg-[#1a1a1a] group'
      >
        {statusDot}
        <span className={`font-mono text-xs font-medium ${statusColor}`}>
          {isRunning ? 'Running' : status === 'failed' ? 'Failed' : 'Ran'}
        </span>
        <span className='flex-1 truncate font-mono text-xs text-zinc-400'>
          {toolLabel}{command ? ` ${command}` : ''}
        </span>
        <span className='rounded-md border border-[#2f2f2f] bg-[#171717] px-1.5 py-0.5 text-[10px] font-medium text-zinc-500'>
          sandbox
        </span>
        <IcoChevronRight className='h-3 w-3 text-zinc-600 group-hover:text-zinc-400 transition-colors flex-shrink-0' />
      </button>
    )
  }

  // Expanded: full terminal shell card (like Cursor's Shell block)
  return (
    <div className='my-1 overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#0d0d0d]'>
      {/* Terminal header bar */}
      <button
        type='button'
        onClick={() => setExpanded(false)}
        className='flex w-full items-center gap-2.5 border-b border-[#1e1e1e] bg-[#141414] px-3 py-2 text-left hover:bg-[#1a1a1a] transition-colors'
      >
        {/* Traffic-light dots */}
        <span className='flex gap-1.5 flex-shrink-0'>
          <span className='h-2.5 w-2.5 rounded-full bg-[#ff5f56]' />
          <span className='h-2.5 w-2.5 rounded-full bg-[#ffbd2e]' />
          <span className='h-2.5 w-2.5 rounded-full bg-[#27c93f]' />
        </span>
        <IcoTerminal className='h-3.5 w-3.5 flex-shrink-0 text-zinc-500' />
        <span className='flex-1 truncate font-mono text-[11px] font-medium text-zinc-300'>
          Shell — {toolLabel}
        </span>
        <span className='rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300'>
          Sandboxed
        </span>
        {isRunning && (
          <span className='flex-shrink-0 text-[10px] font-mono text-amber-400 animate-pulse'>running…</span>
        )}
        {statusDot}
      </button>

      {/* Terminal body */}
      <pre
        ref={outputRef}
        className='max-h-52 overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed text-zinc-300 whitespace-pre-wrap'
        style={{ background: '#0d0d0d' }}
      >
        {/* Prompt line */}
        <span className='text-emerald-400'>$ </span>
        <span className='text-zinc-200'>{command}</span>
        {'\n'}
        {result && <span className='text-zinc-400'>{result}</span>}
        {isRunning && <span className='shell-cursor' />}
      </pre>
    </div>
  )
}

// ─── ThinkingRow — Cursor-style "Thinking" with shimmer + dropdown ────────────
interface ThinkingRowProps {
  stepId: string
  reasoningText: string
  isStreaming: boolean
}

function ThinkingRow({ stepId: _stepId, reasoningText, isStreaming }: ThinkingRowProps) {
  const [open, setOpen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight
    }
  })

  return (
    <div className='my-0.5'>
      <button
        type='button'
        onClick={() => setOpen((v) => !v)}
        className='flex items-center gap-2 rounded-xl px-3 py-1.5 hover:bg-[#1a1a1a] transition-colors text-left'
      >
        {isStreaming ? (
          /* Shimmer "Thinking" tag */
          <span
            className='thinking-shimmer rounded-md bg-[#1e1e2e] px-2.5 py-0.5 text-xs font-semibold text-violet-300 border border-violet-500/20'
          >
            Thinking
          </span>
        ) : (
          <span className='rounded-md bg-[#1a1a1a] px-2.5 py-0.5 text-xs font-medium text-zinc-500 border border-[#2a2a2a]'>
            Thought
          </span>
        )}
        <svg
          className={`h-3 w-3 text-zinc-600 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
          viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'>
          <path d='m9 18 6-6-6-6' />
        </svg>
      </button>
      {open && (
        <div
          ref={contentRef}
          className='mx-3 mt-0.5 max-h-48 overflow-y-auto rounded-xl border border-violet-500/15 bg-[#0e0e18] px-3 py-2.5 font-mono text-[11px] leading-relaxed text-zinc-400 whitespace-pre-wrap'
        >
          {reasoningText || <span className='text-zinc-600 animate-pulse'>…</span>}
        </div>
      )}
    </div>
  )
}

// ─── ApprovalCard — permission-gate confirm/decline ──────────────────────────
// Used for tool-permission actions and bot confirmations (Telegram, Slack, Discord).
// Sends 'confirmed' or 'declined' as a prompt so the agent can proceed.
function ApprovalCard({ msg, onApprove, onReject }: { msg: ChatMessage; onApprove: () => void; onReject: () => void }) {
  const [status, setStatus] = useState<'pending' | 'confirmed' | 'declined'>('pending')

  if (status !== 'pending') {
    return (
      <div className={`my-1.5 flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
        status === 'confirmed' ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400' : 'border-red-500/20 bg-red-500/5 text-red-400'
      }`}>
        {status === 'confirmed' ? <IcoCheck className='h-3.5 w-3.5 flex-shrink-0' /> : <IcoX className='h-3.5 w-3.5 flex-shrink-0' />}
        <span className='font-medium'>{status === 'confirmed' ? 'Action confirmed' : 'Action declined'}</span>
        <span className='text-zinc-500 truncate'>· {msg.text.slice(0, 60)}{msg.text.length > 60 ? '…' : ''}</span>
      </div>
    )
  }

  return (
    <div className='my-2 rounded-2xl border border-[#2a2a2a] bg-[#191919] overflow-hidden'>
      {/* Header */}
      <div className='flex items-center gap-2 border-b border-[#222] px-4 pt-4 pb-3'>
        <span className='flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-amber-500/15'>
          <IcoSparkle className='h-3.5 w-3.5 text-amber-400' />
        </span>
        <p className='text-xs font-semibold text-zinc-300'>Confirm action</p>
      </div>

      {/* Action content */}
      <div className='px-4 py-3'>
        <p className='text-sm leading-relaxed text-zinc-200'>{msg.text}</p>
      </div>

      {/* Buttons */}
      <div className='flex items-center gap-2 border-t border-[#222] px-4 py-3'>
        <button
          type='button'
          onClick={() => { setStatus('confirmed'); onApprove() }}
          className='flex-1 rounded-xl bg-zinc-100 px-3 py-2 text-xs font-semibold text-zinc-900 hover:bg-white transition-colors'
        >
          Confirm
        </button>
        <button
          type='button'
          onClick={() => { setStatus('declined'); onReject() }}
          className='rounded-xl border border-[#333] bg-[#1a1a1a] px-3 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors'
        >
          Decline
        </button>
      </div>
    </div>
  )
}

// ─── SubagentCard ─────────────────────────────────────────────────────────────
function SubagentCard({ msg }: { msg: ChatMessage }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div className='my-2 overflow-hidden rounded-xl border border-blue-500/20 bg-[#0d1626]'>
      <div className='flex items-center gap-3 border-b border-blue-500/10 px-4 py-3'>
        <span className='relative flex h-3 w-3 flex-shrink-0'>
          <span className='absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75' />
          <span className='relative inline-flex h-3 w-3 rounded-full bg-blue-500' />
        </span>
        <p className='flex-1 text-xs font-semibold text-blue-300'>Sub-agent spawned</p>
        <button type='button' onClick={() => setDismissed(true)} className='text-zinc-600 hover:text-zinc-300 transition-colors'>
          <IcoX className='h-3.5 w-3.5' />
        </button>
      </div>
      <div className='px-4 py-3'>
        <p className='text-sm text-zinc-300'>{msg.text}</p>
        {msg.subagentStatus && (
          <p className='mt-1.5 text-[11px] font-mono text-zinc-500'>{msg.subagentStatus}</p>
        )}
      </div>
    </div>
  )
}

// ─── UserInputCard — inline quick-reply + custom reply slot ───────────────────
function UserInputCard({
  question, options, requestId, onRespond,
}: { question: string; options: string[]; requestId: string; onRespond: (answer: string, requestId: string) => void }) {
  const [customMode, setCustomMode] = useState(false)
  const [customText, setCustomText] = useState('')
  const [answered, setAnswered] = useState<string | null>(null)

  const promptOptions = options.length > 0 ? options : ['Continue']
  const customSlotLabel = 'Type your own answer'

  const handleQuickReply = (opt: string) => {
    setAnswered(opt)
    onRespond(opt, requestId)
  }

  const handleCustomSend = () => {
    const answer = customText.trim()
    if (!answer) return
    setAnswered(answer)
    onRespond(answer, requestId)
  }

  if (answered) {
    return (
      <div className='my-1.5 rounded-xl border border-[#2a2a2a] bg-[#141414] px-3 py-2'>
        <p className='text-xs text-zinc-500'>You answered: <span className='text-zinc-300'>{answered}</span></p>
      </div>
    )
  }

  return (
    <div className='my-2 rounded-xl border border-[#2a2a2a] bg-[#151515]'>
      <div className='border-b border-[#242424] px-3 py-2'>
        <p className='text-xs font-medium text-zinc-200'>Asking question</p>
        <p className='mt-1 text-sm leading-snug text-zinc-100'>{question}</p>
      </div>

      <div className='px-3 py-2'>
        <div className='flex flex-wrap gap-2'>
          {promptOptions.map((opt, idx) => (
            <button
              key={`${opt}-${idx}`}
              type='button'
              onClick={() => handleQuickReply(opt)}
              className='rounded-full border border-[#2f2f2f] bg-[#1d1d1d] px-3 py-1.5 text-xs text-zinc-200 hover:border-zinc-500 hover:bg-[#252525]'
            >
              {idx + 1}. {opt}
            </button>
          ))}
          <button
            type='button'
            onClick={() => setCustomMode((prev) => !prev)}
            className={`rounded-full border px-3 py-1.5 text-xs ${
              customMode
                ? 'border-blue-400/60 bg-blue-500/10 text-blue-300'
                : 'border-[#2f2f2f] bg-[#1d1d1d] text-zinc-200 hover:border-zinc-500 hover:bg-[#252525]'
            }`}
          >
            {promptOptions.length + 1}. {customSlotLabel}
          </button>
        </div>
      </div>

      {customMode && (
        <div className='border-t border-[#242424] px-3 py-2'>
          <div className='flex items-center gap-2'>
            <input
              type='text'
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCustomSend() }}
              placeholder='Type your answer...'
              className='flex-1 rounded-lg border border-[#2a2a2a] bg-[#101010] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-500/60'
            />
            <button
              type='button'
              onClick={handleCustomSend}
              disabled={!customText.trim()}
              className='rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed'
            >
              Continue
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── TaskSummaryCard — inline summary with expand/collapse for long plans ─────
function TaskSummaryCard({ summary }: { summary: string }) {
  const [decision, setDecision] = useState<'pending' | 'implement' | 'discard'>('pending')
  const [expanded, setExpanded] = useState(false)
  const TRUNCATE_LEN = 380
  const isLong = summary.length > TRUNCATE_LEN
  const displayText = isLong && !expanded ? summary.slice(0, TRUNCATE_LEN) + '…' : summary

  if (decision !== 'pending') {
    return (
      <div className={`my-1.5 flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
        decision === 'implement' ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400' : 'border-[#2a2a2a] bg-[#141414] text-zinc-500'
      }`}>
        {decision === 'implement' ? <IcoCheck className='h-3.5 w-3.5 flex-shrink-0' /> : <IcoX className='h-3.5 w-3.5 flex-shrink-0' />}
        <span>{decision === 'implement' ? 'Plan accepted — implementing' : 'Plan declined'}</span>
      </div>
    )
  }

  return (
    <div className='my-2 rounded-2xl border border-[#2a2a2a] bg-[#191919] overflow-hidden'>
      {/* Header */}
      <div className='flex items-center gap-2 border-b border-[#222] px-4 py-3'>
        <span className='flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/15'>
          <IcoCheck className='h-3.5 w-3.5 text-emerald-400' />
        </span>
        <p className='flex-1 text-xs font-semibold text-zinc-200'>Plan summary</p>
      </div>

      {/* Summary body */}
      <div className='px-4 py-3'>
        <div className='text-sm leading-relaxed text-zinc-300 whitespace-pre-wrap'>{displayText}</div>
        {isLong && (
          <button
            type='button'
            onClick={() => setExpanded((v) => !v)}
            className='mt-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors'
          >
            {expanded ? 'Show less' : 'Show full plan'}
          </button>
        )}
      </div>

      {/* Footer */}
      <div className='flex items-center justify-end gap-2 border-t border-[#222] px-4 py-3'>
        <button
          type='button'
          onClick={() => setDecision('discard')}
          className='px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors'
        >
          Decline
        </button>
        <button
          type='button'
          onClick={() => setDecision('implement')}
          className='flex items-center gap-1.5 rounded-xl bg-zinc-100 px-4 py-1.5 text-xs font-semibold text-zinc-900 hover:bg-white transition-colors'
        >
          Implement
          <span className='text-[10px] opacity-50'>&#9166;</span>
        </button>
      </div>
    </div>
  )
}

// ─── PlanConfirmCard — same layout as TaskSummaryCard but for pre-execution plans
function PlanConfirmCard({ plan, requestId, onConfirm, onReject }: {
  plan: string; requestId: string;
  onConfirm: (requestId: string) => void; onReject: (requestId: string) => void
}) {
  const [status, setStatus] = useState<'pending' | 'confirmed' | 'rejected'>('pending')
  const [expanded, setExpanded] = useState(false)
  const TRUNCATE_LEN = 380
  const isLong = plan.length > TRUNCATE_LEN
  const displayText = isLong && !expanded ? plan.slice(0, TRUNCATE_LEN) + '…' : plan

  if (status !== 'pending') {
    return (
      <div className={`my-1.5 flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${
        status === 'confirmed' ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400' : 'border-[#2a2a2a] bg-[#141414] text-zinc-500'
      }`}>
        {status === 'confirmed' ? <IcoCheck className='h-3.5 w-3.5 flex-shrink-0' /> : <IcoX className='h-3.5 w-3.5 flex-shrink-0' />}
        <span>Plan {status === 'confirmed' ? 'confirmed' : 'rejected'}</span>
      </div>
    )
  }

  return (
    <div className='my-2 rounded-2xl border border-[#2a2a2a] bg-[#191919] overflow-hidden'>
      {/* Header */}
      <div className='flex items-center gap-2 border-b border-[#222] px-4 py-3'>
        <IcoPlan className='h-4 w-4 flex-shrink-0 text-zinc-400' />
        <p className='flex-1 text-xs font-semibold text-zinc-200'>Plan ready</p>
        <span className='text-[10px] text-zinc-600'>Confirm to proceed</span>
      </div>

      {/* Plan body */}
      <div className='px-4 py-3'>
        <div className='text-sm leading-relaxed text-zinc-300 whitespace-pre-wrap'>{displayText}</div>
        {isLong && (
          <button
            type='button'
            onClick={() => setExpanded((v) => !v)}
            className='mt-2 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors'
          >
            {expanded ? 'Show less' : 'Show full plan'}
          </button>
        )}
      </div>

      {/* Footer */}
      <div className='flex items-center justify-end gap-2 border-t border-[#222] px-4 py-3'>
        <button
          type='button'
          onClick={() => { setStatus('rejected'); onReject(requestId) }}
          className='px-3 py-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors'
        >
          Reject
        </button>
        <button
          type='button'
          onClick={() => { setStatus('confirmed'); onConfirm(requestId) }}
          className='flex items-center gap-1.5 rounded-xl bg-zinc-100 px-4 py-1.5 text-xs font-semibold text-zinc-900 hover:bg-white transition-colors'
        >
          Confirm Plan
          <span className='text-[10px] opacity-50'>&#9166;</span>
        </button>
      </div>
    </div>
  )
}

// ─── PlusMenu ─────────────────────────────────────────────────────────────────
interface PlusMenuProps {
  onAttach: (accept: string, capture?: string) => void
  onConnector: (connector: ConnectorMeta) => void
  onClose: () => void
}

function PlusMenu({ onAttach, onConnector, onClose }: PlusMenuProps) {
  const [connectors, setConnectors] = useState<ConnectorMeta[]>([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    let cancelled = false
    fetch(apiUrl('/api/connectors'), { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => { if (!cancelled && data.ok) setConnectors(data.connectors as ConnectorMeta[]) })
      .catch(() => { /* silently ignore */ })
    return () => { cancelled = true }
  }, [])

  const filteredConnectors = connectors.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))

  const attachRows = [
    { id: 'camera',  label: 'Camera',  accept: 'image/*',  capture: 'environment' },
    { id: 'photos',  label: 'Photos',  accept: 'image/*',  capture: undefined },
    { id: 'files',   label: 'Files',   accept: '*/*',      capture: undefined },
    { id: 'videos',  label: 'Videos',  accept: 'video/*',  capture: undefined },
  ]

  return (
    <>
      <div className='fixed inset-0 z-40 bg-black/60' onClick={onClose} />
      <div className='fixed bottom-0 left-0 right-0 z-50 rounded-t-3xl bg-[#1c1c1c] pb-safe shadow-2xl sm:absolute sm:bottom-full sm:left-0 sm:mb-2 sm:rounded-2xl sm:w-72 sm:pb-0'>
        <div className='flex justify-center pt-2 pb-1 sm:hidden'>
          <div className='h-1 w-10 rounded-full bg-zinc-700' />
        </div>
        <div className='px-1 pt-2'>
          {attachRows.map((row) => (
            <button key={row.id} type='button' onClick={() => { onAttach(row.accept, row.capture); onClose() }}
              className='flex w-full items-center gap-4 rounded-xl px-3 py-2.5 text-left hover:bg-[#2a2a2a] transition-colors'>
              <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
                <IcoPaperclip className='h-5 w-5 text-zinc-200' />
              </div>
              <span className='text-sm font-medium text-zinc-200'>{row.label}</span>
            </button>
          ))}
        </div>

        {connectors.length > 0 && (
          <>
            <div className='mx-4 my-2 border-t border-[#2a2a2a]' />
            <div className='px-3 pb-1'>
              <div className='mb-2 flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#111] px-3 py-1.5'>
                <IcoSearch className='h-3.5 w-3.5 flex-shrink-0 text-zinc-500' />
                <input value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder='Search connectors…'
                  className='flex-1 bg-transparent text-xs text-zinc-300 outline-none placeholder:text-zinc-600' />
              </div>
              <div className='max-h-40 overflow-y-auto'>
                {filteredConnectors.map((conn) => (
                  <button key={conn.id} type='button' onClick={() => { onConnector(conn); onClose() }}
                    className='flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left hover:bg-[#2a2a2a] transition-colors'>
                    <div className='flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#2a2a2a]'>
                      <img src={conn.icon} alt={conn.name} className='h-5 w-5 rounded object-contain' onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                    </div>
                    <span className='flex-1 truncate text-sm font-medium text-zinc-200'>{conn.name}</span>
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

// ─── Cursor-style input bar ────────────────────────────────────────────────────
interface InputBarCursorProps {
  input: string
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  onSend: () => void
  onStop: () => void
  onMicClick: () => void
  onPlusClick: () => void
  onPlanClick: () => void
  isWorking: boolean
  isDisabled: boolean
  micIsActive: boolean
  micAvailable: boolean
  micTitle: string
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  placeholder: string
  activeConnector: ConnectorMeta | null
  onRemoveConnector: () => void
  hasAttachments: boolean
  modelChipLabel?: string
  isLocalOnly?: boolean
  hasFullAccess?: boolean
}

function InputBarCursor({
  input, onInputChange, onKeyDown, onSend, onStop, onMicClick, onPlusClick, onPlanClick,
  isWorking, isDisabled, micIsActive, micAvailable, micTitle, textareaRef, placeholder,
  activeConnector, onRemoveConnector, hasAttachments,
  modelChipLabel = 'GPT-5.4',
  isLocalOnly = true,
  hasFullAccess = true,
}: InputBarCursorProps) {
  const canSend = input.trim().length > 0 || hasAttachments

  return (
    <div className='rounded-3xl border border-[#303030] bg-[#1a1a1a] shadow-[0_8px_30px_rgba(0,0,0,0.3)] overflow-hidden'>

      {/* Connector chip inside card */}
      {activeConnector && (
        <div className='flex items-center gap-1.5 border-b border-[#2a2a2a] px-3 py-1.5'>
          <img src={activeConnector.icon} alt={activeConnector.name}
            className='h-3.5 w-3.5 rounded object-contain flex-shrink-0'
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          <span className='flex-1 text-xs font-medium text-blue-300 truncate'>{activeConnector.name}</span>
          <button type='button' onClick={onRemoveConnector} className='text-zinc-600 hover:text-zinc-300 transition-colors'>
            <IcoX className='h-3 w-3' />
          </button>
        </div>
      )}

      {/* Textarea */}
      <div className='relative'>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={onInputChange}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          className='w-full resize-none bg-transparent px-4 pb-12 pt-3 text-sm text-zinc-200 placeholder:text-zinc-500 outline-none disabled:opacity-40 leading-6'
          style={{ minHeight: '70px', maxHeight: '160px', overflow: 'hidden' }}
        />
        {isWorking && !canSend ? (
          <button type='button' onClick={onStop}
            className='absolute bottom-2.5 right-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-[#2a2a2a] text-red-300 hover:bg-[#333] transition-colors'
            aria-label='Stop task' title='Stop current task'>
            <span className='relative flex h-4 w-4 items-center justify-center'>
              <span className='absolute inset-0 animate-spin rounded-full border-2 border-red-400/50 border-t-transparent' />
              <span className='h-1.5 w-1.5 rounded-sm bg-red-300' />
            </span>
          </button>
        ) : (
          <button type='button' onClick={onSend}
            disabled={isDisabled || !canSend}
            className='absolute bottom-2.5 right-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-zinc-900 hover:bg-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors'
            aria-label='Send message'>
            <IcoArrowUp className='h-4 w-4' />
          </button>
        )}
      </div>

      <div className='flex items-center gap-1.5 border-t border-[#242424] px-2.5 py-2'>
        {/* + button */}
        <button type='button' onClick={onPlusClick} disabled={isDisabled}
          className='flex items-center justify-center h-7 w-7 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-[#2a2a2a] disabled:opacity-40 transition-colors flex-shrink-0'
          aria-label='Add files or connectors'>
          <Icons.plus className='h-4 w-4' />
        </button>

        {/* Plan button */}
        <button type='button' onClick={onPlanClick} disabled={isDisabled}
          className='flex items-center gap-1.5 h-7 rounded-lg px-2.5 text-zinc-500 hover:text-zinc-200 hover:bg-[#2a2a2a] disabled:opacity-40 transition-colors flex-shrink-0 text-xs font-medium'>
          <IcoPlan className='h-3.5 w-3.5' />
          Plan
        </button>

        <span className='rounded-lg px-2 py-1 text-xs text-zinc-500'>⚡ {modelChipLabel}</span>

        <div className='flex-1' />

        {/* Mic */}
        <button type='button' onClick={onMicClick} disabled={!micAvailable}
          title={micTitle} aria-pressed={micIsActive}
          className={`flex h-7 w-7 items-center justify-center rounded-lg transition-colors flex-shrink-0 ${
            micIsActive ? 'text-blue-300 bg-blue-500/10 animate-pulse' : 'text-zinc-600 hover:text-zinc-300 hover:bg-[#2a2a2a]'
          } disabled:cursor-not-allowed disabled:opacity-40`}>
          <IcoMic className='h-3.5 w-3.5' />
        </button>

      </div>

      <div className='flex items-center gap-3 border-t border-[#242424] px-3 py-1.5 text-[11px] text-zinc-500'>
        <span className='inline-flex items-center gap-1'>{isLocalOnly ? '◻ Local' : '◻ Remote'}</span>
        <span className='inline-flex items-center gap-1'>{hasFullAccess ? '◉ Full access' : '◉ Limited access'}</span>
      </div>
    </div>
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
  onUserInputResponse,
  onPlanConfirm,
  onPlanReject,
  reasoningMap,
  contextSnapshot,
  userName,
  subAgentNames = [],
  browseHandoffPromptVisible = false,
  onDismissBrowsePrompt,
}: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState<AttachedFile[]>([])

  // ── Conversation persistence ──────────────────────────────────────────────
  const CHAT_KEY = (id: string) => `aegis.chat.${id}`
  const saveMsgs = (id: string | null | undefined, msgs: ChatMessage[]) => {
    if (!id) return
    try { localStorage.setItem(CHAT_KEY(id), JSON.stringify(msgs.slice(-200))) } catch { /* quota */ }
  }

  const [sentMessages, setSentMessages] = useState<ChatMessage[]>([])
  const prevTaskIdRef    = useRef(activeTaskId)
  const prevServerLenRef = useRef(0)

  useEffect(() => {
    const taskChanged   = prevTaskIdRef.current !== activeTaskId
    const serverArrived = prevServerLenRef.current === 0 && serverMessages.length > 0
    prevTaskIdRef.current    = activeTaskId
    prevServerLenRef.current = serverMessages.length
    if (!taskChanged && !serverArrived) return
    if (serverMessages.length > 0) {
      const serverMapped = serverMessages.map((m) => ({
        id: m.id,
        role: (m.role === 'user' ? 'user' : 'assistant') as ChatRole,
        text: m.content,
        timestamp:
          m.role === 'assistant'
            ? undefined
            : m.created_at
              ? new Date(m.created_at).toLocaleTimeString()
              : new Date().toLocaleTimeString(),
        attachments: Array.isArray((m.metadata as Record<string, unknown> | null)?.attachments)
          ? ((m.metadata as Record<string, unknown>).attachments as AttachedFile[])
          : undefined,
      }))
      const serverUserTexts = new Set(serverMapped.filter((m) => m.role === 'user').map((m) => m.text.trim()))
      setSentMessages((prev) => {
        const optimisticLocalUsers = prev.filter(
          (m) => m.role === 'user' && String(m.id).startsWith('local-') && !serverUserTexts.has((m.text ?? '').trim()),
        )
        return [...optimisticLocalUsers, ...serverMapped]
      })
    } else if (taskChanged) {
      setSentMessages([])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTaskId, serverMessages.length])

  const [activeConnector, setActiveConnector] = useState<ConnectorMeta | null>(null)
  const [showPlusMenu, setShowPlusMenu] = useState(false)
  const [approvedIds, setApprovedIds]   = useState<Set<string>>(new Set())
  const [rejectedIds, setRejectedIds]   = useState<Set<string>>(new Set())

  // ── Voice (Gemini Live + browser SR fallback) ─────────────────────────────
  type AnySR = { continuous: boolean; interimResults: boolean; lang: string; start(): void; stop(): void; onresult: ((e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null }
  const srRef = useRef<AnySR | null>(null)
  const [srActive, setSrActive] = useState(false)
  const geminiLiveAvailable = connectionStatus === 'connected' && !voiceDisabled

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
    if (geminiLiveAvailable && onToggleVoice) { onToggleVoice(); return }
    const SR = getSRCtor()
    if (!SR) return
    if (srActive && srRef.current) { srRef.current.stop(); return }
    const sr = new SR()
    sr.continuous = false; sr.interimResults = false; sr.lang = 'en-US'
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

  const micIsActive = voiceActive || srActive
  const micAvailable = !voiceDisabled && (geminiLiveAvailable || !!getSRCtor())
  const micTitle = micIsActive
    ? (voiceActive ? 'Stop Gemini Live voice input' : 'Stop recording')
    : voiceDisabled ? 'Microphone requires HTTPS or localhost'
    : geminiLiveAvailable ? 'Start Gemini 2.0 Flash Live voice input'
    : 'Start voice input (browser fallback)'

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef    = useRef<HTMLTextAreaElement>(null)
  const fileInputRef   = useRef<HTMLInputElement>(null)

  const baseMessages = useMemo(() => logsToMessages(logs), [logs])

  useEffect(() => {
    if (sentMessages.length > 500) setSentMessages((prev) => prev.slice(-500))
  }, [sentMessages.length])

  const allMessages = useMemo(() => {
    const seenUserTexts = new Set(sentMessages.filter((m) => m.role === 'user').map((m) => m.text.trim()))
    const dedupedBase = baseMessages.filter((m) => {
      if (m.role !== 'user') return true
      const key = m.text.trim()
      if (!key) return true
      if (seenUserTexts.has(key)) return false
      seenUserTexts.add(key)
      return true
    })
    return [...sentMessages, ...dedupedBase]
  }, [sentMessages, baseMessages])
  const latestThinkingId = useMemo(() => {
    for (let i = allMessages.length - 1; i >= 0; i -= 1) {
      if (allMessages[i].role === 'thinking') return allMessages[i].id
    }
    return null
  }, [allMessages])

  useEffect(() => {
    if (allMessages.length > 0) saveMsgs(activeTaskId, allMessages)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allMessages.length, activeTaskId])

  const showBrowsePill = browseHandoffPromptVisible && isWorking && latestFrame

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [allMessages.length])

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
    el.style.overflow = el.scrollHeight > 144 ? 'auto' : 'hidden'
  }, [])

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    resizeTextarea()
  }

  const mentionQuery = useMemo(() => {
    const match = input.match(/@([a-zA-Z0-9._-]*)$/)
    return match ? match[1].toLowerCase() : null
  }, [input])

  const mentionOptions = useMemo(() => {
    if (mentionQuery === null) return []
    return subAgentNames
      .filter((name) => name.toLowerCase().includes(mentionQuery))
      .slice(0, 6)
  }, [mentionQuery, subAgentNames])

  const handleMentionPick = (name: string) => {
    setInput((prev) => prev.replace(/@([a-zA-Z0-9._-]*)$/, `@${name} `))
    window.setTimeout(() => textareaRef.current?.focus(), 0)
  }

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed && attachments.length === 0) return
    const withContext = activeConnector ? `[${activeConnector.name}] ${trimmed}` : trimmed
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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
      onSend(withContext || '(attachment)', 'steer', {
        attachments: attachments.length > 0 ? attachments : undefined,
        active_connector: activeConnector
          ? { id: activeConnector.id, name: activeConnector.name }
          : undefined,
        context_snapshot: contextSnapshot ?? undefined,
        task_label_source: 'chat',
        task_label: withContext || '(attachment)',
      })
    }
    setInput('')
    setAttachments([])
    setActiveConnector(null)
    if (textareaRef.current) { textareaRef.current.style.height = 'auto' }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const handlePlanClick = () => {
    const prompt = input.trim()
    if (prompt) { onDecomposePlan(prompt); setInput('') }
    else setInput('/plan ')
    textareaRef.current?.focus()
  }

  const handleConnectorSelect = (connector: ConnectorMeta) => {
    setActiveConnector(connector)
    window.setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const handleAttach = (accept: string, capture?: string) => {
    if (!fileInputRef.current) return
    fileInputRef.current.accept = accept
    if (capture) fileInputRef.current.setAttribute('capture', capture)
    else fileInputRef.current.removeAttribute('capture')
    fileInputRef.current.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    files.forEach((file) => {
      const reader = new FileReader()
      reader.onload = (ev) => {
        setAttachments((prev) => [...prev, { name: file.name, type: file.type, dataUrl: ev.target?.result as string }])
      }
      reader.onerror = () => { console.error('Failed to read file:', file.name) }
      reader.readAsDataURL(file)
    })
    e.target.value = ''
  }

  const handleApprove = (msgId: string) => { setApprovedIds((prev) => new Set([...prev, msgId])); onSend('approved', 'steer') }
  const handleReject  = (msgId: string) => { setRejectedIds((prev) => new Set([...prev, msgId])); onSend('rejected', 'steer') }

  const handleUserInputReply = (answer: string, requestId: string) => {
    const trimmed = answer.trim()
    if (!trimmed) return
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setSentMessages((prev) => {
      const next: ChatMessage[] = [...prev, { id: `local-${crypto.randomUUID()}`, role: 'user', text: trimmed, timestamp: now }]
      saveMsgs(activeTaskId, next)
      return next
    })
    onUserInputResponse?.(trimmed, requestId)
    onSend(trimmed, 'steer', { task_label_source: 'chat', task_label: trimmed })
  }

  const isDisabled = connectionStatus !== 'connected'

  // Personalised CTA — first name only
  const firstName = userName ? userName.split(' ')[0] : null
  const ctaText = firstName ? `Hi ${firstName}, what do you want me to do today?` : 'What do you want me to do today?'
  const ctaSubtext = 'Send an instruction, attach files, or use a connector'
  const modelChipLabel = 'GPT-5.4'
  const isLocalOnly = true
  const hasFullAccess = true

  return (
    <div className='flex h-full flex-col rounded-xl border border-[#2a2a2a] bg-[#111] overflow-hidden'>

      {/* Browsing pill */}
      {showBrowsePill && (
        <div className='flex justify-center pt-2 px-4'>
          <div className='flex items-center gap-2 rounded-full border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs font-medium text-blue-300 shadow-md'>
            <button
              type='button'
              onClick={onSwitchToBrowser}
              className='flex items-center gap-2 rounded-full px-1 py-0.5 text-xs font-medium text-blue-300 hover:text-blue-100 transition-colors'
            >
              <IcoGlobe className='h-3.5 w-3.5' />
              Agent is browsing — Switch to Browser
            </button>
            <button
              type='button'
              onClick={onDismissBrowsePrompt}
              className='rounded-full border border-blue-400/30 px-1.5 py-0.5 text-[10px] text-blue-200/80 hover:text-blue-100'
              title='Dismiss'
              aria-label='Dismiss browse switch prompt'
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className='flex-1 overflow-y-auto px-3 py-3 space-y-0.5'>

        {allMessages.length === 0 && (
          <div className='flex h-full flex-col items-center justify-center gap-3 text-center px-4'>
            <div className='flex h-12 w-12 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]'>
              <IcoMessage className='h-5 w-5 text-zinc-500' />
            </div>
            <div>
              <p className='text-base font-semibold text-zinc-200'>{ctaText}</p>
              <p className='mt-1 text-xs text-zinc-600'>{ctaSubtext}</p>
            </div>
            <div className='flex flex-wrap justify-center gap-2 max-w-xs mt-1'>
              {['Research a topic', 'Write a plan', 'Summarize a URL'].map((chip) => (
                <button key={chip} type='button' onClick={() => setInput(chip + ' ')}
                  className='rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-1.5 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 transition-colors'>
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {allMessages.map((msg) => {
          if (msg.role === 'user') return <UserBubble key={msg.id} msg={msg} />
          if (msg.role === 'generating') return <GeneratingCanvas key={msg.id} label={msg.text || 'Creating…'} />

          // Tool calls → ShellCard (collapsed accordion by default when done, open while running)
          if (msg.role === 'tool') {
            const isLive = isWorking && msg.toolStatus === 'in_progress'
            return <ShellCard key={msg.id} msg={msg} isRunning={isLive} />
          }

          if (msg.role === 'approval') {
            if (approvedIds.has(msg.id) || rejectedIds.has(msg.id)) {
              return (
                <div key={msg.id} className='my-1 flex items-center gap-2 px-3 py-2 rounded-xl border border-[#2a2a2a] text-xs text-zinc-500'>
                  {approvedIds.has(msg.id) ? <IcoCheck className='h-3 w-3 text-emerald-400' /> : <IcoX className='h-3 w-3 text-red-400' />}
                  {approvedIds.has(msg.id) ? 'Approved' : 'Rejected'} — {msg.text}
                </div>
              )
            }
            return <ApprovalCard key={msg.id} msg={msg} onApprove={() => handleApprove(msg.id)} onReject={() => handleReject(msg.id)} />
          }

          if (msg.role === 'subagent') return <SubagentCard key={msg.id} msg={msg} />

          if (msg.role === 'user_input') {
            return (
              <UserInputCard key={msg.id}
                question={msg.question ?? msg.text}
                options={msg.options ?? []}
                requestId={msg.requestId ?? msg.id}
                onRespond={(answer, reqId) => { handleUserInputReply(answer, reqId) }}
              />
            )
          }

          if (msg.role === 'task_summary') return <TaskSummaryCard key={msg.id} summary={msg.text} />

          if (msg.role === 'plan_confirm') {
            return (
              <PlanConfirmCard key={msg.id} plan={msg.text} requestId={msg.requestId ?? msg.id}
                onConfirm={(reqId) => { onPlanConfirm?.(reqId); onSend('confirmed', 'steer') }}
                onReject={(reqId) => { onPlanReject?.(reqId); onSend('rejected', 'steer') }}
              />
            )
          }

          if (msg.role === 'thinking') {
            const stepId = msg.stepId ?? ''
            const reasoningText = reasoningMap?.[stepId] ?? msg.text ?? ''
            const isStreaming = isWorking && msg.id === latestThinkingId
            return (
              <div key={msg.id} className='px-1'>
                <ThinkingRow stepId={stepId} reasoningText={reasoningText} isStreaming={isStreaming} />
              </div>
            )
          }

          return <AssistantCard key={msg.id} msg={msg} />
        })}

        {/* Agent working indicator — shows when no explicit thinking card yet */}
        {isWorking && !allMessages.some((m) => m.role === 'thinking' || m.role === 'tool') && (
          <div className='flex items-center gap-2 px-3 py-2'>
            <span
              className='thinking-shimmer rounded-md bg-[#1e1e2e] px-2.5 py-0.5 text-xs font-semibold text-violet-300 border border-violet-500/20'
            >
              Thinking
            </span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Attachment previews */}
      {attachments.length > 0 && (
        <div className='flex gap-2 overflow-x-auto px-3 py-2 border-t border-[#2a2a2a]'>
          {attachments.map((att, i) => (
            <div key={i} className='relative flex-shrink-0'>
              {att.type.startsWith('image/') ? (
                <img src={att.dataUrl} alt={att.name} className='h-14 w-14 rounded-xl object-cover border border-[#2a2a2a]' />
              ) : (
                <div className='flex h-14 w-20 flex-col items-center justify-center gap-1 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] text-center p-1'>
                  <IcoFile className='h-4 w-4 text-zinc-400' />
                  <span className='truncate w-full text-[9px] text-zinc-500 px-1'>{att.name}</span>
                </div>
              )}
              <button type='button' onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                className='absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-zinc-700 text-white hover:bg-zinc-600'>
                <IcoX className='h-2.5 w-2.5' />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className='relative border-t border-[#1e1e1e] bg-[#111] px-3 py-3'>
        {mentionOptions.length > 0 && (
          <div className='mb-2 rounded-xl border border-[#2a2a2a] bg-[#141414] p-1.5'>
            {mentionOptions.map((name) => (
              <button
                key={name}
                type='button'
                onClick={() => handleMentionPick(name)}
                className='flex w-full items-center justify-between rounded-lg px-2 py-1 text-left text-xs text-zinc-300 hover:bg-[#1f1f1f]'
              >
                <span>@{name}</span>
                <span className='text-zinc-600'>tag sub-agent</span>
              </button>
            ))}
          </div>
        )}
        {/* Plus menu */}
        {showPlusMenu && (
          <PlusMenu
            onAttach={handleAttach}
            onConnector={handleConnectorSelect}
            onClose={() => setShowPlusMenu(false)}
          />
        )}

        <InputBarCursor
          input={input}
          onInputChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onSend={handleSend}
          onStop={() => onStop?.()}
          onMicClick={handleMicClick}
          onPlusClick={() => setShowPlusMenu((v) => !v)}
          onPlanClick={handlePlanClick}
          isWorking={isWorking}
          isDisabled={isDisabled}
          micIsActive={micIsActive}
          micAvailable={micAvailable}
          micTitle={micTitle}
          textareaRef={textareaRef}
          placeholder={
            activeConnector
              ? `Ask about ${activeConnector.name}…`
              : isDisabled
              ? 'Connecting…'
              : 'Ask for a task, research, or code…'
          }
          activeConnector={activeConnector}
          onRemoveConnector={() => setActiveConnector(null)}
          hasAttachments={attachments.length > 0}
          modelChipLabel={modelChipLabel}
          isLocalOnly={isLocalOnly}
          hasFullAccess={hasFullAccess}
        />

        {/* Hidden file input */}
        <input ref={fileInputRef} type='file' multiple className='hidden' onChange={handleFileChange} />

        {connectionStatus !== 'connected' && (
          <p className='mt-1.5 text-center text-[10px] text-zinc-600'>
            {connectionStatus === 'connecting' ? 'Reconnecting to agent…' : 'Disconnected — check your connection'}
          </p>
        )}
      </div>
    </div>
  )
}
