import { useCallback, useEffect, useRef, useState } from 'react'
import { IncrementalTextNormalizer, normalizeTextPreservingMarkdown } from '../lib/textNormalization'

export type SteeringMode = 'steer' | 'interrupt' | 'queue'

export type ActivityPhase = 'idle' | 'thinking' | 'browsing' | 'calling_tool' | 'generating'

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

type WebSocketPayload = {
  type: 'step' | 'result' | 'frame' | 'error' | 'workflow_step' | 'screenshot' | 'transcript' | 'usage' | 'usage_tick' | 'context_update' | 'conversation_id' | 'reasoning_start' | 'reasoning_delta' | 'reasoning' | 'subagent_spawned' | 'subagent_step' | 'subagent_completed' | 'subagent_error' | 'subagent_cancelled' | 'subagent_list'
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

const BROWSER_TOOL_NAMES = new Set([
  'click',
  'type',
  'type_text',
  'scroll',
  'go_to_url',
  'go_back',
  'wait',
  'screenshot',
  'extract_page',
])

const ACTIVITY_FALLBACK_LABEL = 'Aegis is working…'

function getToolNameFromStep(content: string): string | null {
  const match = content.trim().match(/^\[([\w_]+)\]/)
  return match?.[1]?.toLowerCase() ?? null
}

function inferActivityFromStep(content: string): Omit<TaskActivity, 'updatedAt'> {
  const normalized = content.trim().toLowerCase()
  const toolName = getToolNameFromStep(content)
  if (toolName) {
    if (toolName === 'thinking') return { phase: 'thinking', detail: content }
    if (BROWSER_TOOL_NAMES.has(toolName)) return { phase: 'browsing', detail: content }
    if (/(model response|assistant response|generating|drafting)/i.test(content)) return { phase: 'generating', detail: content }
    return { phase: 'calling_tool', detail: content }
  }
  if (/(model response|assistant response|generating|drafting)/i.test(content)) {
    return { phase: 'generating', detail: content }
  }
  if (/(thinking|reasoning|analyzing|planning)/i.test(normalized)) {
    return { phase: 'thinking', detail: content }
  }
  return { phase: 'calling_tool', detail: ACTIVITY_FALLBACK_LABEL }
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
  const [isWorking, setIsWorking] = useState(false)
  const [taskActivity, setTaskActivity] = useState<TaskActivity>({ phase: 'idle', updatedAt: new Date().toISOString() })
  const [latestFrame, setLatestFrame] = useState('')
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
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const pingIntervalRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef(true)
  const activeTaskIdRef = useRef('idle')
  const activeFrameScopeKeyRef = useRef('')
  const reasoningNormalizersRef = useRef<Record<string, IncrementalTextNormalizer>>({})
  const lastStepAtRef = useRef(0)
  const lastNotConnectedAtRef = useRef(0)
  const connectRef = useRef<() => void>(() => undefined)

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
        wsUrl = `${protocol}//${parsed.host}${basePath}/ws/navigate`
      } catch {
        wsUrl = ''
      }
    }
    if (!wsUrl) {
      wsUrl = `${window.location.origin.replace('http', 'ws')}/ws/navigate`
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
      const payload = JSON.parse(event.data) as WebSocketPayload
      const taskId = activeTaskIdRef.current

      if (payload.type === 'conversation_id') {
        const convId = String(payload.data?.conversation_id ?? '')
        if (convId) setActiveConversationId(convId)
        return
      }
      if (payload.type === 'step') {
        const stepType = String(payload.data?.type ?? '').toLowerCase()
        const nonExecutionStepTypes = new Set(['queue', 'steer', 'config'])
        if (!nonExecutionStepTypes.has(stepType)) {
          setIsWorking(true)
          const inferred = inferActivityFromStep(String(payload.data?.content ?? payload.data?.type ?? ''))
          setTaskActivity({ ...inferred, updatedAt: new Date().toISOString() })
        }
        const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
        const urlMatch = content.match(/https?:\/\/[^\s)]+/)
        if (urlMatch?.[0]) setCurrentUrl(urlMatch[0])
        appendLog({
          message: content,
          taskId,
          type: stepType === 'interrupt' ? 'interrupt' : 'step',
          status: stepType === 'steer' ? 'steered' : 'in_progress',
        })
        return
      }
      if (payload.type === 'result') {
        setIsWorking(false)
        setTaskActivity({ phase: 'idle', updatedAt: new Date().toISOString() })
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
        setTaskActivity({ phase: 'thinking', detail: 'reasoning_start', updatedAt: new Date().toISOString() })
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
        setTaskActivity({ phase: 'thinking', detail: String(payload.data?.delta ?? 'reasoning_delta'), updatedAt: new Date().toISOString() })
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
          setTaskActivity({ phase: 'generating', detail: 'reasoning_completed', updatedAt: nowIso })
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
        const parentTaskId = activeTaskIdRef.current
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
        setTaskActivity({ phase: 'idle', updatedAt: new Date().toISOString() })
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), taskId, type: 'error', status: 'failed' })
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

  const send = useCallback(
    (message: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        if (message.action === 'navigate' || message.action === 'interrupt') {
          const nextTaskId = crypto.randomUUID()
          activeTaskIdRef.current = nextTaskId
          setIsWorking(true)
          setTaskActivity({ phase: 'thinking', detail: String(message.instruction ?? 'New task'), updatedAt: new Date().toISOString() })
          appendLog({
            message: String(message.instruction ?? 'New task'),
            taskId: nextTaskId,
            type: 'step',
            status: 'in_progress',
            stepKind: 'navigate',
            elapsedSeconds: 0,
          })
          const maybeUrl = String(message.instruction ?? '')
          if (/^https?:\/\//i.test(maybeUrl)) setCurrentUrl(maybeUrl)
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
    [appendLog],
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
    setTaskActivity({ phase: 'idle', updatedAt: new Date().toISOString() })
    setWorkflowSteps([])
    setTranscripts([])
    setReasoningMap({})
    setSubAgents([])
    setSubAgentSteps({})
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
      wsRef.current.send(JSON.stringify({ action: 'spawn_subagent', instruction, model }))
      return true
    }
    return false
  }, [])

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

  return { connectionStatus, isWorking, taskActivity, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, clearFrameCache, removeFrameForThread, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, spawnSubAgent, messageSubAgent, cancelSubAgent }
}
