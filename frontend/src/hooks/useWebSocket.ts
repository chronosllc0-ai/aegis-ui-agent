import { useCallback, useEffect, useRef, useState } from 'react'
import { IncrementalTextNormalizer, normalizeTextPreservingMarkdown } from '../lib/textNormalization'
import { createIdleActivityState, reduceActivityState, selectActivityView, type ActivitySelector, type ActivityState } from '../lib/activityState'
import { modeLabel, normalizeAgentMode, parseModeRuntimeEvent, type AgentModeId } from '../lib/agentModes'

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
  type: 'step' | 'result' | 'error' | 'interrupt' | 'workflow_step' | 'transcript' | 'usage' | 'usage_tick' | 'context_update' | 'conversation_id' | 'reasoning_start' | 'reasoning_delta' | 'reasoning' | 'tool-call' | 'subagent_spawned' | 'subagent_step' | 'subagent_completed' | 'subagent_error' | 'subagent_cancelled' | 'subagent_list' | 'mode_event' | 'mode_transition' | 'mode_event_parse_failed' | 'navigate_ack' | 'task_state' | 'task_result' | 'task_error' | 'pong' | 'runtime_session' | 'runtime_event'
  data?: Record<string, unknown>
  [key: string]: unknown
}

// ── Phase 9: truthful runtime context meter wire types ────────────
// These mirror the payloads :func:`backend.runtime.context_window.build_prepared_context`
// emits via the agent_loop dispatch hook. The frontend used to derive
// the meter from chat tokens alone — that heuristic is replaced by
// the eight-bucket meter the model actually receives.

export type RuntimeMeterBucket = {
  name:
    | 'system_prompt'
    | 'active_tools'
    | 'checkpoints'
    | 'workspace_files'
    | 'pinned_memories'
    | 'pending_tool_outputs'
    | 'chat_history'
    | 'current_user_message'
    | string
  tokens: number
  chars: number
}

export type RuntimeContextMeter = {
  total_tokens: number
  projected_pct: number
  should_compact: boolean
  model_context_window: number
  compact_threshold_pct: number
  buckets: RuntimeMeterBucket[]
  owner_uid?: string
  session_id?: string
}

export type RuntimeCompactionCheckpoint = {
  id?: string
  session_id?: string
  owner_uid?: string
  source_event_count?: number
  token_count?: number
  created_at?: string
}

export type RuntimeSessionInfo = {
  session_id: string
  owner_uid: string
  channel: string
}

// ── Runtime payload type guards (Phase 9) ─────────────────────────
// These run on every fan-out event before it reaches the React state,
// so they need to be cheap. The backend always sends the full set of
// required fields when the meter is real; partial payloads can only
// come from a degraded backend or a future schema change. Either way,
// surfacing them as ``NaN%`` is worse than dropping them on the floor.

function isRuntimeMeterBucket(value: unknown): value is RuntimeMeterBucket {
  if (!value || typeof value !== 'object') return false
  const b = value as Record<string, unknown>
  return (
    typeof b.name === 'string'
    && typeof b.tokens === 'number'
    && Number.isFinite(b.tokens)
    && typeof b.chars === 'number'
    && Number.isFinite(b.chars)
  )
}

export function isRuntimeContextMeter(value: unknown): value is RuntimeContextMeter {
  if (!value || typeof value !== 'object') return false
  const m = value as Record<string, unknown>
  if (typeof m.total_tokens !== 'number' || !Number.isFinite(m.total_tokens)) return false
  if (typeof m.projected_pct !== 'number' || !Number.isFinite(m.projected_pct)) return false
  if (typeof m.should_compact !== 'boolean') return false
  if (typeof m.model_context_window !== 'number' || !Number.isFinite(m.model_context_window)) return false
  if (typeof m.compact_threshold_pct !== 'number' || !Number.isFinite(m.compact_threshold_pct)) return false
  if (!Array.isArray(m.buckets)) return false
  return m.buckets.every(isRuntimeMeterBucket)
}

export function isRuntimeCompactionCheckpoint(value: unknown): value is RuntimeCompactionCheckpoint {
  if (!value || typeof value !== 'object') return false
  // Every documented field is optional, so the only requirement is
  // "is an object" — but we still null-check above so the consumer
  // can rely on getting a non-null record.
  return true
}

const THINKING_KEY = (taskId: string) => `aegis.reasoning.${taskId}`

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
  /**
   * Phase 9 runtime fan-out hooks. ``onRuntimeContextMeter`` fires on
   * every dispatch (including background heartbeat / automation runs),
   * ``onRuntimeCompactionCheckpoint`` fires when the projected pct
   * crosses ``compact_threshold_pct`` and the prompt was rewritten.
   * ``onRuntimeSession`` fires once at WS open with the canonical
   * ``agent:main:web:{owner_uid}`` id the meter REST endpoint expects.
   */
  onRuntimeSession?: (info: RuntimeSessionInfo) => void
  onRuntimeContextMeter?: (meter: RuntimeContextMeter) => void
  onRuntimeCompactionCheckpoint?: (checkpoint: RuntimeCompactionCheckpoint) => void
}

export function useWebSocket(options?: UseWebSocketOptions) {
  const onUsageMessage = options?.onUsageMessage
  const activeThreadId = options?.activeThreadId ?? null
  const onRuntimeSession = options?.onRuntimeSession
  const onRuntimeContextMeter = options?.onRuntimeContextMeter
  const onRuntimeCompactionCheckpoint = options?.onRuntimeCompactionCheckpoint
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [executionState, setExecutionState] = useState<ExecutionState>('idle')
  const [isWorking, setIsWorking] = useState(false)
  const [taskActivity, setTaskActivity] = useState<ActivityState>(() => createIdleActivityState())
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
  const reconnectRef = useRef<number | null>(null)
  const pingIntervalRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef(true)
  const activeTaskIdRef = useRef('idle')
  const reasoningNormalizersRef = useRef<Record<string, IncrementalTextNormalizer>>({})
  const lastStepAtRef = useRef(0)
  const lastNotConnectedAtRef = useRef(0)
  const connectRef = useRef<() => void>(() => undefined)
  const pendingStartRef = useRef<{ requestId: string; timer: number | null; instruction: string } | null>(null)
  const pendingBackendActivityTimeoutRef = useRef<number | null>(null)
  const pendingPostQueueProgressTimeoutRef = useRef<number | null>(null)
  const lastBackendActivityAtRef = useRef(0)
  const terminalTaskStateRef = useRef<Record<string, string>>({})
  const ackTimeoutMs = Number(import.meta.env.VITE_NAVIGATE_ACK_TIMEOUT_MS ?? 5000)
  const backendActivityTimeoutMs = Number(import.meta.env.VITE_BACKEND_ACTIVITY_TIMEOUT_MS ?? 3000)
  const postQueueProgressTimeoutMs = Number(import.meta.env.VITE_NAVIGATE_POST_QUEUE_PROGRESS_TIMEOUT_MS ?? 60000)

  const clearPostQueueProgressTimeout = useCallback(() => {
    if (pendingPostQueueProgressTimeoutRef.current !== null) {
      window.clearTimeout(pendingPostQueueProgressTimeoutRef.current)
      pendingPostQueueProgressTimeoutRef.current = null
    }
  }, [])

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
      const pendingStart = pendingStartRef.current
      if (pendingStart && pendingStart.timer !== null) {
        window.clearTimeout(pendingStart.timer)
      }
      pendingStartRef.current = null
      if (pingIntervalRef.current !== null) {
        window.clearInterval(pingIntervalRef.current)
        pingIntervalRef.current = null
      }
      if (pendingBackendActivityTimeoutRef.current !== null) {
        window.clearTimeout(pendingBackendActivityTimeoutRef.current)
        pendingBackendActivityTimeoutRef.current = null
      }
      clearPostQueueProgressTimeout()
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
      if (pendingBackendActivityTimeoutRef.current !== null) {
        window.clearTimeout(pendingBackendActivityTimeoutRef.current)
        pendingBackendActivityTimeoutRef.current = null
      }
      clearPostQueueProgressTimeout()
      setConnectionStatus('disconnected')
    }
    ws.onmessage = (event: MessageEvent<string>) => {
      lastBackendActivityAtRef.current = Date.now()
      if (pendingBackendActivityTimeoutRef.current !== null) {
        window.clearTimeout(pendingBackendActivityTimeoutRef.current)
        pendingBackendActivityTimeoutRef.current = null
      }
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
      // Phase 9: announce the canonical runtime session id so the
      // caller can hydrate /api/runtime/context-meter/{session_id}
      // before any user message has dispatched. Without this hook the
      // meter shows zero until the first reply arrives.
      if (payload.type === 'runtime_session') {
        const data = payload.data as Record<string, unknown> | undefined
        const sessionId = typeof data?.session_id === 'string' ? data.session_id : ''
        const ownerUid = typeof data?.owner_uid === 'string' ? data.owner_uid : ''
        const channel = typeof data?.channel === 'string' ? data.channel : 'web'
        if (sessionId && onRuntimeSession) {
          onRuntimeSession({ session_id: sessionId, owner_uid: ownerUid, channel })
        }
        return
      }
      // Phase 9: every event the agent_loop dispatch hook fans out
      // arrives here. We route by ``kind`` and forward truthful bucket
      // payloads up to the consumer hooks. The fan-out also carries
      // ``final_message`` / ``run_completed`` / ``error`` /
      // ``tool_call*`` etc. Phase 10 wires the chat-content kinds into
      // ``appendLog`` so the live UI stops depending on the (now-dead)
      // legacy ``step`` emitter for assistant replies. Phase 8/9 only
      // consumed the meter / checkpoint kinds; everything else is
      // dispatched here.
      //
      // Branch contract:
      //   • ``run_started``       → flip working/running state
      //   • ``user_message``      → ignored (frontend already shows the
      //                              optimistic bubble before dispatch)
      //   • ``model_message``     → ignored (intermediate Agents-SDK
      //                              messages are coalesced into the
      //                              ``final_message`` to avoid double
      //                              rendering on no-tool turns)
      //   • ``final_message``     → assistant ``result`` bubble
      //   • ``tool_call``         → in-progress tool ``step`` card
      //   • ``tool_result``       → completed tool ``step`` card
      //   • ``run_completed``     → terminal state (clears working flag)
      //   • ``error``             → error log + failed state
      //   • ``context_meter`` /
      //     ``compaction_checkpoint`` → forwarded to the meter hook
      //   • ``trace`` / ``accepted`` → ignored (debug-only)
      if (payload.type === 'runtime_event') {
        const data = payload.data as Record<string, unknown> | undefined
        const kind = typeof data?.kind === 'string' ? data.kind : ''
        const inner = (data?.payload as Record<string, unknown> | undefined) ?? {}
        const channel = typeof data?.channel === 'string' ? data.channel : ''
        // Runtime events fan out to every subscribed surface; only
        // the ``web`` channel events should drive the chat UI. Slack /
        // Telegram / heartbeat events are surfaced by their own egress
        // workers and would otherwise spam the chat panel with foreign
        // assistant bubbles. Meter / checkpoint events are exempt
        // because the context meter is session-wide regardless of
        // origin channel.
        //
        // Empty-string ``channel`` is *not* accepted: the runtime
        // dispatch path always sets ``channel`` from the
        // ``ChannelSession``, so an empty string indicates a malformed
        // / forged event. Treating it as web-relevant would diverge
        // from the backend persistence guard (``channel == "web"``)
        // and was flagged as the kilo critical from the PR #345
        // review — we now align both sides on a strict ``"web"``
        // match.
        const isChannelChatRelevant =
          channel === 'web' || kind === 'context_meter' || kind === 'compaction_checkpoint'
        if (kind === 'context_meter' && onRuntimeContextMeter) {
          // Validate at the WS boundary so the consumer never sees a
          // partially-populated meter — missing numeric fields would
          // otherwise turn into NaN downstream (percentage bars going
          // wild). All required-by-the-type fields are checked; the
          // optional ``owner_uid`` / ``session_id`` are passed through
          // untouched.
          if (isRuntimeContextMeter(inner)) {
            onRuntimeContextMeter(inner)
          } else if (typeof console !== 'undefined') {
            // eslint-disable-next-line no-console
            console.warn('[runtime] dropped malformed context_meter payload', inner)
          }
          return
        }
        if (kind === 'compaction_checkpoint' && onRuntimeCompactionCheckpoint) {
          if (isRuntimeCompactionCheckpoint(inner)) {
            onRuntimeCompactionCheckpoint(inner)
          } else if (typeof console !== 'undefined') {
            // eslint-disable-next-line no-console
            console.warn('[runtime] dropped malformed compaction_checkpoint payload', inner)
          }
          return
        }
        if (!isChannelChatRelevant) return
        // ``activeTaskIdRef`` reflects whatever task the UI considers
        // current at the moment the event lands; runtime events do not
        // (yet) carry a frontend ``task_id`` so we cannot do better
        // than this. If the user starts a new task before the
        // previous run's tail events drain, those tail events get
        // attributed to the new task in the chat log. Acceptable for
        // now — fix in a future phase by either (a) propagating
        // ``frontend_task_id`` through ``agent_loop.emit`` or (b)
        // pairing run_started/run_completed with a per-run task scope
        // ref. (kilo S1 from the PR #345 review.)
        const liveTaskId = activeTaskIdRef.current
        lastBackendActivityAtRef.current = performance.now()
        if (kind === 'run_started' || kind === 'final_message' || kind === 'tool_call' || kind === 'tool_result' || kind === 'run_completed' || kind === 'error') {
          clearPostQueueProgressTimeout()
        }
        if (kind === 'run_started') {
          setIsWorking(true)
          setExecutionState('running')
          return
        }
        if (kind === 'final_message') {
          const text = typeof inner.text === 'string' ? inner.text : ''
          if (text.trim().length > 0) {
            appendLog({
              message: text,
              taskId: liveTaskId,
              type: 'result',
              status: 'completed',
              rawStepType: 'final_message',
            })
          }
          // Defensive: clear the working flag here too. ``run_completed``
          // is the canonical terminal signal, but if it's ever dropped
          // (websocket re-handshake mid-run, supervisor crash before
          // emit, etc.) the spinner would otherwise hang forever
          // (kilo P2 from the PR #345 review). A transient
          // ``tool_call`` after a ``final_message`` is rare but flips
          // it back on cleanly.
          setIsWorking(false)
          return
        }
        if (kind === 'tool_call') {
          setIsWorking(true)
          const name = typeof inner.name === 'string' ? inner.name : 'tool'
          const args = typeof inner.arguments === 'string' ? inner.arguments : ''
          // Mirror the legacy ``tool_start`` step card shape so
          // ChatPanel / SubAgentPanel render a familiar in-progress
          // card. Truncate arguments aggressively to keep the chat
          // log readable; the full payload is in the persisted run
          // record for replay.
          const previewArgs = args.length > 160 ? `${args.slice(0, 160)}…` : args
          appendLog({
            message: previewArgs ? `${name}(${previewArgs})` : name,
            taskId: liveTaskId,
            type: 'step',
            status: 'in_progress',
            rawStepType: 'tool_start',
          })
          return
        }
        if (kind === 'tool_result') {
          const output = typeof inner.output === 'string' ? inner.output : ''
          if (output.trim().length > 0) {
            const preview = output.length > 240 ? `${output.slice(0, 240)}…` : output
            appendLog({
              message: preview,
              taskId: liveTaskId,
              type: 'step',
              status: 'completed',
              rawStepType: 'tool_end',
            })
          }
          return
        }
        if (kind === 'run_completed') {
          // ``agent_loop.dispatch`` emits ``status: "error"`` when
          // ``Runner.run`` raises (the ``error`` event is fired first
          // and ``run_completed`` follows in the ``finally`` block).
          // Without folding ``"error"`` into ``failed`` here the
          // execution state would be briefly set to ``failed`` by
          // the ``error`` handler and then immediately overwritten
          // back to ``completed`` — flagged as codex P1 from the PR
          // #345 review.
          const status = typeof inner.status === 'string' ? inner.status : 'completed'
          setIsWorking(false)
          if (status === 'failed' || status === 'error') {
            setExecutionState('failed')
          } else if (status === 'cancelled') {
            setExecutionState('cancelled')
          } else {
            setExecutionState('completed')
          }
          return
        }
        if (kind === 'error') {
          const message = typeof inner.message === 'string' ? inner.message : 'Runtime error'
          setIsWorking(false)
          setExecutionState('failed')
          appendLog({
            message: `⚠️ ${message}`,
            taskId: liveTaskId,
            type: 'error',
            status: 'failed',
          })
          return
        }
        // ``user_message`` / ``model_message`` / ``trace`` / ``accepted``
        // are intentionally dropped — see the contract block above.
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
          clearPostQueueProgressTimeout()
          setExecutionState('failed')
          setIsWorking(false)
          appendLog({ message: `Start rejected: ${String(payload.data?.reason ?? 'unknown')}`, taskId: activeTaskIdRef.current, type: 'error', status: 'failed' })
          return
        }
        setExecutionState('running')
        return
      }
      if (payload.type === 'task_state') {
        const payloadTaskId = String(payload.data?.task_id ?? '').trim() || activeTaskIdRef.current
        const state = String(payload.data?.state ?? '')
        if (state === 'queued') {
          clearPostQueueProgressTimeout()
          const frontendTaskId = activeTaskIdRef.current
          pendingPostQueueProgressTimeoutRef.current = window.setTimeout(() => {
            pendingPostQueueProgressTimeoutRef.current = null
            if (activeTaskIdRef.current !== frontendTaskId || terminalTaskStateRef.current[payloadTaskId]) return
            setExecutionState('failed')
            setIsWorking(false)
            appendLog({
              message: 'No runtime progress reported after queueing (E_START_TIMEOUT). Retry from chat.',
              taskId: frontendTaskId,
              type: 'error',
              status: 'failed',
            })
          }, postQueueProgressTimeoutMs)
          setExecutionState('starting')
          setIsWorking(true)
        } else if (state === 'running' || state === 'tool_call' || state === 'waiting_input') {
          clearPostQueueProgressTimeout()
          setExecutionState('running')
          setIsWorking(true)
        } else if (state === 'succeeded') {
          clearPostQueueProgressTimeout()
          terminalTaskStateRef.current[payloadTaskId] = state
          setExecutionState('completed')
          setIsWorking(false)
        } else if (state === 'failed') {
          clearPostQueueProgressTimeout()
          terminalTaskStateRef.current[payloadTaskId] = state
          setExecutionState('failed')
          setIsWorking(false)
        } else if (state === 'cancelled') {
          clearPostQueueProgressTimeout()
          terminalTaskStateRef.current[payloadTaskId] = state
          setExecutionState('cancelled')
          setIsWorking(false)
        }
        return
      }
      if (payload.type === 'task_result') {
        clearPostQueueProgressTimeout()
        const payloadTaskId = String(payload.data?.task_id ?? '').trim() || taskId
        const terminalState = terminalTaskStateRef.current[payloadTaskId]
        if (terminalState === 'failed') setExecutionState('failed')
        else if (terminalState === 'cancelled') setExecutionState('cancelled')
        else setExecutionState('completed')
        setIsWorking(false)
        setTaskActivity(createIdleActivityState())
        const resultSummary = String(payload.data?.summary ?? '').trim()
        if (resultSummary && terminalState === 'succeeded') {
          appendLog({
            message: `[summarize_task] ${JSON.stringify({ summary: resultSummary })}`,
            taskId: payloadTaskId,
            type: 'result',
            status: 'completed',
            rawStepType: 'task_result',
          })
        }
        return
      }
      if (payload.type === 'task_error') {
        clearPostQueueProgressTimeout()
        setExecutionState('failed')
        setIsWorking(false)
        setTaskActivity(createIdleActivityState())
        const errorAlreadyEmitted = Boolean(payload.data?.error_already_emitted)
        if (!errorAlreadyEmitted) {
          const errorMsg = String(payload.data?.message ?? payload.data?.code ?? 'Task failed')
          appendLog({ message: `⚠️ ${errorMsg}`, taskId, type: 'error', status: 'failed' })
        }
        return
      }
      if (payload.type === 'step') {
        clearPostQueueProgressTimeout()
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
        clearPostQueueProgressTimeout()
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
        clearPostQueueProgressTimeout()
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
        clearPostQueueProgressTimeout()
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
      if (payload.type === 'workflow_step') {
        const step = payload.data as WorkflowStep
        setWorkflowSteps((prev) => [...prev.filter((item) => item.step_id !== step.step_id), step])
        return
      }
      if (payload.type === 'mode_event') {
        const scopedFrontendTaskId = String(payload.data?.frontend_task_id ?? '').trim()
        if (scopedFrontendTaskId && activeThreadId && scopedFrontendTaskId !== activeThreadId) {
          return
        }
        const parsed = parseModeRuntimeEvent(payload.data)
        if (!parsed.ok) {
          appendLog({
            message: `Mode runtime event parse failed (${parsed.error}); using safe fallback.`,
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
      if (payload.type === 'mode_transition') {
        const scopedFrontendTaskId = String(payload.data?.frontend_task_id ?? '').trim()
        if (scopedFrontendTaskId && activeThreadId && scopedFrontendTaskId !== activeThreadId) {
          return
        }
        const toMode = String(payload.data?.to_mode ?? '').trim()
        if (toMode) {
          setActiveExecutionMode(normalizeAgentMode(toMode))
        }
        return
      }
      if (payload.type === 'mode_event_parse_failed') {
        appendLog({
          message: `Mode runtime event parse failed (${String(payload.data?.error ?? 'unknown')}); using safe fallback.`,
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
          appendLog({
            message: '[thinking]',
            taskId,
            type: 'reasoning_start',
            status: 'in_progress',
            stepId,
            rawStepType: 'reasoning_start',
          })
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
          setLogs((prev) =>
            prev.map((entry) => (
              entry.stepId === stepId && entry.type === 'reasoning_start'
                ? { ...entry, message: normalizedCumulative }
                : entry
            )),
          )
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
        clearPostQueueProgressTimeout()
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), taskId, type: 'error', status: 'failed' })
        return
      }
    }
  }, [appendLog, clearPostQueueProgressTimeout, onUsageMessage, onRuntimeCompactionCheckpoint, onRuntimeContextMeter, onRuntimeSession, postQueueProgressTimeoutMs])

  useEffect(() => {
    connectRef.current = connect
  }, [clearPostQueueProgressTimeout, connect])

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
      if (pendingBackendActivityTimeoutRef.current !== null) {
        window.clearTimeout(pendingBackendActivityTimeoutRef.current)
        pendingBackendActivityTimeoutRef.current = null
      }
      clearPostQueueProgressTimeout()
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [clearPostQueueProgressTimeout, connect])

  const send = useCallback(
    (message: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const clientRequestId = String(message.client_request_id ?? crypto.randomUUID())
        const outboundMessage = {
          ...message,
          client_request_id: clientRequestId,
        }
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
          clearPostQueueProgressTimeout()
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
          console.info('[AegisUI] trace_phase=frontend_dispatch request_id=%s client_request_id=%s action=navigate_start', requestId, clientRequestId)
          const sendAt = Date.now()
          if (pendingBackendActivityTimeoutRef.current !== null) {
            window.clearTimeout(pendingBackendActivityTimeoutRef.current)
          }
          pendingBackendActivityTimeoutRef.current = window.setTimeout(() => {
            if (lastBackendActivityAtRef.current >= sendAt) {
              pendingBackendActivityTimeoutRef.current = null
              return
            }
            setExecutionState('failed')
            setIsWorking(false)
            appendLog({
              message: 'No backend activity detected after send (E_START_TIMEOUT). Check connection/server logs and retry.',
              taskId: nextTaskId,
              type: 'error',
              status: 'failed',
            })
            pendingBackendActivityTimeoutRef.current = null
          }, backendActivityTimeoutMs)
          wsRef.current.send(JSON.stringify({
            action: 'navigate_start',
            request_id: requestId,
            client_request_id: clientRequestId,
            instruction: message.instruction,
            metadata: { ...existingMeta, frontend_task_id: nextTaskId },
          }))
          return true
        }
        wsRef.current.send(JSON.stringify(outboundMessage))
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
    [ackTimeoutMs, appendLog, backendActivityTimeoutMs, clearPostQueueProgressTimeout],
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
    setCurrentUrl('about:blank')
    setIsWorking(false)
    setTaskActivity(createIdleActivityState())
    setWorkflowSteps([])
    setTranscripts([])
    setReasoningMap({})
    setSubAgents([])
    setSubAgentSteps({})
    setActiveExecutionMode('orchestrator')
    if (pendingBackendActivityTimeoutRef.current !== null) {
      window.clearTimeout(pendingBackendActivityTimeoutRef.current)
      pendingBackendActivityTimeoutRef.current = null
    }
    clearPostQueueProgressTimeout()
    reasoningNormalizersRef.current = {}
    activeTaskIdRef.current = 'idle'
  }, [clearPostQueueProgressTimeout])

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


  return { connectionStatus, executionState, isWorking, taskActivity, activityStatusLabel: activityView.activityStatusLabel, activityDetail: activityView.activityDetail, isActivityVisible: activityView.isActivityVisible, activeExecutionMode, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, spawnSubAgent, messageSubAgent, cancelSubAgent }
}
