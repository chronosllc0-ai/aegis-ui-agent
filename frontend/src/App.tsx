import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ActionLog } from './components/ActionLog'
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
import { ScreenView } from './components/ScreenView'
import { SpendingAlert } from './components/SpendingAlert'
import { UsageDropdown } from './components/UsageDropdown'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { TaskPlanView } from './components/TaskPlanView'
import { Icons } from './components/icons'
import { ChatPanel } from './components/ChatPanel'
import type { SessionSwitcherItem } from './components/SessionSwitcher'
import { SubAgentPanel } from './components/SubAgentPanel'
import { UseCasePage } from './components/UseCasePage'
import { SettingsPage } from './components/settings/SettingsPage'
import type { SettingsTab } from './components/settings/SettingsPage'
import { AutomationsPage } from './components/AutomationsPage'
import { ImpersonationBanner } from './components/admin/ImpersonationBanner'
import { useImpersonation } from './components/admin/useImpersonation'
import { useToast } from './hooks/useToast'
import { useContextMeter } from './hooks/useContextMeter'
import { useSettingsContext } from './context/useSettingsContext'
import { useMicrophone } from './hooks/useMicrophone'
import { useUsage } from './hooks/useUsage'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { useSessions, type ServerMessage } from './hooks/useSessions'
import { apiUrl } from './lib/api'
import { LuShield } from 'react-icons/lu'
import { modelInfo, PROVIDERS } from './lib/models'
import { modeLabel, normalizeAgentMode } from './lib/agentModes'
import { docsPath, navigateTo, usePathname, PRIVACY_PATH, TERMS_PATH } from './lib/routes'
import { isBrowserPrimitiveActionLogEntry } from './lib/actionLogFilter'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

type ViewMode = 'browser' | 'chat'

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
  const { connectionStatus, isWorking, activityStatusLabel, activityDetail, isActivityVisible, activeExecutionMode, handoffActive, handoffRequestId, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, clearFrameCache, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, messageSubAgent, cancelSubAgent } = useWebSocket({
    onUsageMessage: handleUsageMessage,
    userId: authUser?.uid ?? null,
    activeThreadId: selectedTaskId,
  })
  const prevConnectionStatus = useRef(connectionStatus)
  const { settings, patchSettings, wsConfig } = useSettingsContext()
  const pathname = usePathname()

  const contextMeter = useContextMeter(settings.model)

  const [steeringFlashKey, setSteeringFlashKey] = useState(0)
  const [showSettings, setShowSettings] = useState(false)
  const [showAutomations, setShowAutomations] = useState(false)
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab | undefined>(undefined)
  const [showWorkflow, setShowWorkflow] = useState(false)
  const [urlInput, setUrlInput] = useState('about:blank')
  const [showSubAgentModal, setShowSubAgentModal] = useState(false)
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const { sessions, fetchMessages, fetchSessions } = useSessions(authUser?.uid ?? null)
  // Server messages loaded for the selected conversation
  const [serverMessages, setServerMessages] = useState<ServerMessage[]>([])
  const [optimisticMessagesByTask, setOptimisticMessagesByTask] = useState<Record<string, ServerMessage[]>>({})
  const browserGridRef = useRef<HTMLDivElement>(null)
  const [lastClickCoords, setLastClickCoords] = useState<{ x: number; y: number } | null>(null)

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [, setPendingPlan] = useState<string | null>(() => {
    return sessionStorage.getItem('aegis.pendingPlan')
  })
  const [activePlanId, setActivePlanId] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('browser')
  const [browserInstructionInput, setBrowserInstructionInput] = useState('')
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null)
  const [pendingNavigation, setPendingNavigation] = useState<{ instruction: string; metadata?: Record<string, unknown> } | null>(null)
  const subAgentsRef = useRef(subAgents)
  const [showBrowseHandoffPrompt, setShowBrowseHandoffPrompt] = useState(false)
  const promptShownTaskIdsRef = useRef<Set<string>>(new Set())
  const prevIsWorkingRef = useRef(false)
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
  const activityDetailWithMode = activityDetail
    ? `${activityDetail} · Mode: ${modeLabel(activeExecutionMode)}`
    : `Mode: ${modeLabel(activeExecutionMode)}`
  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true
  const isAdminPath = isAdmin && pathname.startsWith('/admin')
  const isSettingsPath = pathname.startsWith('/settings')
  const isAutomationsPath = pathname === '/automations'
  const { status: impersonationStatus, checkStatus } = useImpersonation()

  useEffect(() => {
    const normalizedActiveMode = normalizeAgentMode(activeExecutionMode)
    if (settings.activeMode === normalizedActiveMode) return
    patchSettings({ activeMode: normalizedActiveMode })
  }, [activeExecutionMode, normalizeAgentMode, patchSettings, settings.activeMode])

  useEffect(() => {
    if (isWorking) return
    const normalizedSelectedMode = normalizeAgentMode(settings.selectedMode)
    if (settings.activeMode === normalizedSelectedMode) return
    patchSettings({ activeMode: normalizedSelectedMode })
  }, [isWorking, normalizeAgentMode, patchSettings, settings.activeMode, settings.selectedMode])

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

  useEffect(() => {
    setUrlInput(currentUrl)
  }, [currentUrl])

  // Split-surface UX helpers:
  // 1) Contextual handoff prompt when browsing starts while user is in chat mode.
  // 2) Optional auto-return to chat when the task completes.
  useEffect(() => {
    const wasWorking = prevIsWorkingRef.current
    const startedWorking = !wasWorking && isWorking
    const finishedWorking = wasWorking && !isWorking
    prevIsWorkingRef.current = isWorking

    if (!settings.separateExecutionSurfaces) {
      setShowBrowseHandoffPrompt(false)
      return
    }

    if (startedWorking && viewMode === 'chat' && settings.promptToSwitchOnBrowse) {
      const activeTaskId = activeTaskIdRef.current
      if (activeTaskId && !promptShownTaskIdsRef.current.has(activeTaskId)) {
        promptShownTaskIdsRef.current.add(activeTaskId)
        setShowBrowseHandoffPrompt(true)
      }
    }

    if (finishedWorking) {
      setShowBrowseHandoffPrompt(false)
      if (viewMode === 'browser' && settings.autoReturnToChat) {
        setViewMode('chat')
        addNotification({
          type: 'info',
          title: 'Task complete',
          message: 'Browsing finished. Returned you to chat.',
          source: 'websocket',
        })
      }
    }
  }, [
    isWorking,
    viewMode,
    settings.separateExecutionSurfaces,
    settings.promptToSwitchOnBrowse,
    settings.autoReturnToChat,
    activeTaskIdRef,
    addNotification,
  ])

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
    setShowSettings(isSettingsPath || isAdminPath)
    setShowAutomations(isAutomationsPath)
    if (!isSettingsPath) return
    const slug = pathname.split('/')[2]
    if (!slug) {
      setSettingsInitialTab(undefined)
      return
    }
    const mapped = SETTINGS_ROUTE_MAP[slug]
    if (mapped) setSettingsInitialTab(mapped)
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
      clearFrameCache()
      setSelectedTaskId(null)
    }
    prevUserUidRef.current = nextUid
  }, [authUser?.uid, clearFrameCache])

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

  // ── Click coordinate extraction for ScreenView pulse overlay ──
  useEffect(() => {
    const lastClick = [...logs].reverse().find(l =>
      l.message?.startsWith('[click]') || l.stepKind === 'click'
    )
    if (lastClick) {
      const match = lastClick.message?.match(/"x":\s*(\d+).*?"y":\s*(\d+)/)
      if (match) {
        setLastClickCoords({ x: parseInt(match[1]), y: parseInt(match[2]) })
      }
    }
  }, [logs])

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

  const taskLabels = useMemo(
    () => Object.fromEntries(sessions.map((item) => [item.session_id, item.title])),
    [sessions],
  )

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
      label: item.title || 'Untitled session',
      channel: 'chat',
      status: selectedTaskId === item.session_id && isWorking ? 'active' : 'idle',
    }))

    const subAgentItems: SessionSwitcherItem[] = subAgents.map((agent) => ({
      id: agent.sub_id,
      label: `${subAgentDisplayName(agent)} · ${agent.instruction.slice(0, 28)}`,
      channel: 'system',
      status: (agent.status === 'running' || agent.status === 'spawning') ? 'active' : 'idle',
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

  const actionLogEntries = useMemo(
    () => enrichedLogs.filter((entry) => isBrowserPrimitiveActionLogEntry(entry)),
    [enrichedLogs],
  )
  const hasBrowserActivityForActiveTask = useMemo(() => {
    const activeTaskId = selectedTaskId ?? activeTaskIdRef.current
    if (!activeTaskId || activeTaskId === 'idle') return false
    return actionLogEntries.some((entry) => entry.taskId === activeTaskId)
  }, [actionLogEntries, selectedTaskId, activeTaskIdRef])

  // ── Auto-return to chat when a browser task finishes ────────────────────
  // When isWorking flips true→false and the task had browser activity,
  // automatically switch the user back to chat so they see the summary card.
  const prevBrowsingWorkingRef = useRef(isWorking)
  const browserActivityDuringRunRef = useRef(false)

  useEffect(() => {
    const wasWorking = prevBrowsingWorkingRef.current

    if (!wasWorking && isWorking) {
      browserActivityDuringRunRef.current = false
    }

    if (isWorking && hasBrowserActivityForActiveTask) {
      browserActivityDuringRunRef.current = true
    }

    if (wasWorking && !isWorking) {
      const hadBrowserActivityThisRun = browserActivityDuringRunRef.current
      browserActivityDuringRunRef.current = false
      if (hadBrowserActivityThisRun && viewMode === 'browser') {
        setViewMode('chat')
      }
    }

    prevBrowsingWorkingRef.current = isWorking
  }, [isWorking, hasBrowserActivityForActiveTask, viewMode])

  // ── Auto-switch to chat on ask_user_input while in browser mode ─────────
  // If the agent needs user input mid-task and the user is watching the
  // browser, jump them to chat so they see (and can answer) the question.
  useEffect(() => {
    if (!enrichedLogs.length || viewMode !== 'browser') return
    const last = enrichedLogs[enrichedLogs.length - 1]
    if (last?.message?.includes('[ask_user_input]') ||
        last?.message?.includes('[confirm_plan]') ||
        last?.message?.includes('[plan_steps]')) {
      setViewMode('chat')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enrichedLogs.length, viewMode])

  const handleSend = useCallback((instruction: string, metadata?: Record<string, unknown>) => {
    const trimmed = instruction.trim()
    if (!trimmed) return
    const mentionMatches = [...trimmed.matchAll(/@([a-zA-Z0-9._-]+)/g)].map((m) => m[1].toLowerCase())
    const mentionedAgents = subAgentsRef.current.filter((agent) =>
      mentionMatches.includes(subAgentDisplayName(agent).toLowerCase()),
    )
    const cleanedInstruction = trimmed.replace(/@[a-zA-Z0-9._-]+/g, '').replace(/\s{2,}/g, ' ').trim()
    const finalInstruction = cleanedInstruction || trimmed

    const selectedAgentMode = normalizeAgentMode(settings.selectedMode)
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

    setSteeringFlashKey((prev) => prev + 1)

    const isNewTask = !isWorking
    const action = runtimeControlAction ?? 'navigate'
    console.info('[AegisUI] action=%s route=%s', action, isNewTask ? 'new_task' : 'runtime_control')
    const sent = send({
      action,
      instruction: finalInstruction,
      metadata: {
        ...outboundMetadata,
        agent_mode: selectedAgentMode,
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
    settings.selectedMode,
    toastCtx,
    wsConfig,
  ])

  const dispatchPromptFromUI = (instruction: string, metadata?: Record<string, unknown>) => {
    console.info('[AegisUI] dispatch_source=chat_input websocket_action=navigate')
    handleSend(instruction, metadata)
  }

  const submitBrowserInstruction = useCallback(() => {
    const trimmed = browserInstructionInput.trim()
    if (!trimmed) return
    dispatchPromptFromUI(trimmed)
    setBrowserInstructionInput('')
  }, [browserInstructionInput, dispatchPromptFromUI])

  const routeBrowserCommandToChatComposer = useCallback((instruction: string) => {
    const trimmed = instruction.trim()
    if (!trimmed) return
    setPendingPrompt(trimmed)
    setShowBrowseHandoffPrompt(false)
    setViewMode('chat')
  }, [])

  useEffect(() => {
    if (connectionStatus !== 'connected' || !pendingNavigation) return
    handleSend(pendingNavigation.instruction, pendingNavigation.metadata)
  }, [connectionStatus, handleSend, pendingNavigation])

  const submitUrl = () => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    routeBrowserCommandToChatComposer(normalized)
  }

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

  const handleHandoffContinue = (requestId: string) => {
    send({ action: 'handoff_continue', request_id: requestId })
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
    setShowWorkflow(false)
    void stopVoice()
  }

  const saveWorkflow = () => {
    if (!visibleLogs.length) return

    const fallbackInstruction = visibleLogs.find(
      (entry) =>
        entry.isUserMessage === true ||
        (entry.type === 'step' &&
          entry.stepKind === 'navigate' &&
          !entry.message.toLowerCase().includes('session settings updated') &&
          !entry.message.toLowerCase().includes('queued instruction')),
    )?.message

    const instruction = fallbackInstruction ?? 'Saved workflow instruction'

    patchSettings({
      workflowTemplates: [
        ...settings.workflowTemplates,
        {
          id: crypto.randomUUID(),
          name: `Workflow ${settings.workflowTemplates.length + 1}`,
          instruction,
          stepCount: visibleLogs.length,
          lastRunAt: new Date().toISOString(),
        },
      ],
    })
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
        <aside data-tour='sidebar' className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] lg:translate-x-0'} fixed inset-y-1.5 left-1.5 z-30 w-[260px] rounded-2xl border border-[#2a2a2a] bg-gradient-to-b from-[#1a1f2d] via-[#191b26] to-[#171717] p-3 transition sm:inset-y-2 sm:left-2 sm:w-[280px] lg:static lg:inset-y-3 lg:left-3 lg:translate-x-0 flex min-h-0 flex-col`}>
          <button type='button' onClick={() => { newSession(); setShowAutomations(false); setShowSettings(false); setSidebarOpen(false); navigateTo('/') }} className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111]/60 px-3 py-2 text-left text-sm text-zinc-200'>
            ⌁ New Session
          </button>

          <div className='min-h-0 flex-1 overflow-y-auto scrollbar-thin'>
            <div className='space-y-4 pr-1'>
              <div>
                <p className='mb-2 px-1 text-[11px] uppercase tracking-wide text-zinc-500'>Dashboard</p>
                <div className='space-y-1'>
                  <button type='button' onClick={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/profile' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.user({ className: 'h-3.5 w-3.5' })}<span>Profile</span></button>
                  <button type='button' onClick={() => { navigateTo('/'); setViewMode('chat'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/' && viewMode === 'chat' && !showSettings && !showAutomations ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.chat({ className: 'h-3.5 w-3.5' })}<span>Chat</span></button>
                  <button type='button' onClick={() => { navigateTo('/'); setViewMode('browser'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/' && viewMode === 'browser' && !showSettings && !showAutomations ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.workflows({ className: 'h-3.5 w-3.5' })}<span>Sessions</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/observability'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/observability' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.alert({ className: 'h-3.5 w-3.5' })}<span>Observability</span></button>
                </div>
              </div>

              <div>
                <p className='mb-2 px-1 text-[11px] uppercase tracking-wide text-zinc-500'>Agent & AI</p>
                <div className='space-y-1'>
                  <button type='button' onClick={() => { navigateTo('/automations'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${showAutomations ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.clock({ className: 'h-3.5 w-3.5' })}<span>Automations</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/connections'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/connections' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.globe({ className: 'h-3.5 w-3.5' })}<span>Connections</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/memory'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/memory' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.folder({ className: 'h-3.5 w-3.5' })}<span>Memory</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/agent-configuration'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/agent-configuration' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.settings({ className: 'h-3.5 w-3.5' })}<span>Agent Configuration</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/skills'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/skills' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.star({ className: 'h-3.5 w-3.5' })}<span>Skills</span></button>
                </div>
              </div>

              <div>
                <p className='mb-2 px-1 text-[11px] uppercase tracking-wide text-zinc-500'>Settings</p>
                <div className='space-y-1'>
                  <button type='button' onClick={() => { navigateTo('/settings/api-keys'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/api-keys' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.lock({ className: 'h-3.5 w-3.5' })}<span>API Keys</span></button>
                  <button type='button' onClick={() => { navigateTo('/settings/support'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/support' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.chat({ className: 'h-3.5 w-3.5' })}<span>Support</span></button>
                  {isAdmin && (
                    <button type='button' onClick={() => { navigateTo('/admin'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${isAdminPath ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}><LuShield className='h-3.5 w-3.5' /><span>Admin</span></button>
                  )}
                  <button type='button' onClick={() => { navigateTo('/settings/billing'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left text-sm ${pathname === '/settings/credits' || pathname === '/settings/invoices' || pathname === '/settings/billing' ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a] text-zinc-200 hover:bg-zinc-800'}`}>{Icons.settings({ className: 'h-3.5 w-3.5' })}<span>Billing</span></button>
                </div>
              </div>
            </div>
          </div>

          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            <UsageDropdown
              balance={balance}
              context={{
                current: contextMeter.current,
                percent: contextMeter.percent,
                isCompacting: contextMeter.isCompacting,
              }}
              modelLabel={currentModelLabel}
            />
            <UserMenu
              name={authUser?.name ?? settings.displayName}
              avatarUrl={authUser?.avatar_url ?? settings.avatarUrl}
              onOpenSettings={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }}
              onSignOut={async () => {
                await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
                clearFrameCache()
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
          <header className='space-y-1.5 sm:space-y-2'>
            <div className='flex items-center justify-between gap-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:rounded-2xl sm:px-4 sm:py-2'>
              <div className='flex min-w-0 items-center gap-1.5 sm:gap-2'>
                <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] p-1.5 text-xs lg:hidden' aria-label='Toggle sidebar'>
                  {Icons.menu({ className: 'h-4 w-4' })}
                </button>
                <img src='/aegis-shield.png' alt='Aegis' className='h-5 w-5 sm:h-6 sm:w-6 object-contain mix-blend-screen' />
                <h1 className='text-sm font-semibold sm:text-lg'>Aegis</h1>
                {/* ── Chat ↔ Browser mode switcher ── */}
                {!showSettings && !showAutomations && (
                  <div className='ml-1 flex max-w-[42vw] shrink items-center gap-0.5 overflow-hidden rounded-full border border-[#2a2a2a] bg-[#111] p-0.5 sm:max-w-none'>
                    <button
                      type='button'
                      onClick={() => setViewMode('browser')}
                      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === 'browser' ? 'bg-[#2a2a2a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                    >
                      {Icons.globe({ className: 'h-3 w-3' })}
                      <span className='hidden xs:inline'>Browser</span>
                    </button>
                    <button
                      type='button'
                      onClick={() => setViewMode('chat')}
                      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === 'chat' ? 'bg-[#2a2a2a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                    >
                      {Icons.chat({ className: 'h-3 w-3' })}
                      <span className='hidden xs:inline'>Chat</span>
                    </button>
                  </div>
                )}
              </div>
              <div className='flex shrink-0 items-center gap-1.5 text-[10px] text-zinc-300 sm:gap-3 sm:text-xs'>
                <span className='inline-flex items-center gap-1 rounded-full border border-[#2a2a2a] px-1.5 py-0.5 sm:px-2 sm:py-1'>
                  <span className={`h-2 w-2 rounded-full sm:h-2.5 sm:w-2.5 ${connectionLabel.cls}`} /> <span className='hidden xs:inline'>{connectionLabel.label}</span>
                </span>
                <span className='hidden sm:inline'>Session {Math.floor(durationSeconds / 60)}:{String(durationSeconds % 60).padStart(2, '0')}</span>
                <NotificationBell />
                <span className='hidden text-[10px] text-zinc-600 sm:inline'>v{appVersion}</span>
                <button type='button' onClick={newSession} className='rounded-md border border-[#2a2a2a] px-2 py-1 hover:border-blue-500/60 hover:bg-zinc-900 sm:px-3 sm:py-1.5'>New</button>
              </div>
            </div>
          </header>

          {!showSettings && !showAutomations && viewMode === 'browser' && (
            <section className='flex items-center gap-1 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:gap-2 sm:rounded-2xl sm:px-3 sm:py-2'>
              <button type='button' onClick={() => routeBrowserCommandToChatComposer('go back')} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Back'>
                {Icons.back({ className: 'h-4 w-4' })}
              </button>
              <button type='button' onClick={() => routeBrowserCommandToChatComposer('go forward')} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Forward'>
                {Icons.chevronRight({ className: 'h-4 w-4' })}
              </button>
              <span className='text-xs text-zinc-400'>{Icons.globe({ className: 'h-3.5 w-3.5' })}</span>
              <input aria-label='URL address' value={urlInput} onChange={(event) => setUrlInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submitUrl()} className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs outline-none focus:border-blue-500/70 sm:text-sm md:text-xl' />
              <button type='button' onClick={submitUrl} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800 sm:px-3'>Go</button>
            </section>
          )}
          {!showSettings && !showAutomations && viewMode === 'browser' && (
            <section className='flex items-center gap-1 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:gap-2 sm:rounded-2xl sm:px-3 sm:py-2'>
              <span className='text-xs text-zinc-400'>{Icons.chat({ className: 'h-3.5 w-3.5' })}</span>
              <input
                aria-label='Send instruction'
                value={browserInstructionInput}
                onChange={(event) => setBrowserInstructionInput(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && !event.shiftKey && !event.ctrlKey && !event.altKey && submitBrowserInstruction()}
                placeholder='Send instruction from browser view (same execution path as chat)'
                className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs outline-none focus:border-blue-500/70 sm:text-sm'
              />
              <button type='button' onClick={submitBrowserInstruction} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800 sm:px-3'>Send</button>
            </section>
          )}

          <div className='min-h-0 flex-1'>
            {showSettings || isAdminPath ? (
              <SettingsPage
                onBack={() => { setShowSettings(false); setSettingsInitialTab(undefined); navigateTo('/') }}
                initialTab={isAdminPath ? 'Admin' : settingsInitialTab}
                isAdmin={authUser?.role === 'admin' || authUser?.role === 'superadmin'}
                authRole={authUser?.role}
                onTabChange={(tab) => {
                  const base = isAdminPath ? '/admin' : '/settings'
                  navigateTo(`${base}/${settingsSlugForTab(tab)}`)
                }}
              />
            ) : showAutomations ? (
              <AutomationsPage />
            ) : activePlanId ? (
              <div className='h-full overflow-y-auto p-2'>
                <TaskPlanView planId={activePlanId} onClose={() => setActivePlanId(null)} />
              </div>
            ) : viewMode === 'chat' ? (
              <ChatPanel
                logs={enrichedLogs}
                isWorking={isWorking}
                steeringMode={settings.steeringMode}
                onPrimarySend={dispatchPromptFromUI}
                onSteeringModeChange={(nextMode) => patchSettings({ steeringMode: nextMode })}
                onDecomposePlan={handleDecomposePlan}
                connectionStatus={connectionStatus}
                transcripts={transcripts.map((t) => t.text)}
                onSwitchToBrowser={() => { setShowBrowseHandoffPrompt(false); setViewMode('browser') }}
                latestFrame={latestFrame}
                voiceActive={voiceActive}
                onToggleVoice={toggleVoice}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                activeTaskId={selectedTaskId}
                serverMessages={mergedChatMessages}
                onStop={() => send({ action: 'stop_task' })}
                onUserInputResponse={handleUserInputResponse}
                onPlanConfirm={handlePlanConfirm}
                onPlanReject={handlePlanReject}
                onHandoffContinue={handleHandoffContinue}
                activityStatusLabel={activityStatusLabel}
                activityDetail={activityDetailWithMode}
                isActivityVisible={isActivityVisible}
                provider={settings.provider}
                model={settings.model}
                selectedMode={settings.selectedMode}
                activeMode={settings.activeMode}
                modeLocked={settings.activeMode !== settings.selectedMode}
                onProviderChange={(nextProvider) => {
                  const providerMeta = PROVIDERS.find((item) => item.id === nextProvider) ?? PROVIDERS[0]
                  patchSettings({ provider: nextProvider, model: providerMeta.models[0].id })
                }}
                onModelChange={(nextModel) => patchSettings({ model: nextModel })}
                onAgentModeChange={(nextMode) => patchSettings({ selectedMode: nextMode, activeMode: nextMode })}
                contextSnapshot={{
                  tokensUsed: contextMeter.current.tokensUsed,
                  contextLimit: contextMeter.current.contextLimit,
                  modelId: contextMeter.current.modelId,
                  isCompacting: contextMeter.isCompacting,
                }}
                subAgentNames={scopedSubAgents.map((agent) => subAgentDisplayName(agent))}
                browseHandoffPromptVisible={settings.separateExecutionSurfaces && showBrowseHandoffPrompt}
                onDismissBrowsePrompt={() => setShowBrowseHandoffPrompt(false)}
                pendingPrompt={pendingPrompt}
                onPendingPromptConsumed={() => setPendingPrompt(null)}
                sessions={sessionSwitcherItems}
                selectedSessionId={selectedTaskId}
                onSessionSwitch={(sessionId) => {
                  setSelectedTaskId(sessionId)
                  setSidebarOpen(false)
                }}
              />
            ) : (
              /* Browser layout - ScreenView full height, ActionLog as floating overlay on desktop */
              <div
                ref={browserGridRef}
                className='relative flex h-full min-h-0 flex-col gap-1.5 sm:gap-2 lg:gap-3'
              >
                {/* Main content (screen / workflow) - full width */}
                <div className='min-h-0 min-w-0 flex-1'>
                  {showWorkflow ? (
                    <WorkflowView steps={workflowSteps} />
                  ) : (
                    <ScreenView
                      frameSrc={latestFrame}
                      isWorking={isWorking}
                      handoffActive={handoffActive}
                      onHumanBrowserAction={(action) => send({ action: 'human_browser_action', ...action })}
                      onHandoffContinue={handoffRequestId ? () => handleHandoffContinue(handoffRequestId) : undefined}
                      steeringFlashKey={steeringFlashKey}
                      onExampleClick={(prompt) => {
                        console.info('[AegisUI] example_click -> send prompt immediately')
                        dispatchPromptFromUI(prompt)
                      }}
                      dataTour='screen-view'
                      lastClickCoords={lastClickCoords}
                    />
                  )}
                </div>

                {/* Action log - stacked below the browser, full width on all screen sizes */}
                <div className='h-40 min-h-0 shrink-0 sm:h-48'>
                  <ActionLog entries={actionLogEntries} taskLabels={taskLabels} dataTour='action-log' showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} reasoningMap={reasoningMap} />
                </div>
              </div>
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
