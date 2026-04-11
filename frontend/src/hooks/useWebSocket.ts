import { useCallback, useEffect, useRef, useState } from 'react'
import { IncrementalTextNormalizer, normalizeTextPreservingMarkdown } from '../lib/textNormalization'
import { createIdleActivityState, reduceActivityState, selectActivityView, type ActivitySelector, type ActivityState } from '../lib/activityState'
import { modeLabel, parseModeRuntimeEvent, type AgentModeId } from '../lib/agentModes'

export type SteeringMode = 'auto' | 'steer' | 'interrupt' | 'queue'

export type ActivityPhase = 'idle' | 'thinking' | 'browsing' | 'calling_tool' | 'generating'
export type ExecutionState = 'idle' | 'starting' | 'running' | 'completed' | 'failed' | 'cancelled'

export type TaskActivity = {
  phase: ActivityPhase
  detail?: string
  updatedAt: string
}

export type LogEntry = {
  id: string
  taskId: string
  message: string
  timestamp: string
  type: 'step' | 'result' | 'error' | 'interrupt' | 'reasoning_start' | 'reasoning'
  status: 'in_progress' | 'completed' | 'failed' | 'steered'
  stepKind: 'analyze' | 'click' | 'type' | 'scroll' | 'navigate' | 'other'
  elapsedSeconds: number
  stepId?: string           // links reasoning to its step
  isUserMessage?: boolean   // true when this entry represents the user's task instruction
  isStreaming?: boolean      // true while stream_chunk deltas are still arriving
  rawStepType?: string       // original step type string from backend
  toolCallId?: string        // call_id linking tool_start → tool_result
  toolResult?: string        // resolved result text for tool_result entries
  toolOk?: boolean           // whether the tool call succeeded
}

export type TranscriptEntry = {
  id: string
  text: string
  timestamp: string
  source: 'voice' | 'system'
}

export type WorkflowStep = {
  step_id: string
  parent_step_id: string | null
  action: string
  description: string
  status: 'in_progress' | 'completed' | 'failed' | 'steered'
  timestamp: string
  duration_ms: number
  screenshot: string | null
}

export type SubAgentInfo = {
  sub_id: string
  instruction: string
  model: string
  status: 'spawning' | 'running' | 'completed' | 'failed' | 'cancelled'
  step_count: number
  parent_task_id?: string
}

export type SubAgentStep = {
  sub_id: string
  step: { type: string; content: string }
  step_index: number
  parent_task_id?: string
}

type ThinkingState = 'streaming' | 'completed'

export interface PersistedThinkingMessage {
  id: string
  role: 'thinking'
  taskId: string
  stepId: string
  status: ThinkingState
  text: string
  updatedAt: string
}

export type WebSocketPayload = {
  type: 'step' | 'result' | 'frame' | 'error' | 'interrupt' | 'workflow_step' | 'screenshot' | 'transcript' | 'usage' | 'usage_tick' | 'context_update' | 'conversation_id' | 'reasoning_start' | 'reasoning_delta' | 'reasoning' | 'tool-call' | 'subagent_spawned' | 'subagent_step' | 'subagent_completed' | 'subagent_error' | 'subagent_cancelled' | 'subagent_list' | 'mode_event' | 'mode_event_parse_failed' | 'navigate_ack' | 'task_state' | 'task_result' | 'task_error' | 'pong'
  data?: Record<string, unknown>
  [key: string]: unknown
}

const THINKING_KEY = (taskId: string) => `aegis.reasoning.${taskId}`
const FRAME_CACHE_PREFIX = 'aegis.frame.'
const FRAME_CACHE_KEY = (scopeKey: string) => `${FRAME_CACHE_PREFIX}${scopeKey}`

function readPersistedFrame(scopeKey: string): string {
  if (!scopeKey || typeof window === 'undefined') return ''
  try {
    return window.localStorage.getItem(FRAME_CACHE_KEY(scopeKey)) ?? ''
  } catch {
    return ''
  }
}

function persistFrame(scopeKey: string, frameDataUrl: string): void {
  if (!scopeKey || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(FRAME_CACHE_KEY(scopeKey), frameDataUrl)
  } catch {
    // Ignore localStorage quota/sandbox issues.
  }
}

function removePersistedFrame(scopeKey: string): void {
  if (!scopeKey || typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(FRAME_CACHE_KEY(scopeKey))
  } catch {
    // Ignore localStorage access issues.
  }
}

function clearPersistedFrameCache(): void {
  if (typeof window === 'undefined') return
  try {
    const keysToDelete: string[] = []
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index)
      if (key && key.startsWith(FRAME_CACHE_PREFIX)) {
        keysToDelete.push(key)
      }
    }
    keysToDelete.forEach((key) => window.localStorage.removeItem(key))
  } catch {
    // Ignore localStorage access issues.
  }
}

function readPersistedThinking(taskId: string): PersistedThinkingMessage[] {
  if (!taskId || typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(THINKING_KEY(taskId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item): item is PersistedThinkingMessage => {
        const candidate = item as Partial<PersistedThinkingMessage>
        return Boolean(
          candidate
          && candidate.role === 'thinking'
          && typeof candidate.taskId === 'string'
          && typeof candidate.stepId === 'string'
          && typeof candidate.id === 'string',
        )
      })
      .map((item) => ({
        ...item,
        status: item.status === 'completed' ? 'completed' : 'streaming',
        text: typeof item.text === 'string' ? item.text : '',
        updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : new Date().toISOString(),
      }))
  } catch {
    return []
  }
}

function persistThinking(taskId: string, messages: PersistedThinkingMessage[]): void {
  if (!taskId || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(THINKING_KEY(taskId), JSON.stringify(messages))
  } catch {
    // Ignore localStorage quota/sandbox issues.
  }
}

function guessStepKind(message: string): LogEntry['stepKind'] {
  const text = message.toLowerCase()
  if (text.includes('analy')) return 'analyze'
  if (text.includes('click')) return 'click'
  if (text.includes('type')) return 'type'
  if (text.includes('scroll')) return 'scroll'
  if (text.includes('navigat') || text.includes('url') || text.includes('http')) return 'navigate'
  return 'other'
}

type UseWebSocketOptions = {
  onUsageMessage?: (msg: Record<string, unknown>) => void
  userId?: string | null
  activeThreadId?: string | null
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const onUsageMessage = options?.onUsageMessage
  const userId = options?.userId ?? null
  const activeThreadId = options?.activeThreadId ?? null
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [opsConnectionStatus, setOpsConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const [executionState, setExecutionState] = useState<ExecutionState>('idle')
  const [isWorking, setIsWorking] = useState(false)
  const [taskActivity, setTaskActivity] = useState<ActivityState>(() => createIdleActivityState())
  const [latestFrame, setLatestFrame] = useState('')
  const [activityView, setActivityView] = useState<ActivitySelector>(() => selectActivityView(createIdleActivityState(), false))
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([])
  const [currentUrl, setCurrentUrl] = useState('about:blank')
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([])
  // Server-assigned conversation ID for the active session - used to load history from DB
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  // Maps step_id → accumulated reasoning text
  const [reasoningMap, setReasoningMap] = useState<Record<string, string>>({})
  // Sub-agents
  const [subAgents, setSubAgents] = useState<SubAgentInfo[]>([])
  const [subAgentSteps, setSubAgentSteps] = useState<Record<string, SubAgentStep[]>>({})
  const [activeExecutionMode, setActiveExecutionMode] = useState<AgentModeId>('orchestrator')
  const wsRef = useRef<WebSocket | null>(null)
  const opsWsRef = useRef<WebSocket | null>(null)
  const _sessionIdRef = useRef<string>(crypto.randomUUID())
  const reconnectRef = useRef<number | null>(null)
  const pingIntervalRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef(true)
  const activeTaskIdRef = useRef('idle')
  const activeFrameScopeKeyRef = useRef('')
  const reasoningNormalizersRef = useRef<Record<string, IncrementalTextNormalizer>>({})
  const lastStepAtRef = useRef(0)
  const lastNotConnectedAtRef = useRef(0)
  const connectRef = useRef<() => void>(() => undefined)
  const pendingStartRef = useRef<{ requestId: string; timer: number | null; instruction: string } | null>(null)
  const pendingQueuedStateTimeoutRef = useRef<number | null>(null)
  const ackTimeoutMs = Number(import.meta.env.VITE_NAVIGATE_ACK_TIMEOUT_MS ?? 5000)
  const queuedTimeoutMs = Number(import.meta.env.VITE_NAVIGATE_QUEUED_TIMEOUT_MS ?? 20000)

  const appendLog = useCallback(
    (entry: Omit<LogEntry, 'id' | 'timestamp' | 'elapsedSeconds' | 'stepKind'> & { elapsedSeconds?: number; stepKind?: LogEntry['stepKind'] }) => {
      const now = performance.now()
      const elapsed =
        entry.elapsedSeconds ?? (lastStepAtRef.current > 0 ? (now - lastStepAtRef.current) / 1000 : 0)
      lastStepAtRef.current = now
      setLogs((prev) => [
        ...prev,
        {
          ...entry,
          id: crypto.randomUUID(),
          timestamp: new Date().toLocaleTimeString(),
          elapsedSeconds: elapsed,
          stepKind: entry.stepKind ?? guessStepKind(entry.message),
        },
      ])
    },
    [],
  )

  useEffect(() => {
    const normalizedUserId = (userId ?? '').trim() || 'anon'
    const normalizedThreadId = (activeThreadId ?? '').trim()
    const scopeKey = normalizedThreadId ? `${normalizedUserId}:${normalizedThreadId}` : ''
    activeFrameScopeKeyRef.current = scopeKey
    setLatestFrame(scopeKey ? readPersistedFrame(scopeKey) : '')
  }, [activeThreadId, userId])

  const connect = useCallback(function connectSocket() {
    setConnectionStatus('connecting')
    const configuredWsUrl = (import.meta.env.VITE_WS_URL as string | undefined)?.trim()
    const apiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
    let wsUrl = configuredWsUrl && configuredWsUrl.length > 0 ? configuredWsUrl : ''
    if (!wsUrl && apiUrl) {
      try {
        const parsed = new URL(apiUrl)
        const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
        let basePath = parsed.pathname.replace(/\/+$/, '')
        if (basePath.endsWith('/api')) {
          basePath = basePath.slice(0, -4)
        }
        wsUrl = `${protocol}//${parsed.host}${basePath}/ws/agent`
      } catch {
        wsUrl = ''
      }
    }
    if (!wsUrl) {
      wsUrl = `${window.location.origin.replace('http', 'ws')}/ws/agent`
    }
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus('connected')
      // Client-side keepalive ping every 25s to prevent proxy idle-timeout drops
      if (pingIntervalRef.current !== null) window.clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = window.setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ action: 'ping' }))
        }
      }, 25000)
    }
    ws.onclose = () => {
      if (pendingQueuedStateTimeoutRef.current !== null) {
        window.clearTimeout(pendingQueuedStateTimeoutRef.current)
        pendingQueuedStateTimeoutRef.current = null
      }
      const pendingStart = pendingStartRef.current
      if (pendingStart && pendingStart.timer !== null) {
        window.clearTimeout(pendingStart.timer)
      }
      pendingStartRef.current = null
      if (pingIntervalRef.current !== null) {
        window.clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = null
      }
      setConnectionStatus('disconnected')
      setIsWorking(false)
      if (shouldReconnectRef.current) {
        if (reconnectRef.current !== null) {
          window.clearTimeout(reconnectRef.current)
        }
        reconnectRef.current = window.setTimeout(() => connectRef.current(), 1500)
      }
    }
    ws.onerror = () => {
      if (pingIntervalRef.current !== null) {
        window.clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = null
      }
      setConnectionStatus('disconnected')
    }
    ws.onmessage = (event: MessageEvent<string>) => {
      let payload: WebSocketPayload
      try {
        payload = JSON.parse(event.data) as WebSocketPayload
      } catch {
        appendLog({
          message: 'Failed to parse websocket message; ignoring malformed payload.',
          taskId: activeTaskIdRef.current,
          type: 'error',
          status: 'failed',
        })
        return
      }
      const taskId = activeTaskIdRef.current
      setTaskActivity((prev) => reduceActivityState(prev, payload, Date.now()))

      if (payload.type === 'conversation_id') {
        const convId = String(payload.data?.conversation_id ?? '')
        if (convId) setActiveConversationId(convId)
        return
      }
      if (payload.type === 'navigate_ack') {
        const accepted = Boolean(payload.data?.accepted)
        const requestId = String(payload.data?.request_id ?? '')
        if (pendingStartRef.current?.requestId === requestId && pendingStartRef.current.timer !== null) {
          window.clearTimeout(pendingStartRef.current.timer)
          pendingStartRef.current = null
        }
        if (!accepted) {
          setExecutionState('failed')
          setIsWorking(false)
          appendLog({ message: `Start rejected: ${String(payload.data?.reason ?? 'unknown')}`, taskId: activeTaskIdRef.current, type: 'error', status: 'failed' })
          return
        }
        if (pendingQueuedStateTimeoutRef.current !== null) {
          window.clearTimeout(pendingQueuedStateTimeoutRef.current)
          pendingQueuedStateTimeoutRef.current = null
        }
        setExecutionState('running')
        return
      }
      if (payload.type === 'task_state') {
        const state = String(payload.data?.state ?? '')
        if (state === 'running' || state === 'tool_call' || state === 'queued' || state === 'waiting_input') {
          setExecutionState(state === 'queued' ? 'starting' : 'running')
          setIsWorking(true)
          if (state === 'queued') {
            if (pendingQueuedStateTimeoutRef.current !== null) {
              window.clearTimeout(pendingQueuedStateTimeoutRef.current)
            }
            pendingQueuedStateTimeoutRef.current = window.setTimeout(() => {
              setExecutionState('failed')
              setIsWorking(false)
              appendLog({ message: 'Task stayed queued too long (E_START_TIMEOUT). Retry from chat.', taskId: activeTaskIdRef.current, type: 'error', status: 'failed' })
            }, queuedTimeoutMs)
          } else if (pendingQueuedStateTimeoutRef.current !== null) {
            window.clearTimeout(pendingQueuedStateTimeoutRef.current)
            pendingQueuedStateTimeoutRef.current = null
          }
        } else if (state === 'succeeded') {
          setExecutionState('completed')
          setIsWorking(false)
        } else if (state === 'failed') {
          setExecutionState('failed')
          setIsWorking(false)
        } else if (state === 'cancelled') {
          setExecutionState('cancelled')
          setIsWorking(false)
        }
        return
      }
      if (payload.type === 'task_result') {
        if (pendingQueuedStateTimeoutRef.current !== null) {
          window.clearTimeout(pendingQueuedStateTimeoutRef.current)
          pendingQueuedStateTimeoutRef.current = null
        }
        setExecutionState('completed')
        setIsWorking(false)
        // The model's actual response was already emitted as a step — don't double-print.
        // Only surface a fallback summary if no step content came through.
        return
      }
      if (payload.type === 'task_error') {
        if (pendingQueuedStateTimeoutRef.current !== null) {
          window.clearTimeout(pendingQueuedStateTimeoutRef.current)
          pendingQueuedStateTimeoutRef.current = null
        }
        setExecutionState('failed')
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Task failed'), taskId, type: 'error', status: 'failed' })
        return
      }
      if (payload.type === 'step') {
        const stepType = String(payload.data?.type ?? '').toLowerCase()
        const nonExecutionStepTypes = new Set(['queue', 'steer', 'config'])
        if (!nonExecutionStepTypes.has(stepType)) {
          setIsWorking(true)
        }
        const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
        const urlMatch = content.match(/https?:\/\/[^\s)]+/)
        if (urlMatch?.[0]) setCurrentUrl(urlMatch[0])

        // ── stream_chunk: accumulate token deltas into a streaming bubble ──
        if (stepType === 'stream_chunk') {
          const msgId = String(payload.data?.message_id ?? '')
          const delta = String(payload.data?.content ?? '')
          setLogs((prev) => {
            const existing = prev.find((e) => e.id === `stream_${msgId}`)
            if (existing) {
              return prev.map((e) =>
                e.id === `stream_${msgId}` ? { ...e, message: e.message + delta } : e,
              )
            }
            return [
              ...prev,
              {
                id: `stream_${msgId}`,
                message: delta,
                taskId,
                type: 'result' as const,
                status: 'in_progress' as const,
                stepKind: 'other' as const,
                elapsedSeconds: 0,
                timestamp: new Date().toISOString(),
                isStreaming: true,
                rawStepType: 'stream_chunk',
              },
            ]
          })
          return
        }

        // ── stream_done: mark bubble as complete ───────────────────────────
        if (stepType === 'stream_done') {
          const msgId = String(payload.data?.message_id ?? '')
          setLogs((prev) =>
            prev.map((e) =>
              e.id === `stream_${msgId}`
                ? { ...e, isStreaming: false, status: 'completed' as const }
                : e,
            ),
          )
          return
        }

        // ── tool_start: emit card with spinner ─────────────────────────────
        if (stepType === 'tool_start') {
          try {
            const data = JSON.parse(content) as { call_id?: string }
            appendLog({
              message: content,
              taskId,
              type: 'step',
              status: 'in_progress',
              rawStepType: 'tool_start',
              toolCallId: data.call_id,
            })
          } catch {
            appendLog({ message: content, taskId, type: 'step', status: 'in_progress', rawStepType: 'tool_start' })
          }
          return
        }

        // ── tool_result: resolve matching tool_start card ──────────────────
        // If the result arrives before the start (out-of-order / race), buffer it
        // and apply once the start card appears via a follow-up setState.
        if (stepType === 'tool_result') {
          try {
            const data = JSON.parse(content) as { call_id?: string; result?: string; ok?: boolean }
            setLogs((prev) => {
              const matched = prev.some((e) => e.toolCallId === data.call_id)
              if (matched) {
                // Normal case: start card exists — resolve it
                return prev.map((e) =>
                  e.toolCallId === data.call_id
                    ? { ...e, status: 'completed' as const, rawStepType: 'tool_result', toolResult: data.result, toolOk: data.ok }
                    : e,
                )
              }
              // Out-of-order: synthesise a completed card so no spinner is ever left hanging
              return [
                ...prev,
                {
                  id: `tool_${data.call_id ?? crypto.randomUUID()}`,
                  message: content,
                  taskId,
                  type: 'step' as const,
                  status: 'completed' as const,
                  stepKind: 'other' as const,
                  elapsedSeconds: 0,
                  timestamp: new Date().toISOString(),
                  rawStepType: 'tool_result',
                  toolCallId: data.call_id,
                  toolResult: data.result,
                  toolOk: data.ok,
                },
              ]
            })
          } catch { /* ignore malformed */ }
          return
        }

        // ── assistant_message = direct model text reply (no tools used); treat as a
        // completed result so ChatPanel renders it as a plain assistant bubble.
        // The frontend deduplicates against stream_chunk entries by message_id.
        const isAssistantMsg = stepType === 'assistant_message' || stepType === 'result'
        appendLog({
          message: content,
          taskId,
          type: stepType === 'interrupt' ? 'interrupt' : isAssistantMsg ? 'result' : 'step',
          status: isAssistantMsg ? 'completed' : stepType === 'steer' ? 'steered' : 'in_progress',
          rawStepType: stepType,
        })
        return
      }
      if (payload.type === 'interrupt') {
        setIsWorking(false)
        appendLog({
          message: String(payload.data?.message ?? 'Task interrupted'),
          taskId,
          type: 'interrupt',
          status: 'completed',
        })
        return
      }
      if (payload.type === 'tool-call') {
        setIsWorking(true)
        appendLog({
          message: String(payload.data?.content ?? payload.data?.tool ?? 'Tool call'),
          taskId,
          type: 'step',
          status: 'in_progress',
        })
        return
      }
      if (payload.type === 'result') {
        setIsWorking(false)
        setExecutionState('completed')
        const persisted = readPersistedThinking(taskId)
        if (persisted.length > 0) {
          const nowIso = new Date().toISOString()
          const next = persisted.map((item) => (
            item.status === 'streaming'
              ? { ...item, status: 'completed' as const, updatedAt: nowIso }
              : item
          ))
          persistThinking(taskId, next)
        }
        const status = String(payload.data?.status ?? 'completed')
        const failed = status !== 'completed' && status !== 'interrupted'
        appendLog({
          message: `Task ${status}`,
          taskId,
          type: status === 'interrupted' ? 'interrupt' : failed ? 'error' : 'result',
          status: failed ? 'failed' : 'completed',
        })
        return
      }
      if (payload.type === 'frame') {
        const image = String(payload.data?.image ?? '')
        const frameDataUrl = image ? `data:image/png;base64,${image}` : ''
        const scopeKey = activeFrameScopeKeyRef.current
        if (frameDataUrl && scopeKey) {
          persistFrame(scopeKey, frameDataUrl)
          setLatestFrame(frameDataUrl)
        }
        return
      }
      if (payload.type === 'screenshot') {
        const image = String(payload.data ?? '')
        const frameDataUrl = image ? `data:image/png;base64,${image}` : ''
        const scopeKey = activeFrameScopeKeyRef.current
        if (frameDataUrl && scopeKey) {
          persistFrame(scopeKey, frameDataUrl)
          setLatestFrame(frameDataUrl)
        }
        return
      }
      if (payload.type === 'workflow_step') {
        const step = payload.data as WorkflowStep
        setWorkflowSteps((prev) => [...prev.filter((item) => item.step_id !== step.step_id), step])
        return
      }
      if (payload.type === 'mode_event') {
        const parsed = parseModeRuntimeEvent(payload.data)
        if (!parsed.ok) {
          appendLog({
            message: `Mode event parse failed (${parsed.error}); falling back to raw event stream.`,
            taskId,
            type: 'error',
            status: 'failed',
          })
          return
        }
        const modeEvent = parsed.event
        if (modeEvent.event_name === 'route_decision') {
          setActiveExecutionMode(modeEvent.payload.selected_mode)
          setTaskActivity((prev) => ({
            ...prev,
            phase: 'thinking',
            detail: `Routing to ${modeLabel(modeEvent.payload.selected_mode)} mode`,
            updatedAt: new Date().toISOString(),
            lastEventAt: Date.now(),
          }))
          appendLog({
            message: `Route decision: ${modeLabel(modeEvent.payload.selected_mode)} (${modeEvent.payload.reason})`,
            taskId,
            type: 'step',
            status: 'in_progress',
          })
          return
        }
        if (modeEvent.event_name === 'mode_transition') {
          setActiveExecutionMode(modeEvent.payload.to_mode)
          setTaskActivity((prev) => ({
            ...prev,
            phase: 'thinking',
            detail: `${modeLabel(modeEvent.payload.from_mode)} → ${modeLabel(modeEvent.payload.to_mode)}`,
            updatedAt: new Date().toISOString(),
            lastEventAt: Date.now(),
          }))
          return
        }
        if (modeEvent.event_name === 'worker_summary') {
          setActiveExecutionMode(modeEvent.payload.worker_mode)
          appendLog({
            message: `${modeLabel(modeEvent.payload.worker_mode)} summary: ${modeEvent.payload.summary || modeEvent.payload.status}`,
            taskId,
            type: 'result',
            status: modeEvent.payload.status === 'failed' ? 'failed' : 'completed',
          })
          return
        }
        if (modeEvent.event_name === 'final_synthesis') {
          setActiveExecutionMode('orchestrator')
          setTaskActivity((prev) => ({
            ...prev,
            phase: 'generating',
            detail: 'Orchestrator final synthesis',
            updatedAt: new Date().toISOString(),
            lastEventAt: Date.now(),
          }))
          appendLog({
            message: `Final synthesis: ${modeEvent.payload.status}`,
            taskId,
            type: modeEvent.payload.status === 'failed' ? 'error' : 'result',
            status: modeEvent.payload.status === 'failed' ? 'failed' : 'completed',
          })
          return
        }
      }
      if (payload.type === 'mode_event_parse_failed') {
        appendLog({
          message: `Mode event parse failed on server (${String(payload.data?.error ?? 'unknown')}); using safe fallback.`,
          taskId,
          type: 'error',
          status: 'failed',
        })
        return
      }
      if (payload.type === 'transcript') {
        const text = String(payload.data?.text ?? '').trim()
        if (text) {
          const source = String(payload.data?.source ?? 'voice') === 'system' ? 'system' : 'voice'
          setTranscripts((prev) => {
            const entry: TranscriptEntry = {
              id: crypto.randomUUID(),
              text,
              timestamp: new Date().toLocaleTimeString(),
              source,
            }
            const next = [...prev, entry]
            return next.length > 5 ? next.slice(next.length - 5) : next
          })
        }
        return
      }
      if (payload.type === 'usage' || payload.type === 'usage_tick') {
        onUsageMessage?.(payload as unknown as Record<string, unknown>)
        return
      }
      if (payload.type === 'context_update') {
        onUsageMessage?.(payload as unknown as Record<string, unknown>)
        return
      }
      if (payload.type === 'reasoning_start') {
        const stepId = String(payload.data?.step_id ?? '')
        if (stepId) {
          if (!reasoningNormalizersRef.current[stepId]) {
            reasoningNormalizersRef.current[stepId] = new IncrementalTextNormalizer()
          }
          setReasoningMap((prev) => ({ ...prev, [stepId]: prev[stepId] ?? '' }))
          const nowIso = new Date().toISOString()
          const persisted = readPersistedThinking(taskId)
          const existing = persisted.find((item) => item.stepId === stepId)
          const nextEntry: PersistedThinkingMessage = {
            id: `thinking-${taskId}-${stepId}`,
            role: 'thinking',
            taskId,
            stepId,
            status: 'streaming',
            text: existing?.text ?? '',
            updatedAt: nowIso,
          }
          const next = [
            ...persisted.filter((item) => item.stepId !== stepId),
            nextEntry,
          ]
          persistThinking(taskId, next)
        }
        return
      }
      if (payload.type === 'reasoning_delta') {
        const stepId = String(payload.data?.step_id ?? '')
        const delta = String(payload.data?.delta ?? '')
        if (stepId && delta) {
          const normalizer = reasoningNormalizersRef.current[stepId] ?? new IncrementalTextNormalizer()
          reasoningNormalizersRef.current[stepId] = normalizer
          const normalizedCumulative = normalizer.push(delta)
          const normalizedDelta = normalizeTextPreservingMarkdown(delta)
          setReasoningMap((prev) => ({
            ...prev,
            [stepId]: normalizedCumulative,
          }))
          const nowIso = new Date().toISOString()
          const persisted = readPersistedThinking(taskId)
          const existing = persisted.find((item) => item.stepId === stepId)
          const nextEntry: PersistedThinkingMessage = existing
            ? {
                ...existing,
                status: existing.status === 'completed' ? 'completed' : 'streaming',
                text: normalizedCumulative,
                updatedAt: nowIso,
              }
            : {
                id: `thinking-${taskId}-${stepId}`,
                role: 'thinking',
                taskId,
                stepId,
                status: 'streaming',
                text: normalizedDelta,
                updatedAt: nowIso,
              }
          const next = [
            ...persisted.filter((item) => item.stepId !== stepId),
            nextEntry,
          ]
          persistThinking(taskId, next)
        }
        return
      }
      if (payload.type === 'reasoning') {
        // Full reasoning result - update log entry status
        const stepId = String(payload.data?.step_id ?? '')
        const content = String(payload.data?.content ?? '')
        if (stepId) {
          const normalizer = reasoningNormalizersRef.current[stepId]
          const finalContent = content ? normalizeTextPreservingMarkdown(content) : (normalizer?.finalize() ?? '')
          const nowIso = new Date().toISOString()
          const persisted = readPersistedThinking(taskId)
          const existing = persisted.find((item) => item.stepId === stepId)
          const nextEntry: PersistedThinkingMessage = existing
            ? { ...existing, text: finalContent || existing.text, status: 'completed', updatedAt: nowIso }
            : {
                id: `thinking-${taskId}-${stepId}`,
                role: 'thinking',
                taskId,
                stepId,
                status: 'completed',
                text: finalContent,
                updatedAt: nowIso,
              }
          const next = [
            ...persisted.filter((item) => item.stepId !== stepId),
            nextEntry,
          ]
          persistThinking(taskId, next)
          setLogs((prev) =>
            prev.map((e) =>
              e.stepId === stepId
                ? { ...e, type: 'reasoning', status: 'completed', message: finalContent }
                : e,
            ),
          )
          delete reasoningNormalizersRef.current[stepId]
        }
        return
      }
      if (payload.type === 'subagent_list') {
        const agents = (payload.data?.agents ?? []) as SubAgentInfo[]
        setSubAgents(agents)
        return
      }
      if (payload.type === 'subagent_spawned') {
        const agent = payload.data as unknown as SubAgentInfo
        // Prefer parent_task_id from the payload (set by backend from frontend_task_id),
        // falling back to the current active task ID tracked client-side.
        const parentTaskId = (payload.data as Record<string, unknown>)['parent_task_id'] as string | undefined ?? activeTaskIdRef.current
        setSubAgents((prev) => {
          const exists = prev.find((a) => a.sub_id === agent.sub_id)
          if (exists) return prev
          return [...prev, { ...agent, status: 'spawning', step_count: 0, parent_task_id: parentTaskId }]
        })
        return
      }
      if (payload.type === 'subagent_step') {
        const { sub_id, step, step_index } = payload.data as unknown as SubAgentStep
        const parentTaskId = activeTaskIdRef.current
        setSubAgentSteps((prev) => ({
          ...prev,
          [sub_id]: [...(prev[sub_id] ?? []), { sub_id, step, step_index, parent_task_id: parentTaskId }],
        }))
        setSubAgents((prev) =>
          prev.map((a) => a.sub_id === sub_id ? { ...a, status: 'running', step_count: (step_index ?? 0) + 1, parent_task_id: a.parent_task_id ?? parentTaskId } : a)
        )
        return
      }
      if (payload.type === 'subagent_completed') {
        const { sub_id, status } = payload.data as { sub_id: string; status: string; step_count: number }
        setSubAgents((prev) =>
          prev.map((a) => a.sub_id === sub_id ? { ...a, status: status as SubAgentInfo['status'] } : a)
        )
        return
      }
      if (payload.type === 'subagent_error') {
        const { sub_id } = payload.data as { sub_id: string; message: string }
        setSubAgents((prev) =>
          prev.map((a) => a.sub_id === sub_id ? { ...a, status: 'failed' } : a)
        )
        return
      }
      if (payload.type === 'subagent_cancelled') {
        const { sub_id } = payload.data as { sub_id: string }
        setSubAgents((prev) => prev.filter((a) => a.sub_id !== sub_id))
        return
      }
      if (payload.type === 'error') {
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), taskId, type: 'error', status: 'failed' })
        return
      }
    }
  }, [appendLog, onUsageMessage])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    shouldReconnectRef.current = true
    const connectTimeout = window.setTimeout(() => connect(), 0)
    return () => {
      window.clearTimeout(connectTimeout)
      shouldReconnectRef.current = false
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current)
        reconnectRef.current = null
      }
      if (pingIntervalRef.current !== null) {
        window.clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  // ─── Ops WebSocket (port 8001) ────────────────────────────────────────────
  const connectOps = useCallback(function connectOpsSocket() {
    setOpsConnectionStatus('connecting')
    const configuredOpsUrl = (import.meta.env.VITE_OPS_WS_URL as string | undefined)?.trim()
    let opsUrl = configuredOpsUrl && configuredOpsUrl.length > 0 ? configuredOpsUrl : ''
    if (!opsUrl) {
      // Derive from current location: swap protocol and replace port 8000 → 8001
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.hostname
      const opsPort = (import.meta.env.VITE_OPS_PORT as string | undefined)?.trim() || '8001'
      opsUrl = `${protocol}//${host}:${opsPort}/ws/ops`
    }
    const ows = new WebSocket(`${opsUrl}?session_id=${_sessionIdRef.current}`)
    opsWsRef.current = ows

    ows.onopen = () => {
      setOpsConnectionStatus('connected')
    }
    ows.onclose = () => {
      setOpsConnectionStatus('disconnected')
    }
    ows.onerror = () => {
      setOpsConnectionStatus('disconnected')
    }
    ows.onmessage = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as Record<string, unknown>
        if (payload.type === 'ops_ready') {
          // Ops channel confirmed — session_id echoed back from server
          setOpsConnectionStatus('connected')
        } else if (payload.type === 'background_task_result') {
          // Background task completed — consumers can subscribe via their own state
        } else if (payload.type === 'heartbeat_triggered') {
          // Heartbeat notification — no UI action needed here
        } else if (payload.type === 'subagent_result') {
          // Sub-agent list update delivered via ops channel
          const data = payload.data as Record<string, unknown> | undefined
          if (data?.agents) {
            setSubAgents(data.agents as SubAgentInfo[])
          }
        }
      } catch {
        // Ignore malformed messages
      }
    }
  }, [])

  useEffect(() => {
    connectOps()
    return () => {
      if (opsWsRef.current) {
        opsWsRef.current.onclose = null
        opsWsRef.current.close()
        opsWsRef.current = null
      }
    }
  }, [connectOps])

  const send = useCallback(
    (message: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        if (message.action === 'navigate' || message.action === 'task' || message.action === 'chat' || message.action === 'message') {
          const nextTaskId = crypto.randomUUID()
          const requestId = crypto.randomUUID()
          activeTaskIdRef.current = nextTaskId
          setExecutionState('starting')
          setIsWorking(true)
          setTaskActivity((prev) => ({ ...prev, phase: 'thinking', detail: String(message.instruction ?? 'New task'), updatedAt: new Date().toISOString(), lastEventAt: Date.now() }))
          appendLog({
            message: String(message.instruction ?? 'New task'),
            taskId: nextTaskId,
            type: 'step',
            status: 'in_progress',
            stepKind: 'navigate',
            elapsedSeconds: 0,
            isUserMessage: true,
          })
          const maybeUrl = String(message.instruction ?? '')
          if (/^https?:\/\//i.test(maybeUrl)) setCurrentUrl(maybeUrl)
          // Embed frontend task ID in metadata so backend can scope sub-agents to this task
          const existingMeta = (message.metadata as Record<string, unknown> | undefined) ?? {}
          const pendingStart = pendingStartRef.current
          if (pendingStart && pendingStart.timer !== null) {
            window.clearTimeout(pendingStart.timer)
          }
          const timer = window.setTimeout(() => {
            setExecutionState('failed')
            setIsWorking(false)
            appendLog({ message: 'Start timed out (E_START_TIMEOUT). Retry from chat.', taskId: nextTaskId, type: 'error', status: 'failed' })
            pendingStartRef.current = null
          }, ackTimeoutMs)
          pendingStartRef.current = { requestId, timer, instruction: String(message.instruction ?? '') }
          wsRef.current.send(JSON.stringify({ action: 'navigate_start', request_id: requestId, instruction: message.instruction, metadata: { ...existingMeta, frontend_task_id: nextTaskId } }))
          return true
        }
        wsRef.current.send(JSON.stringify(message))
        return true
      }
      if (message.action === 'config') return false
      const now = performance.now()
      if (now - lastNotConnectedAtRef.current > 2500) {
        lastNotConnectedAtRef.current = now
        const statusMsg =
          wsRef.current === null
            ? 'WebSocket not connected - check your network and try refreshing.'
            : wsRef.current.readyState === WebSocket.CONNECTING
              ? 'WebSocket still connecting - please wait a moment and try again.'
              : 'WebSocket disconnected - reconnecting automatically…'
        appendLog({ message: statusMsg, taskId: activeTaskIdRef.current, type: 'error', status: 'failed' })
      }
      return false
    },
    [ackTimeoutMs, appendLog, queuedTimeoutMs],
  )

  const sendAudioChunk = useCallback((audio: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'audio_chunk', audio }))
      return true
    }
    return false
  }, [])

  const resetClientState = useCallback(() => {
    setLogs([])
    setLatestFrame('')
    setCurrentUrl('about:blank')
    setIsWorking(false)
    setTaskActivity(createIdleActivityState())
    setWorkflowSteps([])
    setTranscripts([])
    setReasoningMap({})
    setSubAgents([])
    setSubAgentSteps({})
    setActiveExecutionMode('orchestrator')
    reasoningNormalizersRef.current = {}
    activeTaskIdRef.current = 'idle'
  }, [])

  const clearFrameCache = useCallback(() => {
    clearPersistedFrameCache()
    setLatestFrame('')
  }, [])

  const removeFrameForThread = useCallback((threadId: string) => {
    const normalizedThreadId = threadId.trim()
    if (!normalizedThreadId) return
    const normalizedUserId = (userId ?? '').trim() || 'anon'
    const scopeKey = `${normalizedUserId}:${normalizedThreadId}`
    removePersistedFrame(scopeKey)
    if (activeFrameScopeKeyRef.current === scopeKey) {
      setLatestFrame('')
    }
  }, [userId])

  const spawnSubAgent = useCallback((instruction: string, model: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Include the current task ID so the backend can track which parent task owns this sub-agent.
      // This is echoed back in subagent_list so the frontend can correctly scope sub-agents.
      wsRef.current.send(JSON.stringify({ action: 'spawn_subagent', instruction, model, parent_task_id: activeTaskIdRef.current }))
      return true
    }
    return false
  }, [activeTaskIdRef])

  const messageSubAgent = useCallback((sub_id: string, message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'message_subagent', sub_id, message }))
      return true
    }
    return false
  }, [])

  const cancelSubAgent = useCallback((sub_id: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'cancel_subagent', sub_id }))
      return true
    }
    return false
  }, [])
  useEffect(() => {
    setActivityView(selectActivityView(taskActivity, isWorking))
  }, [taskActivity, isWorking])

  useEffect(() => {
    if (!isWorking) return
    const timer = window.setInterval(() => {
      setActivityView(selectActivityView(taskActivity, true, Date.now()))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isWorking, taskActivity])


  return { connectionStatus, opsConnectionStatus, executionState, isWorking, taskActivity, activityStatusLabel: activityView.activityStatusLabel, activityDetail: activityView.activityDetail, isActivityVisible: activityView.isActivityVisible, activeExecutionMode, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, clearFrameCache, removeFrameForThread, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, spawnSubAgent, messageSubAgent, cancelSubAgent }
}
