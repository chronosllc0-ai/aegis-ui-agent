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
  /** Called when user responds to an ask_user_input card */
  onUserInputResponse?: (answer: string, requestId: string) => void
  /** Called when user confirms a plan_confirm card */
  onPlanConfirm?: (requestId: string) => void
  /** Called when user rejects a plan_confirm card */
  onPlanReject?: (requestId: string) => void
  /** Map of step_id → accumulated reasoning text */
  reasoningMap?: Record<string, string>
  /** Whether reasoning/thinking mode is enabled */
  enableReasoning?: boolean
  /** Toggle reasoning on/off */
  onToggleReasoning?: (enabled: boolean) => void
  /** Current reasoning effort level */
  reasoningEffort?: 'low' | 'medium' | 'high'
  /** Change reasoning effort level */
  onChangeReasoningEffort?: (effort: 'low' | 'medium' | 'high') => void
  /** Whether the currently selected model supports reasoning */
  currentModelSupportsReasoning?: boolean
}

// ─── Message shape ────────────────────────────────────────────────────────────
type ChatRole = 'user' | 'assistant' | 'tool' | 'approval' | 'subagent' | 'generating' | 'user_input' | 'task_summary' | 'plan_confirm' | 'thinking'

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
  // user_input card fields
  question?: string
  options?: string[]
  requestId?: string
  // reasoning/thinking card fields
  stepId?: string
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
// ── Heuristics for classifying LogEntry messages ─────────────────────────────
// A "model response" is any step message that starts with "Model response" — these
// are raw LLM text turns (not a tool call) and must render as AssistantCard, not
// as a ToolCard dropdown. The backend currently surfaces them prefixed with
// "Model response (no tool call):" but may also emit bare text.
const RE_MODEL_RESPONSE = /^Model response/i
// Real tool calls are identified by bracket-prefixed messages like [screenshot], [go_to_url], etc.
const RE_TOOL_CALL = /^\[[\w_]+\]/
// Only trigger the full-screen generating animation for explicit image/video creation tools.
// Do NOT match free-text messages that happen to contain the word "generating".
const RE_GENERATION_TOOL = /^\[(create_image|generate_image|create_video|generate_video|render_image|text_to_image|image_gen)\]/i

function logsToMessages(logs: LogEntry[]): ChatMessage[] {
  const msgs: ChatMessage[] = []
  for (const entry of logs) {
    const msg = typeof entry.message === 'string' ? entry.message : String(entry.message ?? '')

    // ── Reasoning entries → thinking role cards ─────────────────────────────
    if (entry.type === 'reasoning_start' || entry.type === 'reasoning') {
      const stepId = entry.stepId
      if (stepId) {
        msgs.push({
          id: entry.id,
          role: 'thinking',
          text: entry.message,
          timestamp: entry.timestamp,
          stepId,
        })
      }
      continue
    }

    // ── Special card types ─────────────────────────────────────────────────
    if (msg.startsWith('[ask_user_input]')) {
      try {
        const jsonStr = msg.replace('[ask_user_input]', '').trim()
        const parsed = JSON.parse(jsonStr)
        msgs.push({
          id: entry.id,
          role: 'user_input' as ChatRole,
          text: msg,
          timestamp: entry.timestamp,
          question: parsed.question as string,
          options: parsed.options as string[],
          requestId: parsed.request_id as string,
        })
        continue
      } catch { /* fall through */ }
    }
    if (msg.startsWith('[summarize_task]')) {
      const summary = msg.replace('[summarize_task]', '').trim()
      msgs.push({ id: entry.id, role: 'task_summary' as ChatRole, text: summary, timestamp: entry.timestamp })
      continue
    }
    if (msg.startsWith('[confirm_plan]')) {
      try {
        const jsonStr = msg.replace('[confirm_plan]', '').trim()
        const parsed = JSON.parse(jsonStr)
        msgs.push({
          id: entry.id,
          role: 'plan_confirm' as ChatRole,
          text: parsed.plan as string ?? jsonStr,
          timestamp: entry.timestamp,
          requestId: parsed.request_id as string,
        })
      } catch {
        const plan = msg.replace('[confirm_plan]', '').trim()
        msgs.push({ id: entry.id, role: 'plan_confirm' as ChatRole, text: plan, timestamp: entry.timestamp })
      }
      continue
    }

    // ── User navigation (first event of a new task) ───────────────────────
    const isUser = entry.stepKind === 'navigate' && entry.elapsedSeconds === 0

    // ── Image/video generation spinner — ONLY for dedicated generation tools ─
    const isGenerating = entry.type === 'step' && RE_GENERATION_TOOL.test(msg)

    // ── Model text response — show as AssistantCard, never as ToolCard ──────
    // Catches: "Model response (no tool call): ..." and bare model output steps
    const isModelResponse = entry.type === 'step' && RE_MODEL_RESPONSE.test(msg)

    // ── Real tool call — bracket-prefixed step messages ─────────────────────
    const isToolCall = entry.type === 'step' && !isUser && !isModelResponse && RE_TOOL_CALL.test(msg)

    // ── Anything else that's a step but not tool-shaped → assistant text ─────
    const isStepText = entry.type === 'step' && !isUser && !isGenerating && !isModelResponse && !isToolCall

    // Strip the "Model response (no tool call):" prefix for cleaner display
    const displayText = isModelResponse
      ? msg.replace(/^Model response\s*\([^)]*\)\s*:\s*/i, '').trim() || msg
      : msg

    if (isGenerating) {
      msgs.push({ id: entry.id, role: 'generating' as ChatRole, text: msg, timestamp: entry.timestamp })
      continue
    }
    if (isUser) {
      msgs.push({ id: entry.id, role: 'user' as ChatRole, text: msg, timestamp: entry.timestamp })
      continue
    }
    if (isModelResponse || isStepText) {
      // These are assistant-side text messages — render as full readable AssistantCard
      msgs.push({ id: entry.id, role: 'assistant' as ChatRole, text: displayText, timestamp: entry.timestamp })
      continue
    }
    if (isToolCall) {
      // Extract tool name from bracket prefix e.g. "[go_to_url] {...}" → "go_to_url"
      const toolMatch = msg.match(/^\[([\w_]+)\]/)
      const toolName = toolMatch?.[1] ?? entry.stepKind
      // Args are everything after the bracket prefix (the JSON args object)
      const argsRaw = msg.replace(/^\[[\w_]+\]\s*/, '').trim()
      let argsFormatted = argsRaw
      try {
        argsFormatted = JSON.stringify(JSON.parse(argsRaw), null, 2)
      } catch { /* keep raw */ }
      msgs.push({
        id: entry.id,
        role: 'tool' as ChatRole,
        text: `[${toolName}]`,
        toolName,
        toolArgs: argsFormatted || undefined,
        toolStatus: entry.status === 'failed' ? 'failed' : entry.status === 'completed' ? 'completed' : 'in_progress',
        timestamp: entry.timestamp,
      })
      continue
    }
    if (entry.type === 'error') {
      msgs.push({ id: entry.id, role: 'assistant' as ChatRole, text: `⚠️ ${msg}`, timestamp: entry.timestamp })
      continue
    }
    // result / interrupt / fallback → assistant text
    msgs.push({ id: entry.id, role: 'assistant' as ChatRole, text: displayText, timestamp: entry.timestamp })
  }

  // ── Auto-complete in_progress tool steps ──────────────────────────────────
  // The backend emits each step when it STARTS, not when it ends, so every tool
  // card arrives as in_progress. Post-process rules:
  //   1. Any tool step that is followed by another message → completed (work moved on)
  //   2. If the task finished (last log entry is result/error), flip all remaining
  //      in_progress tools to completed or failed respectively
  const lastLog = logs[logs.length - 1]
  const taskEnded = lastLog && (lastLog.type === 'result' || lastLog.type === 'error')
  const taskFailed = taskEnded && lastLog.type === 'error'

  for (let i = 0; i < msgs.length; i++) {
    if (msgs[i].role !== 'tool' || msgs[i].toolStatus !== 'in_progress') continue
    const hasSuccessor = i < msgs.length - 1
    if (hasSuccessor) {
      msgs[i] = { ...msgs[i], toolStatus: 'completed' }
    } else if (taskEnded) {
      msgs[i] = { ...msgs[i], toolStatus: taskFailed ? 'failed' : 'completed' }
    }
    // else: still the last message and task is running — keep spinner
  }

  return msgs
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
        <div className='rounded-2xl rounded-tr-sm bg-blue-600 px-3.5 py-2.5 text-sm md:text-xl text-white shadow-md'>
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
        <div className='rounded-2xl rounded-tl-sm border border-[#2a2a2a] bg-[#1a1a1a] px-3.5 py-2.5 text-sm md:text-xl text-zinc-200 shadow-md break-words overflow-wrap-anywhere'>
          {parts.map((part, i) =>
            part.type === 'code' ? (
              <CodeCard key={i} code={part.content} lang={part.lang ?? 'text'} />
            ) : (
              <span key={i} className='whitespace-pre-wrap break-words'>{part.content}</span>
            )
          )}
        </div>
        <p className='mt-0.5 text-[10px] text-zinc-600'>{msg.timestamp}</p>
      </div>
    </div>
  )
}

/** Animated spinner / tick / X that replaces the old text badge */
function ToolStatusIcon({ status }: { status: 'in_progress' | 'completed' | 'failed' }) {
  if (status === 'in_progress') {
    return (
      <span className='relative flex h-4 w-4 flex-shrink-0 items-center justify-center'>
        <span className='absolute inset-0 animate-spin rounded-full border-2 border-blue-500/30 border-t-blue-400' />
      </span>
    )
  }
  if (status === 'completed') {
    return (
      <span className='flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/15'>
        <IcoCheck className='h-2.5 w-2.5 text-emerald-400' />
      </span>
    )
  }
  // failed
  return (
    <span className='flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-red-500/15'>
      <IcoX className='h-2.5 w-2.5 text-red-400' />
    </span>
  )
}

function ToolCard({ msg }: { msg: ChatMessage }) {
  const [expanded, setExpanded] = useState(false)
  const toolName = msg.toolName ?? 'other'
  const icon = TOOL_ICON[toolName] ?? TOOL_ICON.other
  const toolStatus = msg.toolStatus ?? 'in_progress'
  // Human-readable label: convert snake_case to Title Case e.g. "go_to_url" → "Go To URL"
  const toolLabel = toolName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  const hasArgs = Boolean(msg.toolArgs)

  return (
    <div className='flex gap-2.5 mb-1.5'>
      <div className='mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-[#2a2a2a] bg-[#1a1a1a] text-zinc-400'>
        {icon}
      </div>
      <div className='min-w-0 flex-1'>
        <button
          type='button'
          onClick={() => hasArgs && setExpanded((v) => !v)}
          className={`w-full rounded-xl border border-[#2a2a2a] bg-[#141414] px-3 py-2 text-left transition-colors ${hasArgs ? 'cursor-pointer hover:bg-[#1a1a1a]' : 'cursor-default'}`}
        >
          {/* Top row: tool name + status icon + chevron — always one line, never wraps */}
          <div className='flex items-center gap-2'>
            <span className='flex-1 truncate font-mono text-xs font-medium text-zinc-300'>{toolLabel}</span>
            <div className='flex flex-shrink-0 items-center gap-1'>
              <ToolStatusIcon status={toolStatus} />
              {hasArgs && (
                <IcoChevronDown className={`h-3 w-3 text-zinc-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
              )}
            </div>
          </div>
          {/* Args preview — only shown when collapsed and present */}
          {!expanded && msg.toolArgs && (
            <p className='mt-0.5 truncate text-[10px] text-zinc-600'>
              {msg.toolArgs.slice(0, 120)}
            </p>
          )}
          {/* Expanded args */}
          {expanded && msg.toolArgs && (
            <pre className='mt-2 overflow-x-auto rounded-lg bg-[#0d0d0d] p-2 text-[10px] text-zinc-400 font-mono whitespace-pre-wrap break-words'>
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

// ─── User input request card ─────────────────────────────────────────────────
function UserInputCard({
  question,
  options,
  requestId,
  onRespond,
}: {
  question: string
  options: string[]
  requestId: string
  onRespond: (answer: string, requestId: string) => void
}) {
  const [customMode, setCustomMode] = useState(false)
  const [customText, setCustomText] = useState('')
  const [answered, setAnswered] = useState<string | null>(null)

  const handleOption = (opt: string) => {
    if (opt === 'Let me tell you') {
      setCustomMode(true)
      return
    }
    setAnswered(opt)
    onRespond(opt, requestId)
  }

  if (answered) {
    return (
      <div className='rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3'>
        <p className='text-xs text-zinc-400 mb-1'>You answered:</p>
        <p className='text-sm text-emerald-300'>{answered}</p>
      </div>
    )
  }

  return (
    <div className='rounded-xl border border-blue-500/20 bg-[#0f1628] p-4 space-y-3'>
      <div className='flex items-start gap-2'>
        <span className='text-lg'>❓</span>
        <div>
          <p className='text-xs font-medium text-blue-300 mb-1'>Aegis needs your input</p>
          <p className='text-sm text-zinc-200'>{question}</p>
        </div>
      </div>
      {!customMode ? (
        <div className='flex flex-wrap gap-2'>
          {options.map((opt) => (
            <button
              key={opt}
              type='button'
              onClick={() => handleOption(opt)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                opt === 'Let me tell you'
                  ? 'border-zinc-600 bg-[#1a1a1a] text-zinc-400 hover:border-zinc-400 hover:text-zinc-200'
                  : 'border-blue-500/40 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20 hover:border-blue-400'
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <div className='flex gap-2'>
          <input
            autoFocus
            type='text'
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && customText.trim()) {
                setAnswered(customText.trim())
                onRespond(customText.trim(), requestId)
              }
            }}
            placeholder='Type your answer...'
            className='flex-1 rounded-lg border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-blue-500/60'
          />
          <button
            type='button'
            onClick={() => {
              if (customText.trim()) {
                setAnswered(customText.trim())
                onRespond(customText.trim(), requestId)
              }
            }}
            className='rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-500 transition-colors'
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Task summary card ────────────────────────────────────────────────────────
function TaskSummaryCard({ summary }: { summary: string }) {
  return (
    <div className='rounded-xl border border-[#2a2a2a] bg-[#141414] p-4 space-y-2'>
      <div className='flex items-center gap-2 mb-2'>
        <span className='text-lg'>✅</span>
        <p className='text-xs font-semibold text-emerald-300 uppercase tracking-wide'>Task Complete</p>
      </div>
      <div className='text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap'>{summary}</div>
    </div>
  )
}

// ─── Plan confirm card ────────────────────────────────────────────────────────
function PlanConfirmCard({
  plan,
  requestId,
  onConfirm,
  onReject,
}: {
  plan: string
  requestId: string
  onConfirm: (requestId: string) => void
  onReject: (requestId: string) => void
}) {
  const [status, setStatus] = useState<'pending' | 'confirmed' | 'rejected'>('pending')

  if (status !== 'pending') {
    return (
      <div className={`rounded-xl border p-3 text-xs font-medium ${
        status === 'confirmed'
          ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300'
          : 'border-red-500/20 bg-red-500/5 text-red-300'
      }`}>
        Plan {status === 'confirmed' ? 'confirmed ✓' : 'rejected ✗'}
      </div>
    )
  }

  return (
    <div className='rounded-xl border border-amber-500/20 bg-[#1a1500] p-4 space-y-3'>
      <div className='flex items-center gap-2'>
        <span className='text-lg'>📋</span>
        <p className='text-xs font-semibold text-amber-300 uppercase tracking-wide'>Plan ready — confirm to proceed</p>
      </div>
      <div className='text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap'>{plan}</div>
      <div className='flex gap-2 pt-1'>
        <button
          type='button'
          onClick={() => { setStatus('confirmed'); onConfirm(requestId) }}
          className='flex-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors'
        >
          ✓ Confirm Plan
        </button>
        <button
          type='button'
          onClick={() => { setStatus('rejected'); onReject(requestId) }}
          className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-400 hover:bg-red-500/20 transition-colors'
        >
          ✗ Reject
        </button>
      </div>
    </div>
  )
}

// ─── ThinkingCard (ChatGPT-style streaming reasoning dropdown) ────────────────
interface ThinkingCardProps {
  stepId: string
  reasoningText: string
  isStreaming: boolean
}

function ThinkingCard({ stepId: _stepId, reasoningText, isStreaming }: ThinkingCardProps) {
  const [userCollapsed, setUserCollapsed] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const shouldExpand = isStreaming ? !userCollapsed : false
  const [manualExpand, setManualExpand] = useState(false)

  // Auto-scroll while streaming
  useEffect(() => {
    if ((shouldExpand || manualExpand) && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight
    }
  })

  const displayTitle = reasoningText.split('\n')[0]?.slice(0, 60) || 'Thinking…'
  const isOpen = shouldExpand || manualExpand

  return (
    <div className='mb-1.5 overflow-hidden rounded-xl border border-violet-500/20 bg-[#1a1a1a]'>
      <button
        type='button'
        onClick={() => {
          if (isStreaming) {
            setUserCollapsed((v) => !v)
          } else {
            setManualExpand((v) => !v)
          }
        }}
        className='flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-[#2a2a2a] transition-colors'
      >
        {isStreaming ? (
          <span className='flex h-4 w-4 flex-shrink-0 items-center justify-center'>
            <span className='h-3 w-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent' />
          </span>
        ) : (
          <svg className='h-4 w-4 flex-shrink-0 text-violet-400' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
            <path d='M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z'/>
            <path d='M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z'/>
          </svg>
        )}
        <span className='flex-1 truncate text-xs font-medium text-violet-300'>
          {isStreaming ? displayTitle : `Reasoned: ${displayTitle}`}
        </span>
        <svg
          className={`h-3.5 w-3.5 flex-shrink-0 text-zinc-500 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2'
        >
          <path d='M6 9l6 6 6-6' />
        </svg>
      </button>
      {isOpen && (
        <div
          ref={contentRef}
          className='max-h-48 overflow-y-auto px-3 pb-3 pt-1 font-mono text-xs leading-relaxed text-zinc-400 whitespace-pre-wrap'
        >
          {reasoningText || <span className='animate-pulse text-zinc-600'>…</span>}
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
  enableReasoning?: boolean
  onToggleReasoning?: (enabled: boolean) => void
  reasoningEffort?: 'low' | 'medium' | 'high'
  onChangeReasoningEffort?: (effort: 'low' | 'medium' | 'high') => void
  modelSupportsReasoning?: boolean
}

function PlusMenu({ onAttach, onConnector, onClose, enableReasoning, onToggleReasoning, reasoningEffort, onChangeReasoningEffort, modelSupportsReasoning }: PlusMenuProps) {
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

        {/* Think harder — flat list row, only for capable models. Hidden for non-reasoning models. */}
        {modelSupportsReasoning && (
          <>
            <div className='mx-4 my-1 border-t border-[#2a2a2a]' />
            {/* Primary row — lightbulb icon + label + checkmark, tapping toggles */}
            <button
              type='button'
              onClick={() => onToggleReasoning?.(!enableReasoning)}
              className='flex w-full items-center gap-4 rounded-xl px-3 py-2.5 text-left hover:bg-[#2a2a2a] transition-colors'
            >
              <div className='flex h-10 w-10 items-center justify-center rounded-full bg-[#2a2a2a]'>
                {/* Lightbulb icon — provider-neutral "think harder" signal */}
                <svg className='h-5 w-5 text-zinc-200' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
                  <path d='M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5'/>
                  <path d='M9 18h6'/><path d='M10 22h4'/>
                </svg>
              </div>
              <span className='flex-1 text-sm font-medium text-zinc-200'>Think harder</span>
              {/* Checkmark when active */}
              {enableReasoning && (
                <svg className='h-5 w-5 text-zinc-200 flex-shrink-0' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2.5' strokeLinecap='round' strokeLinejoin='round'>
                  <path d='M20 6 9 17l-5-5'/>
                </svg>
              )}
            </button>
            {/* Effort sub-row — only shown when active */}
            {enableReasoning && (
              <div className='flex gap-1.5 px-3 pb-2'>
                {(['low', 'medium', 'high'] as const).map((effort) => (
                  <button
                    key={effort}
                    type='button'
                    onClick={(e) => { e.stopPropagation(); onChangeReasoningEffort?.(effort) }}
                    className={`flex-1 rounded-lg py-1 text-xs font-medium capitalize transition-colors ${
                      reasoningEffort === effort
                        ? 'bg-violet-600 text-white'
                        : 'bg-[#2a2a2a] text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {effort}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

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
  onUserInputResponse,
  onPlanConfirm,
  onPlanReject,
  reasoningMap,
  enableReasoning,
  onToggleReasoning,
  reasoningEffort,
  onChangeReasoningEffort,
  currentModelSupportsReasoning,
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
          if (msg.role === 'user_input') {
            return (
              <UserInputCard
                key={msg.id}
                question={msg.question ?? msg.text}
                options={msg.options ?? []}
                requestId={msg.requestId ?? msg.id}
                onRespond={(answer, reqId) => {
                  onUserInputResponse?.(answer, reqId)
                  onSend(answer, 'steer')
                }}
              />
            )
          }
          if (msg.role === 'task_summary') return <TaskSummaryCard key={msg.id} summary={msg.text} />
          if (msg.role === 'plan_confirm') {
            return (
              <PlanConfirmCard
                key={msg.id}
                plan={msg.text}
                requestId={msg.requestId ?? msg.id}
                onConfirm={(reqId) => {
                  onPlanConfirm?.(reqId)
                  onSend('confirmed', 'steer')
                }}
                onReject={(reqId) => {
                  onPlanReject?.(reqId)
                  onSend('rejected', 'steer')
                }}
              />
            )
          }
          if (msg.role === 'thinking') {
            const stepId = msg.stepId ?? ''
            const reasoningText = reasoningMap?.[stepId] ?? msg.text ?? ''
            const isStreaming = isWorking && reasoningText.length < 3
            return (
              <div key={msg.id} className='flex justify-start px-2 py-0.5'>
                <div className='w-full max-w-[85%]'>
                  <ThinkingCard
                    stepId={stepId}
                    reasoningText={reasoningText}
                    isStreaming={isStreaming}
                  />
                </div>
              </div>
            )
          }
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
            enableReasoning={enableReasoning}
            onToggleReasoning={onToggleReasoning}
            reasoningEffort={reasoningEffort}
            onChangeReasoningEffort={onChangeReasoningEffort}
            modelSupportsReasoning={currentModelSupportsReasoning}
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
              className='w-full resize-none overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2 text-sm md:text-xl text-zinc-200 placeholder:text-zinc-600 outline-none focus:border-blue-500/60 disabled:opacity-40 transition-colors leading-6'
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
