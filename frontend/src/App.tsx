import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChangelogModal, SubAgentModal, useChangelog } from './components/ChangelogModal'
import { NotificationBell } from './components/NotificationBell'
import { PrivacyPage } from './components/PrivacyPage'
import { TermsPage } from './components/TermsPage'
import { useNotifications } from './context/NotificationContext'
import { AuthPage } from './components/AuthPage'
// CostEstimator removed from main UI - credit details live in Settings > Usage
import { LandingPage } from './components/LandingPage'
import { OnboardingWizard, isOnboardingComplete } from './components/OnboardingWizard'
import { ProductTour, isTourComplete } from './components/ProductTour'
import { SpendingAlert } from './components/SpendingAlert'
import { UsageDropdown } from './components/UsageDropdown'
import { UserMenu } from './components/UserMenu'
import { TaskPlanView } from './components/TaskPlanView'
import { Icons } from './components/icons'
import { ChatPanel } from './components/ChatPanel'
import { HeaderBar, NavItem, SidebarSection } from './components/ui/DesignSystem'
import type { SessionSwitcherItem } from './components/SessionSwitcher'
import { SubAgentPanel } from './components/SubAgentPanel'
import { UseCasePage } from './components/UseCasePage'
import { SettingsPage } from './components/settings/SettingsPage'
import { StandaloneSettingsPage } from './components/settings/StandaloneSettingsPage'
import type { SettingsTab } from './components/settings/SettingsPage'
import { AutomationsPage } from './components/AutomationsPage'
import { SessionsPage } from './components/SessionsPage'
import { ImpersonationBanner } from './components/admin/ImpersonationBanner'
import { useImpersonation } from './components/admin/useImpersonation'
import { useToast } from './hooks/useToast'
import { useContextMeter } from './hooks/useContextMeter'
import type { RuntimeCompactionCheckpoint, RuntimeContextMeter } from './hooks/useWebSocket'
import { useSettingsContext } from './context/useSettingsContext'
import { useMicrophone } from './hooks/useMicrophone'
import { useUsage } from './hooks/useUsage'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { useSessions, type ServerMessage } from './hooks/useSessions'
import { apiUrl } from './lib/api'
import { LuShield } from 'react-icons/lu'
import { modelInfo, PROVIDERS } from './lib/models'
import { docsPath, navigateTo, usePathname, PRIVACY_PATH, TERMS_PATH } from './lib/routes'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

/**
 * Phase 9 helper: pull the truthful, eight-bucket context meter for a
 * runtime session and feed it into the meter hook. The dispatch hook
 * only emits ``context_meter`` events on actual runs, so without this
 * REST call the bar would sit at zero from WS open until the first
 * model invocation. ``GET /api/runtime/context-meter/{session_id}``
 * returns the same payload shape ``RuntimeContextMeter`` decodes.
 *
 * Failures are logged and swallowed — the meter falls back to the
 * heuristic until the next live ``context_meter`` event arrives, which
 * is strictly better than throwing into a render path.
 */
async function hydrateRuntimeMeter(
  sessionId: string,
  apply: ((meter: RuntimeContextMeter) => void) | null,
): Promise<void> {
  if (!sessionId || !apply) return
  try {
    // Use ``apiUrl`` so deployments with ``VITE_API_URL`` pointing to
    // a different origin (the common Netlify-frontend + Railway-API
    // split) actually hit the backend rather than the static host.
    const resp = await fetch(
      apiUrl(`/api/runtime/context-meter/${encodeURIComponent(sessionId)}`),
      { credentials: 'include' },
    )
    if (!resp.ok) {
      // 404 is expected for sessions that have never dispatched a run.
      // We keep silent on 404 so the console isn't littered for fresh
      // anonymous tabs.
      if (resp.status !== 404) {
        // eslint-disable-next-line no-console
        console.warn('[runtime] context-meter hydrate failed', resp.status)
      }
      return
    }
    const body = (await resp.json()) as RuntimeContextMeter
    if (typeof body?.total_tokens === 'number' && Array.isArray(body?.buckets)) {
      apply(body)
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[runtime] context-meter hydrate error', err)
  }
}
const MAIN_SESSION_ID = 'agent:main:main'
// Stop-words to skip when picking the first meaningful word from an instruction
const STOP_WORDS = new Set(['a', 'an', 'the', 'to', 'do', 'in', 'on', 'at', 'of', 'for', 'and', 'or', 'with', 'by', 'from', 'please', 'now', 'then', 'that', 'this', 'it', 'is', 'be', 'can', 'will', 'your', 'my', 'our', 'their'])

/**
 * Derive a short, unique, human-readable display name for a sub-agent.
 * Format: "<FirstMeaningfulWord>-<4-char sub_id suffix>"
 * The sub_id suffix guarantees uniqueness even when instructions share the same opening words.
 */
function subAgentDisplayName(agent: { instruction: string; sub_id: string }): string {
  const words = agent.instruction.trim().split(/\s+/)
  const first = words.find((w) => w.length > 1 && !STOP_WORDS.has(w.toLowerCase()))
  const label = first ? first.replace(/[^a-zA-Z0-9]/g, '') : 'Agent'
  const shortId = agent.sub_id.replace(/-/g, '').slice(0, 4)
  return `${label}-${shortId}`
}
const SETTINGS_ROUTE_MAP: Record<string, SettingsTab> = {
  profile: 'Profile',
  'agent-configuration': 'Agent Configuration',
  'workspace-files': 'Agent Configuration',
  'api-keys': 'API Keys',
  credits: 'Billing',
  invoices: 'Billing',
  billing: 'Billing',
  connections: 'Connections',
  memory: 'Memory',
  observability: 'Observability',
  skills: 'Skills',
  support: 'Support',
  admin: 'Admin',
}
const settingsSlugForTab = (tab: SettingsTab): string => tab.toLowerCase().replace(/\s+/g, '-')


const STANDALONE_SETTINGS_TABS = new Set<SettingsTab>([
  'Agent Configuration',
  'API Keys',
  'Billing',
  'Connections',
  'Memory',
  'Observability',
  'Skills',
  'Support',
  'Admin',
])

// Rough token estimate for context tracking (≈4 chars per token)
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4)
}

function App() {
  const { balance, handleUsageMessage, resetSession: resetUsageSession } = useUsage()
  const { show: showChangelog, dismiss: dismissChangelog, version: appVersion } = useChangelog()
  const toastCtx = useToast()
  const { addNotification } = useNotifications()
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(MAIN_SESSION_ID)
  // Server-side conversation persistence - replaces localStorage for history + messages
  const [authUser, setAuthUser] = useState<{ uid?: string; name: string; email: string; avatar_url?: string | null; role?: string; impersonating?: boolean } | null>(null)
  // Phase 9 runtime meter wiring. ``useSettingsContext`` and
  // ``useContextMeter`` are now hoisted above ``useWebSocket`` so the
  // runtime callbacks can reference ``contextMeter.*`` directly via
  // refs that are populated *during render* (not in an effect). This
  // closes the first-render race the original code had: the websocket
  // can fan-out a ``runtime_session`` event between mount and the
  // post-render effect, so any ref written in a ``useEffect`` is null
  // exactly when ``onRuntimeSession`` fires.
  const { settings, patchSettings, wsConfig } = useSettingsContext()
  const pathname = usePathname()
  const contextMeter = useContextMeter(settings.model)

  // Latest-ref pattern: assigned synchronously on every render so any
  // websocket callback (which always runs after at least one render
  // completes, since the WS itself is opened in a useEffect) sees the
  // current ``applyRuntimeMeter`` / ``applyCompactionCheckpoint``.
  const runtimeMeterCbRef = useRef<((meter: RuntimeContextMeter) => void) | null>(null)
  const runtimeCheckpointCbRef = useRef<((cp: RuntimeCompactionCheckpoint) => void) | null>(null)
  runtimeMeterCbRef.current = contextMeter.applyRuntimeMeter
  runtimeCheckpointCbRef.current = contextMeter.applyCompactionCheckpoint

  // Keep the snapshot's ``modelId`` / ``contextLimit`` in sync when
  // the user switches models in Settings. ``useContextMeter`` doesn't
  // sync internally — it only knows the *current* model on construction
  // — so we drive ``updateModel`` from the settings change.
  const updateMeterModel = contextMeter.updateModel
  useEffect(() => {
    updateMeterModel(settings.model)
  }, [settings.model, updateMeterModel])

  const { connectionStatus, isWorking, activityStatusLabel, activityDetail, isActivityVisible, logs, transcripts, send, sendAudioChunk, resetClientState, activeConversationId, subAgents, subAgentSteps, messageSubAgent, cancelSubAgent } = useWebSocket({
    onUsageMessage: handleUsageMessage,
    userId: authUser?.uid ?? null,
    activeThreadId: selectedTaskId,
    onRuntimeSession: (info) => {
      // Hydrate the meter immediately so the bar reflects the session's
      // current footprint before the user even types — the dispatch
      // hook only emits ``context_meter`` on actual runs, so without
      // this fetch the bar would sit at zero across reconnects.
      void hydrateRuntimeMeter(info.session_id, runtimeMeterCbRef.current)
    },
    onRuntimeContextMeter: (meter) => {
      runtimeMeterCbRef.current?.(meter)
    },
    onRuntimeCompactionCheckpoint: (cp) => {
      runtimeCheckpointCbRef.current?.(cp)
    },
  })
  const prevConnectionStatus = useRef(connectionStatus)

  const [showSettings, setShowSettings] = useState(false)
  const [showAutomations, setShowAutomations] = useState(false)
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab | undefined>(undefined)
  const [showSubAgentModal, setShowSubAgentModal] = useState(false)
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const { sessions, fetchMessages, fetchSessions } = useSessions(authUser?.uid ?? null)
  // Server messages loaded for the selected conversation
  const [serverMessages, setServerMessages] = useState<ServerMessage[]>([])
  const [optimisticMessagesByTask, setOptimisticMessagesByTask] = useState<Record<string, ServerMessage[]>>({})
  const saveSessionLabel = useCallback(async (sessionId: string, label: string) => {
    if (!label) return
    await fetch(apiUrl(`/api/sessions/${encodeURIComponent(sessionId)}/label`), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: label }),
    })
    await fetchSessions()
  }, [fetchSessions])

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [, setPendingPlan] = useState<string | null>(() => {
    return sessionStorage.getItem('aegis.pendingPlan')
  })
  const [activePlanId, setActivePlanId] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const [pendingNavigation, setPendingNavigation] = useState<{ instruction: string; metadata?: Record<string, unknown> } | null>(null)
  const subAgentsRef = useRef(subAgents)
  const redirectedLegacySessionsRef = useRef(false)
  // Use case page routing
  const [activeUseCaseId, setActiveUseCaseId] = useState<string | null>(null)
  // draftInput reserved for future InputBar onChange wiring
  void useState

  const docsSlug = slugFromDocsPath(pathname)
  const isDocsRoute = pathname === '/docs' || pathname.startsWith('/docs/')
  const isAuthRoute = pathname === '/auth'
  const isPrivacyRoute = pathname === PRIVACY_PATH
  const isTermsRoute = pathname === TERMS_PATH
  const isUseCaseRoute = pathname.startsWith('/use-case/')

  const currentModelMeta = modelInfo(settings.model)
  const currentModelLabel = currentModelMeta?.label ?? settings.model
  const activityDetailText = activityDetail
  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true
  const isAdminPath = isAdmin && pathname.startsWith('/admin')
  const isSettingsPath = pathname.startsWith('/settings')
  const activeSettingsTab: SettingsTab | undefined = settingsInitialTab
  const isAutomationsPath = pathname === '/automations'
  const isSessionsPath = pathname === '/sessions'
  const { status: impersonationStatus, checkStatus } = useImpersonation()

  const { isActive: voiceActive, isSupported: voiceSupported, toggle: toggleVoice, stop: stopVoice } =
    useMicrophone({ onChunk: (payload) => sendAudioChunk(payload) })

  useEffect(() => {
    if (connectionStatus !== 'connected' && voiceActive) {
      void stopVoice()
    }
  }, [connectionStatus, voiceActive, stopVoice])

  useEffect(() => {
    subAgentsRef.current = subAgents
  }, [subAgents])

  // Track WebSocket connection changes → notify on disconnect / reconnect
  useEffect(() => {
    const prev = prevConnectionStatus.current
    if (prev === 'connected' && connectionStatus === 'disconnected') {
      addNotification({
        type: 'warning',
        title: 'Agent disconnected',
        message: 'Lost connection to the Aegis backend. Attempting to reconnect automatically…',
        source: 'websocket',
      })
    } else if (prev !== 'connected' && prev !== 'connecting' && connectionStatus === 'connected') {
      addNotification({ type: 'success', title: 'Agent reconnected', message: 'Connection to Aegis restored.', source: 'websocket' })
    }
    prevConnectionStatus.current = connectionStatus
  }, [connectionStatus, addNotification])

  // Detect and surface agent errors from WebSocket log messages
  useEffect(() => {
    if (!logs.length) return
    const last = logs[logs.length - 1]
    if (last.type !== 'error') return
    const msg = last.message?.toLowerCase() ?? ''

    // Categorise the error for a clearer title
    const isCreditError =
      msg.includes('insufficient') || msg.includes('quota') || msg.includes('credits') ||
      msg.includes('rate limit') || msg.includes('402') || msg.includes('429') ||
      msg.includes('billing') || msg.includes('out of credits') || msg.includes('usage limit')
    const isAuthError =
      msg.includes('401') || msg.includes('unauthorized') || msg.includes('invalid api key') ||
      msg.includes('authentication') || msg.includes('api key')
    const isProviderError =
      msg.includes('no api key') || msg.includes('provider') || msg.includes('model')

    let title = 'Agent error'
    if (isCreditError) title = 'API credit / quota error'
    else if (isAuthError) title = 'API key invalid or expired'
    else if (isProviderError) title = 'Provider not configured'

    // Always surface agent errors as a notification so they are impossible to miss
    addNotification({
      type: 'error',
      title,
      message: last.message || 'The agent encountered an unexpected error.',
      source: 'credit',
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs])

  const connectionLabel = useMemo(() => {
    if (connectionStatus === 'connected') return { cls: 'bg-emerald-400', label: 'Connected' }
    if (connectionStatus === 'connecting') return { cls: 'bg-yellow-400', label: 'Reconnecting...' }
    return { cls: 'bg-red-400', label: 'Disconnected' }
  }, [connectionStatus])


  // ── Browser tab title: Working… / Aegis ───────────────────────────
  const [titleMode, setTitleMode] = useState<'idle' | 'working'>('idle')
  useEffect(() => {
    if (!isWorking) { setTitleMode('idle'); return }
    setTitleMode('working')
  }, [isWorking])
  useEffect(() => {
    if (titleMode === 'working') document.title = '⚙ Aegis - Working…'
    else document.title = 'Aegis'
  }, [titleMode])

  useEffect(() => {
    document.body.style.overflow = isAuthenticated && !isDocsRoute && !isPrivacyRoute && !isTermsRoute ? 'hidden' : 'auto'
    return () => {
      document.body.style.overflow = 'auto'
    }
  }, [isAuthenticated, isDocsRoute, isPrivacyRoute, isTermsRoute])

  useEffect(() => {
    if (pathname === '/settings/sessions') {
      if (redirectedLegacySessionsRef.current) return
      redirectedLegacySessionsRef.current = true
      navigateTo('/sessions')
      return
    }
    redirectedLegacySessionsRef.current = false
    setShowSettings(isSettingsPath || isAdminPath)
    setShowAutomations(isAutomationsPath)

    if (!isSettingsPath && !isAdminPath) {
      setSettingsInitialTab(undefined)
      return
    }

    const slug = pathname.split('/')[2]
    if (!slug) {
      setSettingsInitialTab(isAdminPath ? 'Admin' : undefined)
      return
    }

    const mapped = SETTINGS_ROUTE_MAP[slug]
    if (mapped) {
      setSettingsInitialTab(mapped)
      return
    }

    setSettingsInitialTab(isAdminPath ? 'Admin' : undefined)
  }, [isAdminPath, isAutomationsPath, isSettingsPath, pathname])

  useEffect(() => {
    if (!isAuthenticated) return
    if (showSettings && !isSettingsPath && !isAdminPath) navigateTo('/settings')
  }, [isAuthenticated, isAdminPath, isSettingsPath, showSettings])

  useEffect(() => {
    let active = true
    const loadAuth = async () => {
      setAuthLoading(true)
      try {
        const response = await fetch(apiUrl('/api/auth/me'), { credentials: 'include' })
        if (!response.ok) {
          if (active) {
            setIsAuthenticated(false)
            setAuthUser(null)
          }
          return
        }
        const data = await response.json().catch(() => ({}))
        if (active && data?.user) {
          setAuthUser({
            ...data.user,
            impersonating: data.user?.impersonating === true || data?.impersonating === true,
          })
          setIsAuthenticated(true)
          // Redirect away from /auth after session restored (e.g. post-OAuth page reload)
          if (window.location.pathname === '/auth') navigateTo('/')
          // Handle ?settings=<Tab> deep-link (e.g. after OAuth callback redirect)
          const params = new URLSearchParams(window.location.search)
          const settingsTab = params.get('settings') as SettingsTab | null
          if (settingsTab && ['Profile', 'Agent Configuration', 'API Keys', 'Credits', 'Invoices', 'Billing', 'Connections', 'Memory', 'Observability', 'Support'].includes(settingsTab)) {
            setSettingsInitialTab(settingsTab)
            setShowSettings(true)
            // Strip the ?settings= param from the URL without a page reload
            const cleanUrl = new URL(window.location.href)
            cleanUrl.searchParams.delete('settings')
            window.history.replaceState({}, '', cleanUrl.toString())
          }
        }
      } finally {
        if (active) setAuthLoading(false)
      }
    }
    void loadAuth()
    return () => {
      active = false
    }
  }, [])

  const prevUserUidRef = useRef<string | null>(null)
  useEffect(() => {
    const nextUid = authUser?.uid ?? null
    if (prevUserUidRef.current !== null && prevUserUidRef.current !== nextUid) {
      setSelectedTaskId(null)
    }
    prevUserUidRef.current = nextUid
  }, [authUser?.uid])

  useEffect(() => {
    if (!isAuthenticated || !isImpersonating) return
    void checkStatus()
  }, [isAuthenticated, isImpersonating, checkStatus])

  useEffect(() => {
    if (isWorking && taskStartedAt === null) {
      setTaskStartedAt(Date.now())
      setDurationSeconds(0)
      return
    }
    if (!isWorking) return
    const timer = window.setInterval(() => {
      if (taskStartedAt !== null) setDurationSeconds(Math.floor((Date.now() - taskStartedAt) / 1000))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isWorking, taskStartedAt])

  // Task history is saved at send-time (see handleSend) so titles always reflect
  // the actual user instruction, not a backend log message.


  // ── Context tracking: feed log tokens into the context meter ──
  useEffect(() => {
    if (logs.length === 0) return
    const latest = logs[logs.length - 1]
    if (!latest) return
    // Estimate tokens from the latest log entry
    const tokens = estimateTokens(latest.message)
    const { shouldCompact } = contextMeter.addTokens(tokens)
    if (shouldCompact) {
      // Trigger auto-compaction
      contextMeter.startCompacting()
      // Simulate compaction (in production the backend would do this)
      window.setTimeout(() => {
        contextMeter.finishCompacting()
      }, 2500)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs.length])

  // ── Context: sync model changes ──
  useEffect(() => {
    contextMeter.updateModel(settings.model)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.model])

  // ── Context: sync task switches ──
  useEffect(() => {
    if (selectedTaskId) {
      contextMeter.switchTask(selectedTaskId)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTaskId])

  useEffect(() => {
    if (!authUser?.uid) return
    void fetchSessions()
  }, [activeConversationId, authUser?.uid, fetchSessions])

  useEffect(() => {
    if (!sessions.length) return
    if (!selectedTaskId || !sessions.some((session) => session.session_id === selectedTaskId)) {
      setSelectedTaskId(sessions[0]?.session_id ?? MAIN_SESSION_ID)
    }
  }, [selectedTaskId, sessions])

  useEffect(() => {
    const targetSessionId = selectedTaskId ?? MAIN_SESSION_ID
    void fetchMessages(targetSessionId).then(setServerMessages)
  }, [fetchMessages, selectedTaskId])

  const scopedSubAgents = useMemo(() => {
    if (!selectedTaskId) return []
    return subAgents.filter((agent) => agent.parent_task_id === selectedTaskId)
  }, [selectedTaskId, subAgents])

  const scopedSubAgentSteps = useMemo(() => {
    const ids = new Set(scopedSubAgents.map((agent) => agent.sub_id))
    const scoped: typeof subAgentSteps = {}
    for (const [subId, steps] of Object.entries(subAgentSteps)) {
      if (ids.has(subId)) scoped[subId] = steps
    }
    return scoped
  }, [scopedSubAgents, subAgentSteps])


  const sessionSwitcherItems = useMemo<SessionSwitcherItem[]>(() => {
    const historyItems: SessionSwitcherItem[] = sessions.map((item) => ({
      id: item.session_id,
      label: item.title || (item.session_id === 'agent:main:main' ? 'main' : item.session_id.includes(':heartbeat') ? 'heartbeat' : 'Untitled session'),
      channel: 'chat',
      status: selectedTaskId === item.session_id && isWorking ? 'active' : 'idle',
      detail: item.session_id,
      group: item.session_id.endsWith(':main') || item.session_id.includes(':heartbeat')
        ? 'main'
        : (item.session_id.includes(':telegram:') || item.session_id.includes(':discord:') || item.session_id.includes(':slack:'))
          ? 'channels'
          : 'other',
    }))

    const subAgentItems: SessionSwitcherItem[] = subAgents.map((agent) => ({
      id: agent.sub_id,
      label: `${subAgentDisplayName(agent)} · ${agent.instruction.slice(0, 28)}`,
      channel: 'system',
      status: (agent.status === 'running' || agent.status === 'spawning') ? 'active' : 'idle',
      detail: agent.instruction,
      group: 'other',
    }))

    const merged = [...subAgentItems, ...historyItems]
    const deduped = new Map<string, SessionSwitcherItem>()
    for (const item of merged) {
      if (!deduped.has(item.id)) deduped.set(item.id, item)
    }
    return Array.from(deduped.values())
  }, [isWorking, selectedTaskId, sessions, subAgents])

  const mergedChatMessages = useMemo(() => {
    if (!selectedTaskId) return serverMessages
    const optimistic = optimisticMessagesByTask[selectedTaskId] ?? []
    if (!optimistic.length) return serverMessages
    const dedupedOptimistic = optimistic.filter((optimisticMsg) => (
      !serverMessages.some((serverMsg) => (
        serverMsg.role === 'user' &&
        serverMsg.content.trim() === optimisticMsg.content.trim()
      ))
    ))
    return [...serverMessages, ...dedupedOptimistic]
  }, [optimisticMessagesByTask, selectedTaskId, serverMessages])

  const visibleLogs: LogEntry[] = useMemo(() => {
    if (!selectedTaskId) return logs
    const filtered = logs.filter((entry) => entry.taskId === selectedTaskId)
    if (filtered.length > 0) return filtered

    // Rehydrate log timeline from persisted server messages metadata.
    const restoredFromServer = serverMessages
      .map((msg, idx) => {
        const metadata = (msg.metadata ?? {}) as Record<string, unknown>
        const action = String(metadata.action ?? '')
        if (action === 'step') {
          const stepObj = (metadata.step ?? {}) as Record<string, unknown>
          return {
            id: `restored-step-${msg.id}-${idx}`,
            taskId: selectedTaskId,
            message: String(stepObj.content ?? msg.content),
            timestamp: msg.created_at ? new Date(msg.created_at).toLocaleTimeString() : new Date().toLocaleTimeString(),
            type: 'step' as const,
            status: 'completed' as const,
            stepKind: 'other' as const,
            elapsedSeconds: 0,
          }
        }
        if (action === 'workflow_step') {
          const wf = (metadata.workflow_step ?? {}) as Record<string, unknown>
          return {
            id: `restored-wf-${msg.id}-${idx}`,
            taskId: selectedTaskId,
            message: String(wf.description ?? msg.content),
            timestamp: msg.created_at ? new Date(msg.created_at).toLocaleTimeString() : new Date().toLocaleTimeString(),
            type: 'step' as const,
            status: 'completed' as const,
            stepKind: 'other' as const,
            elapsedSeconds: 0,
          }
        }
        return null
      })
      .filter(Boolean) as LogEntry[]

    if (restoredFromServer.length > 0) return restoredFromServer

    return filtered
  }, [logs, selectedTaskId, serverMessages])

  // ── Inject compaction entries into visible logs ──
  const enrichedLogs: LogEntry[] = useMemo(() => {
    const result = [...visibleLogs]
    if (contextMeter.isCompacting) {
      result.push({
        id: '__compacting__',
        taskId: selectedTaskId ?? 'idle',
        message: 'Automatically compacting context…',
        timestamp: new Date().toLocaleTimeString(),
        type: 'step',
        status: 'in_progress',
        stepKind: 'other',
        elapsedSeconds: 0,
      })
    }
    return result
  }, [visibleLogs, contextMeter.isCompacting, selectedTaskId])


  const handleSend = useCallback((instruction: string, metadata?: Record<string, unknown>) => {
    const trimmed = instruction.trim()
    if (!trimmed) return
    const mentionMatches = [...trimmed.matchAll(/@([a-zA-Z0-9._-]+)/g)].map((m) => m[1].toLowerCase())
    const mentionedAgents = subAgentsRef.current.filter((agent) =>
      mentionMatches.includes(subAgentDisplayName(agent).toLowerCase()),
    )
    const cleanedInstruction = trimmed.replace(/@[a-zA-Z0-9._-]+/g, '').replace(/\s{2,}/g, ' ').trim()
    const finalInstruction = cleanedInstruction || trimmed

    const outboundMetadata = { ...(metadata ?? {}) }
    const preferredRuntimeAction = typeof outboundMetadata.runtime_control_action === 'string'
      ? outboundMetadata.runtime_control_action
      : undefined
    delete outboundMetadata.runtime_control_action
    const runtimeControlAction: Exclude<SteeringMode, 'auto'> | null = isWorking
      ? (preferredRuntimeAction === 'interrupt' || preferredRuntimeAction === 'queue' || preferredRuntimeAction === 'steer'
        ? preferredRuntimeAction
        : 'steer')
      : null
    if (import.meta.env.DEV && 'viewMode' in outboundMetadata) {
      console.warn('[AegisUI] viewMode metadata detected on execution payload; execution routing must remain view-agnostic.')
    }
    send({ action: 'config', settings: wsConfig })

    const isNewTask = !isWorking
    const action = runtimeControlAction ?? 'execute'
    console.info('[AegisUI] action=%s route=%s', action, isNewTask ? 'new_task' : 'runtime_control')
    const sent = send({
      action,
      instruction: finalInstruction,
      metadata: {
        ...outboundMetadata,
        target_subagents: mentionedAgents.map((a) => a.sub_id),
      },
    })
    if (!sent) {
      setPendingNavigation({ instruction: finalInstruction, metadata })
      toastCtx.error('Connection issue', 'Task was not sent. Please wait for reconnect and retry.')
      return
    }
    setPendingNavigation(null)
    mentionedAgents.forEach((agent) => { void messageSubAgent(agent.sub_id, finalInstruction) })

    const targetSessionId = selectedTaskId ?? MAIN_SESSION_ID
    if (isNewTask) {
      setOptimisticMessagesByTask((prev) => {
        const existing = prev[targetSessionId] ?? []
        if (existing.some((msg) => msg.role === 'user' && msg.content.trim() === finalInstruction.trim())) {
          return prev
        }
        const optimisticMessage: ServerMessage = {
          id: `optimistic-${targetSessionId}-${existing.length + 1}`,
          role: 'user',
          content: finalInstruction,
          metadata: null,
          created_at: new Date().toISOString(),
        }
        return {
          ...prev,
          [targetSessionId]: [...existing, optimisticMessage],
        }
      })
      setSelectedTaskId(targetSessionId)
    }
  }, [
    isWorking,
    messageSubAgent,
    selectedTaskId,
    send,
    toastCtx,
    wsConfig,
  ])

  const dispatchPromptFromUI = (instruction: string, metadata?: Record<string, unknown>) => {
    console.info('[AegisUI] dispatch_source=chat_input websocket_action=navigate')
    handleSend(instruction, metadata)
  }

  useEffect(() => {
    if (connectionStatus !== 'connected' || !pendingNavigation) return
    handleSend(pendingNavigation.instruction, pendingNavigation.metadata)
  }, [connectionStatus, handleSend, pendingNavigation])

  const handleDecomposePlan = async (prompt: string) => {
    const trimmed = prompt.trim()
    if (!trimmed) return
    try {
      const resp = await fetch(apiUrl('/api/plans/decompose'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ prompt: trimmed, provider: settings.provider, model: settings.model }),
      })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok && data?.ok && data?.plan?.id) {
        setActivePlanId(data.plan.id as string)
      }
    } catch {
      // silent - plan decompose errors are non-fatal
    }
  }

  const handleUserInputResponse = (answer: string, requestId: string) => {
    send({ action: 'user_input_response', request_id: requestId, response: answer })
  }

  const handlePlanConfirm = (requestId: string) => {
    send({ action: 'plan_confirm_response', request_id: requestId, response: 'Approve' })
  }

  const handlePlanReject = (requestId: string) => {
    send({ action: 'plan_confirm_response', request_id: requestId, response: 'Cancel' })
  }

  const newSession = () => {
    send({ action: 'stop_task' })
    setTaskStartedAt(null)
    setDurationSeconds(0)
    resetClientState()
    resetUsageSession()
    contextMeter.reset()
    setSelectedTaskId(MAIN_SESSION_ID)
    setOptimisticMessagesByTask({})
    void stopVoice()
  }

  const openDocsHome = () => navigateTo('/docs')
  const openDoc = (slug: string) => navigateTo(docsPath(slug))
  const openAuth = () => navigateTo('/auth')
  const openHome = () => navigateTo('/')

  if (!isAuthenticated) {
    if (authLoading) {
      return (
        <main className='flex h-screen items-center justify-center bg-[#111] text-zinc-100'>
          <div className='rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2 text-sm text-zinc-400'>Checking session...</div>
        </main>
      )
    }
    if (isDocsRoute) {
      return <EmbeddedDocsPage slug={docsSlug} onGoHome={openHome} onGoAuth={openAuth} onGoDocsHome={openDocsHome} onNavigateToSlug={openDoc} />
    }
    if (isPrivacyRoute) {
      return <PrivacyPage onGoHome={openHome} onGoAuth={openAuth} />
    }
    if (isTermsRoute) {
      return <TermsPage onGoHome={openHome} onGoAuth={openAuth} />
    }
    if (isUseCaseRoute) {
      const ucId = pathname.replace('/use-case/', '')
      return (
        <UseCasePage
          useCaseId={activeUseCaseId ?? ucId}
          onBack={openHome}
          onGetStarted={openAuth}
          onOpenDocsHome={openDocsHome}
          onOpenDoc={openDoc}
        />
      )
    }
    if (!isAuthRoute) {
      return (
        <LandingPage
          onGetStarted={openAuth}
          onOpenDocsHome={openDocsHome}
          onOpenDoc={openDoc}
          docsPortalHref={getStandaloneDocUrl()}
          onBuyCredits={(plan) => {
            sessionStorage.setItem('aegis.pendingPlan', plan)
            setPendingPlan(plan)
            openAuth()
          }}
          onOpenUseCase={(id) => {
            setActiveUseCaseId(id)
            navigateTo(`/use-case/${id}`)
          }}
        />
      )
    }
    return (
      <AuthPage
        onAuthenticated={(user) => {
          setAuthUser(user)
          setIsAuthenticated(true)
          const pending = sessionStorage.getItem('aegis.pendingPlan')
          if (pending) {
            sessionStorage.removeItem('aegis.pendingPlan')
            setPendingPlan(null)
            navigateTo('/')
            setShowSettings(true)
            setSettingsInitialTab('Credits')
          } else if (!isOnboardingComplete()) {
            setShowOnboarding(true)
            navigateTo('/')
          } else {
            toastCtx.success('Welcome back!', `Signed in as ${user.name || user.email}`)
            navigateTo('/')
          }
        }}
        onBack={openHome}
        onOpenDocsHome={openDocsHome}
        onOpenDoc={openDoc}
      />
    )
  }

  if (isDocsRoute) {
    return <EmbeddedDocsPage slug={docsSlug} onGoHome={openHome} onGoAuth={openAuth} onGoDocsHome={openDocsHome} onNavigateToSlug={openDoc} />
  }
  if (isPrivacyRoute) {
    return <PrivacyPage onGoHome={openHome} onGoAuth={openAuth} />
  }
  if (isTermsRoute) {
    return <TermsPage onGoHome={openHome} onGoAuth={openAuth} />
  }

  return (
    <>
      {isImpersonating && <ImpersonationBanner email={impersonationStatus?.target_user?.email ?? authUser?.email ?? ''} />}
      <main className={`h-[100dvh] overflow-x-hidden bg-[#111] p-1.5 text-zinc-100 sm:p-2 lg:p-3 ${isImpersonating ? 'pt-10' : ''}`}>
      {showOnboarding && (
        <OnboardingWizard
          userName={authUser?.name ?? settings.displayName}
          userEmail={authUser?.email ?? settings.email}
          onComplete={(data) => {
            patchSettings({ displayName: data.displayName })
            setShowOnboarding(false)
            if (!isTourComplete()) setShowTour(true)
            toastCtx.success('Welcome!', `Let's get started, ${data.displayName.split(' ')[0]}!`)
          }}
        />
      )}
      {showTour && <ProductTour onComplete={() => setShowTour(false)} />}
      <div className='mx-auto flex h-full max-w-[1750px] gap-1.5 sm:gap-2 lg:gap-3'>
        {/* ───────────── Sidebar ───────────── */}
        {/* Mobile backdrop */}
        {sidebarOpen && (
          <div className='fixed inset-0 z-20 bg-black/60 backdrop-blur-sm lg:hidden' onClick={() => setSidebarOpen(false)} />
        )}
        <aside data-tour='sidebar' className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] lg:translate-x-0'} fixed inset-y-1.5 left-1.5 z-30 w-[260px] rounded-2xl border border-[var(--ds-border-subtle)] bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.14),_transparent_52%),linear-gradient(180deg,var(--ds-surface-2)_0%,var(--ds-surface-1)_100%)] p-3 shadow-[var(--ds-shadow-elevated)] transition sm:inset-y-2 sm:left-2 sm:w-[280px] lg:static lg:inset-y-3 lg:left-3 lg:translate-x-0 flex min-h-0 flex-col`}>
          <button type='button' onClick={() => { newSession(); setShowAutomations(false); setShowSettings(false); setSidebarOpen(false); navigateTo('/') }} className='mb-3 flex min-h-11 w-full items-center justify-center rounded-xl border border-[var(--ds-border-accent)] bg-[var(--ds-accent-soft)] px-3 text-sm font-medium text-[var(--ds-text-primary)] transition-colors hover:bg-[var(--ds-accent-soft-hover)] cursor-pointer'>
            New Session
          </button>

          <div className='min-h-0 flex-1 overflow-y-auto scrollbar-thin'>
            <div className='space-y-4 pr-1'>
              <SidebarSection title='Dashboard'>
                <NavItem icon={Icons.user({ className: 'h-3.5 w-3.5' })} label='Profile' active={pathname === '/settings/profile'} onClick={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.chat({ className: 'h-3.5 w-3.5' })} label='Chat' active={pathname === '/' && !showSettings && !showAutomations} onClick={() => { navigateTo('/'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.alert({ className: 'h-3.5 w-3.5' })} label='Observability' active={pathname === '/settings/observability'} onClick={() => { navigateTo('/settings/observability'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.folder({ className: 'h-3.5 w-3.5' })} label='Sessions' active={isSessionsPath} onClick={() => { navigateTo('/sessions'); setSidebarOpen(false) }} />
              </SidebarSection>

              <SidebarSection title='Agent & AI' defaultCollapsed>
                <NavItem icon={Icons.clock({ className: 'h-3.5 w-3.5' })} label='Automations' active={showAutomations} onClick={() => { navigateTo('/automations'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.globe({ className: 'h-3.5 w-3.5' })} label='Connections' active={pathname === '/settings/connections'} onClick={() => { navigateTo('/settings/connections'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.folder({ className: 'h-3.5 w-3.5' })} label='Memory' active={pathname === '/settings/memory'} onClick={() => { navigateTo('/settings/memory'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.settings({ className: 'h-3.5 w-3.5' })} label='Agent Configuration' active={pathname === '/settings/agent-configuration'} onClick={() => { navigateTo('/settings/agent-configuration'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.star({ className: 'h-3.5 w-3.5' })} label='Skills' active={pathname === '/settings/skills'} onClick={() => { navigateTo('/settings/skills'); setSidebarOpen(false) }} />
              </SidebarSection>

              <SidebarSection title='Settings' defaultCollapsed>
                <NavItem icon={Icons.lock({ className: 'h-3.5 w-3.5' })} label='API Keys' active={pathname === '/settings/api-keys'} onClick={() => { navigateTo('/settings/api-keys'); setSidebarOpen(false) }} />
                <NavItem icon={Icons.chat({ className: 'h-3.5 w-3.5' })} label='Support' active={pathname === '/settings/support'} onClick={() => { navigateTo('/settings/support'); setSidebarOpen(false) }} />
                {isAdmin && (
                  <NavItem icon={<LuShield className='h-3.5 w-3.5' />} label='Admin' active={isAdminPath} onClick={() => { navigateTo('/admin'); setSidebarOpen(false) }} />
                )}
                <NavItem icon={Icons.settings({ className: 'h-3.5 w-3.5' })} label='Billing' active={pathname === '/settings/credits' || pathname === '/settings/invoices' || pathname === '/settings/billing'} onClick={() => { navigateTo('/settings/billing'); setSidebarOpen(false) }} />
              </SidebarSection>
            </div>
          </div>

          <div className='mt-3 space-y-2 border-t border-[var(--ds-border-strong)] bg-[linear-gradient(180deg,transparent_0%,var(--ds-surface-2)_100%)] pt-3 text-xs'>
            <UsageDropdown
              balance={balance}
              context={{
                current: contextMeter.current,
                percent: contextMeter.percent,
                isCompacting: contextMeter.isCompacting,
                source: contextMeter.source,
                buckets: contextMeter.buckets,
                projectedPct: contextMeter.projectedPct,
                compactThresholdPct: contextMeter.compactThresholdPct,
              }}
              modelLabel={currentModelLabel}
            />
            <UserMenu
              name={authUser?.name ?? settings.displayName}
              avatarUrl={authUser?.avatar_url ?? settings.avatarUrl}
              onOpenSettings={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }}
              onSignOut={async () => {
                await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
                setAuthUser(null)
                setIsAuthenticated(false)
                setSelectedTaskId(MAIN_SESSION_ID)
                window.location.href = '/'
              }}
            />
          </div>
        </aside>

        {/* ───────────── Main content ───────────── */}
        <section className='flex min-h-0 min-w-0 flex-1 flex-col gap-1.5 overflow-x-hidden sm:gap-2 lg:gap-3'>
          <div className='space-y-1.5 sm:space-y-2'>
            <HeaderBar
              left={(
              <div className='flex min-w-0 items-center gap-1.5 sm:gap-2'>
                <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] p-1.5 text-xs lg:hidden' aria-label='Toggle sidebar'>
                  {Icons.menu({ className: 'h-4 w-4' })}
                </button>
                <img src='/aegis-shield.png' alt='Aegis' className='h-5 w-5 sm:h-6 sm:w-6 object-contain mix-blend-screen' />
                <h1 className='text-sm font-semibold sm:text-lg'>Aegis</h1>
              </div>
              )}
              right={(
              <div className='flex shrink-0 items-center gap-1.5 text-[10px] text-zinc-300 sm:gap-3 sm:text-xs'>
                <span className='inline-flex items-center gap-1 rounded-full border border-[#2a2a2a] px-1.5 py-0.5 sm:px-2 sm:py-1'>
                  <span className={`h-2 w-2 rounded-full sm:h-2.5 sm:w-2.5 ${connectionLabel.cls}`} /> <span className='hidden xs:inline'>{connectionLabel.label}</span>
                </span>
                <span className='hidden sm:inline'>Session {Math.floor(durationSeconds / 60)}:{String(durationSeconds % 60).padStart(2, '0')}</span>
                <NotificationBell />
                <span className='hidden text-[10px] text-zinc-600 sm:inline'>v{appVersion}</span>
                <button type='button' onClick={newSession} className='rounded-md border border-[#2a2a2a] px-2 py-1 hover:border-blue-500/60 hover:bg-zinc-900 sm:px-3 sm:py-1.5'>New</button>
              </div>
              )}
            />
          </div>

          <div className='min-h-0 flex-1'>
            {showSettings || isAdminPath ? (
              activeSettingsTab && STANDALONE_SETTINGS_TABS.has(activeSettingsTab) ? (
                <StandaloneSettingsPage
                  tab={activeSettingsTab}
                  settings={settings}
                  onPatch={patchSettings}
                  isAdmin={authUser?.role === 'admin' || authUser?.role === 'superadmin'}
                  authRole={authUser?.role}
                />
              ) : (
                <SettingsPage
                  onBack={() => { setShowSettings(false); setSettingsInitialTab(undefined); navigateTo('/') }}
                  initialTab={activeSettingsTab}
                  isAdmin={authUser?.role === 'admin' || authUser?.role === 'superadmin'}
                  authRole={authUser?.role}
                  onTabChange={(tab) => {
                    const base = isAdminPath ? '/admin' : '/settings'
                    navigateTo(`${base}/${settingsSlugForTab(tab)}`)
                  }}
                />
              )
            ) : showAutomations ? (
              <AutomationsPage />
            ) : isSessionsPath ? (
              <div className='h-full overflow-y-auto p-2'>
                {Array.isArray(sessions) ? (
                  <SessionsPage
                    sessions={sessions}
                    onRefresh={fetchSessions}
                    onSaveLabel={saveSessionLabel}
                    onOpenSession={(sessionId) => {
                      setSelectedTaskId(sessionId)
                      navigateTo('/')
                    }}
                  />
                ) : (
                  <div className='rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200'>
                    Sessions page failed to load. Please refresh and try again.
                  </div>
                )}
              </div>
            ) : activePlanId ? (
              <div className='h-full overflow-y-auto p-2'>
                <TaskPlanView planId={activePlanId} onClose={() => setActivePlanId(null)} />
              </div>
            ) : (
              <ChatPanel
                logs={enrichedLogs}
                isWorking={isWorking}
                steeringMode={settings.steeringMode}
                onPrimarySend={dispatchPromptFromUI}
                onSteeringModeChange={(nextMode) => patchSettings({ steeringMode: nextMode })}
                onDecomposePlan={handleDecomposePlan}
                connectionStatus={connectionStatus}
                transcripts={transcripts.map((t) => t.text)}
                voiceActive={voiceActive}
                onToggleVoice={toggleVoice}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                activeTaskId={selectedTaskId}
                serverMessages={mergedChatMessages}
                onStop={() => send({ action: 'stop_task' })}
                onUserInputResponse={handleUserInputResponse}
                onPlanConfirm={handlePlanConfirm}
                onPlanReject={handlePlanReject}
                activityStatusLabel={activityStatusLabel}
                activityDetail={activityDetailText}
                isActivityVisible={isActivityVisible}
                provider={settings.provider}
                model={settings.model}
                reasoningEffort={settings.reasoningEffort}
                onReasoningEffortChange={(nextEffort) => patchSettings({ reasoningEffort: nextEffort, enableReasoning: nextEffort !== 'none' })}
                onProviderChange={(nextProvider) => {
                  const providerMeta = PROVIDERS.find((item) => item.id === nextProvider) ?? PROVIDERS[0]
                  patchSettings({ provider: nextProvider, model: providerMeta.models[0].id })
                }}
                onModelChange={(nextModel) => patchSettings({ model: nextModel })}
                contextSnapshot={{
                  tokensUsed: contextMeter.current.tokensUsed,
                  contextLimit: contextMeter.current.contextLimit,
                  modelId: contextMeter.current.modelId,
                  isCompacting: contextMeter.isCompacting,
                }}
                subAgentNames={scopedSubAgents.map((agent) => subAgentDisplayName(agent))}
                sessions={sessionSwitcherItems}
                selectedSessionId={selectedTaskId}
                onSessionSwitch={(sessionId) => {
                  setSelectedTaskId(sessionId)
                  setSidebarOpen(false)
                }}
              />
            )}
          </div>

          {/* ── Stop button - overlays the send area while agent is working ── */}
          {!showSettings && !showAutomations && scopedSubAgents.length > 0 && (
            <div className='px-3 pb-2'>
              <SubAgentPanel
                agents={scopedSubAgents}
                steps={scopedSubAgentSteps}
                onCancel={cancelSubAgent}
                onMessage={messageSubAgent}
                onOpenThread={(subId) => {
                  // Switch to the sub-agent's task context by selecting its task id
                  const agent = subAgents.find((a) => a.sub_id === subId)
                  if (agent) setSelectedTaskId(agent.sub_id)
                }}
              />
            </div>
          )}

          <SpendingAlert balance={balance} />
        </section>
      </div>
      {showChangelog && (
        <ChangelogModal
          onClose={() => {
            dismissChangelog()
            window.setTimeout(() => {
              if (!localStorage.getItem('aegis_seen_subagent_modal')) setShowSubAgentModal(true)
            }, 800)
          }}
        />
      )}
      {showSubAgentModal && (
        <SubAgentModal
          onClose={() => {
            localStorage.setItem('aegis_seen_subagent_modal', '1')
            setShowSubAgentModal(false)
          }}
          onTryNow={() => {
            localStorage.setItem('aegis_seen_subagent_modal', '1')
            setShowSubAgentModal(false)
            handleSend('spawn sub-agents: ', { task_label_source: 'chat', task_label: 'spawn sub-agents' })
          }}
        />
      )}
      </main>
    </>
  )
}

export default App
