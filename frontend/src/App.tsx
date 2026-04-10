import { useEffect, useMemo, useRef, useState } from 'react'
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
import { useConversations, type ServerMessage } from './hooks/useConversations'
import { apiUrl } from './lib/api'
import { LuShield } from 'react-icons/lu'
import { modelInfo, PROVIDERS } from './lib/models'
import { modeLabel, normalizeAgentMode } from './lib/agentModes'
import { docsPath, navigateTo, usePathname, PRIVACY_PATH, TERMS_PATH } from './lib/routes'
import { deriveTitleFromInstruction, isPlaceholderTitle, mergeTitlePreferMeaningful } from './lib/title'
import { isBrowserPrimitiveActionLogEntry } from './lib/actionLogFilter'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

type AppMode = 'browser' | 'chat'

type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
  labelSource?: 'browser' | 'chat' | 'system'
}
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
const taskHistoryKey = (uid: string | null) => `aegis.taskHistory.${uid || 'anon'}`
const SETTINGS_ROUTE_MAP: Record<string, SettingsTab> = {
  profile: 'Profile',
  'agent-configuration': 'Agent Configuration',
  'api-keys': 'API Keys',
  usage: 'Usage',
  credits: 'Credits',
  invoices: 'Invoices',
  connections: 'Connections',
  workflows: 'Workflows',
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
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  // Server-side conversation persistence - replaces localStorage for history + messages
  const [authUser, setAuthUser] = useState<{ uid?: string; name: string; email: string; avatar_url?: string | null; role?: string; impersonating?: boolean } | null>(null)
  const { connectionStatus, isWorking, activityStatusLabel, activityDetail, isActivityVisible, activeExecutionMode, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, clearFrameCache, removeFrameForThread, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, messageSubAgent, cancelSubAgent } = useWebSocket({
    onUsageMessage: handleUsageMessage,
    userId: authUser?.uid ?? null,
    activeThreadId: selectedTaskId,
  })
  const prevConnectionStatus = useRef(connectionStatus)
  const { settings, patchSettings, wsConfig } = useSettingsContext()
  const pathname = usePathname()

  const contextMeter = useContextMeter(settings.model)

  const [mode, setMode] = useState<SteeringMode>('auto')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [steeringFlashKey, setSteeringFlashKey] = useState(0)
  const [showSettings, setShowSettings] = useState(false)
  const [showAutomations, setShowAutomations] = useState(false)
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab | undefined>(undefined)
  const [showWorkflow, setShowWorkflow] = useState(false)
  const [urlInput, setUrlInput] = useState('about:blank')
  const [showSubAgentModal, setShowSubAgentModal] = useState(false)
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const [historySearch, setHistorySearch] = useState('')
  const { conversations, fetchMessages, deleteConversation, onNewConversationId } = useConversations(authUser?.uid ?? null)
  // Map from clientTaskId → server conversationId (filled when WS emits conversation_id)
  const taskToConvRef = useRef<Map<string, string>>(new Map())
  // Server messages loaded for the selected conversation
  const [serverMessages, setServerMessages] = useState<ServerMessage[]>([])
  const [optimisticMessagesByTask, setOptimisticMessagesByTask] = useState<Record<string, ServerMessage[]>>({})
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([])
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
  const [appMode, setAppMode] = useState<AppMode>('browser')
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null)
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

  const { isActive: voiceActive, isSupported: voiceSupported, toggle: toggleVoice, stop: stopVoice } =
    useMicrophone({ onChunk: (payload) => sendAudioChunk(payload) })

  useEffect(() => {
    if (connectionStatus !== 'connected' && voiceActive) {
      void stopVoice()
    }
  }, [connectionStatus, voiceActive, stopVoice])

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

    if (startedWorking && appMode === 'chat' && settings.promptToSwitchOnBrowse) {
      const activeTaskId = activeTaskIdRef.current
      if (activeTaskId && !promptShownTaskIdsRef.current.has(activeTaskId)) {
        promptShownTaskIdsRef.current.add(activeTaskId)
        setShowBrowseHandoffPrompt(true)
      }
    }

    if (finishedWorking) {
      setShowBrowseHandoffPrompt(false)
      if (appMode === 'browser' && settings.autoReturnToChat) {
        setAppMode('chat')
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
    appMode,
    settings.separateExecutionSurfaces,
    settings.promptToSwitchOnBrowse,
    settings.autoReturnToChat,
    activeTaskIdRef,
    addNotification,
  ])

  // ── Browser tab title: Working… / Steering… / Aegis ──────────────
  const titleTimeoutRef = useRef<number | null>(null)
  const [titleMode, setTitleMode] = useState<'idle' | 'working' | 'steering'>('idle')
  useEffect(() => {
    if (!isWorking) { setTitleMode('idle'); return }
    setTitleMode((prev) => prev === 'steering' ? 'steering' : 'working')
  }, [isWorking])
  useEffect(() => {
    if (titleMode === 'working') document.title = '⚙ Aegis - Working…'
    else if (titleMode === 'steering') document.title = '↩ Aegis - Steering…'
    else document.title = 'Aegis'
  }, [titleMode])

  useEffect(() => {
    document.body.style.overflow = isAuthenticated && !isDocsRoute && !isPrivacyRoute && !isTermsRoute ? 'hidden' : 'auto'
    return () => {
      document.body.style.overflow = 'auto'
    }
  }, [isAuthenticated, isDocsRoute, isPrivacyRoute, isTermsRoute])

  useEffect(() => {
    try {
      const saved = localStorage.getItem(taskHistoryKey(authUser?.uid ?? null))
      setTaskHistory(saved ? (JSON.parse(saved) as TaskHistoryItem[]) : [])
    } catch {
      setTaskHistory([])
    }
  }, [authUser?.uid])

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
          if (settingsTab && ['Profile', 'Agent Configuration', 'API Keys', 'Usage', 'Credits', 'Invoices', 'Connections', 'Workflows', 'Memory', 'Observability', 'Support'].includes(settingsTab)) {
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

  // When the server assigns a conversationId for the current navigate action,
  // map the client-side taskId to it and update the conversation list.
  useEffect(() => {
    if (!activeConversationId) return
    const taskId = activeTaskIdRef.current
    taskToConvRef.current.set(taskId, activeConversationId)
    const localTask = taskHistory.find((item) => item.id === taskId)
    onNewConversationId(activeConversationId, localTask?.title)
  }, [activeConversationId, activeTaskIdRef, onNewConversationId, taskHistory])

  // When the selected task changes, load messages from server for that conversation
  // ── Seed taskHistory from server conversations so history survives refresh ──
  // When the server returns a conversation list (cross-device / post-refresh),
  // merge any server conversations that aren't already in the local history.
  useEffect(() => {
    if (!conversations.length) return
    setTaskHistory((prev) => {
      const byId = new Map(prev.map((item) => [item.id, item]))
      const next = [...prev]

      for (const conv of conversations) {
        const existing = byId.get(conv.id)
        if (existing) {
          const mergedTitle = mergeTitlePreferMeaningful(
            existing.title,
            conv.title,
            existing.instruction || existing.title,
          )
          if (mergedTitle !== existing.title) {
            const idx = next.findIndex((item) => item.id === conv.id)
            if (idx >= 0) next[idx] = { ...next[idx], title: mergedTitle }
          }
          continue
        }

        const createdAt = conv.created_at ? new Date(conv.created_at) : new Date()
        const today = new Date()
        const yesterday = new Date(today)
        yesterday.setDate(today.getDate() - 1)
        let dateLabel = createdAt.toLocaleDateString([], { month: 'short', day: 'numeric' })
        if (createdAt.toDateString() === today.toDateString()) dateLabel = 'Today'
        else if (createdAt.toDateString() === yesterday.toDateString()) dateLabel = 'Yesterday'

        const fallbackInstruction = deriveTitleFromInstruction(conv.title)
        next.unshift({
          id: conv.id,
          title: mergeTitlePreferMeaningful(undefined, conv.title, fallbackInstruction),
          dateLabel,
          instruction: isPlaceholderTitle(conv.title) ? fallbackInstruction : (conv.title ?? ''),
          labelSource: 'system',
        })
      }

      const merged = next.slice(0, 200)
      try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(merged)) } catch { /* quota */ }
      return merged
    })
  }, [authUser?.uid, conversations])

  useEffect(() => {
    if (!selectedTaskId) { setServerMessages([]); return }
    const convId = taskToConvRef.current.get(selectedTaskId)
    if (convId) {
      void fetchMessages(convId).then(setServerMessages)
    } else {
      // Try matching by conversation list (for tasks loaded from history on another device)
      const matchedConv = conversations.find(c => c.id === selectedTaskId)
      if (matchedConv) {
        void fetchMessages(matchedConv.id).then(setServerMessages)
      } else {
        setServerMessages([])
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTaskId])

  const filteredHistory = useMemo(
    () => taskHistory.filter((item) => item.title.toLowerCase().includes(historySearch.toLowerCase())),
    [historySearch, taskHistory],
  )

  const taskLabels = useMemo(
    () => Object.fromEntries(taskHistory.map((item) => [item.id, item.title])),
    [taskHistory],
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
    return [...dedupedOptimistic, ...serverMessages]
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

    const saved = taskHistory.find((t) => t.id === selectedTaskId)
    if (saved) {
      return [{
        id: `restored-${selectedTaskId}`,
        taskId: selectedTaskId,
        message: saved.instruction,
        timestamp: saved.dateLabel,
        type: 'step' as const,
        status: 'completed' as const,
        stepKind: 'navigate' as const,
        elapsedSeconds: 0,
      }]
    }

    return filtered
  }, [logs, selectedTaskId, taskHistory, serverMessages])

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
      setMode('auto')
      if (hadBrowserActivityThisRun && appMode === 'browser') {
        setAppMode('chat')
      }
    }

    prevBrowsingWorkingRef.current = isWorking
  }, [isWorking, hasBrowserActivityForActiveTask, appMode])

  // ── Auto-switch to chat on ask_user_input while in browser mode ─────────
  // If the agent needs user input mid-task and the user is watching the
  // browser, jump them to chat so they see (and can answer) the question.
  useEffect(() => {
    if (!enrichedLogs.length || appMode !== 'browser') return
    const last = enrichedLogs[enrichedLogs.length - 1]
    if (last?.message?.includes('[ask_user_input]') ||
        last?.message?.includes('[confirm_plan]') ||
        last?.message?.includes('[plan_steps]')) {
      setAppMode('chat')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enrichedLogs.length, appMode])

  const handleSend = (instruction: string, selectedMode: SteeringMode, metadata?: Record<string, unknown>) => {
    const trimmed = instruction.trim()
    if (!trimmed) return
    const mentionMatches = [...trimmed.matchAll(/@([a-zA-Z0-9._-]+)/g)].map((m) => m[1].toLowerCase())
    const mentionedAgents = subAgents.filter((agent) => mentionMatches.includes(subAgentDisplayName(agent).toLowerCase()))
    const cleanedInstruction = trimmed.replace(/@[a-zA-Z0-9._-]+/g, '').replace(/\s{2,}/g, ' ').trim()
    const finalInstruction = cleanedInstruction || trimmed

    const selectedAgentMode = normalizeAgentMode(settings.agentMode)
    send({ action: 'config', settings: wsConfig })

    if (selectedMode === 'queue') {
      setQueuedMessages((prev) => [...prev, trimmed])
      const queued = send({ action: 'queue', instruction: finalInstruction, metadata: { ...(metadata ?? {}), agent_mode: selectedAgentMode, target_subagents: mentionedAgents.map((a) => a.sub_id) } })
      if (!queued) {
        toastCtx.error('Connection issue', 'Could not queue task because WebSocket is not connected.')
      }
      return
    }
    if (selectedMode === 'interrupt') {
      const interrupted = send({ action: 'interrupt', instruction: finalInstruction, metadata: { ...(metadata ?? {}), agent_mode: selectedAgentMode, target_subagents: mentionedAgents.map((a) => a.sub_id) } })
      if (!interrupted) {
        toastCtx.error('Connection issue', 'Could not send interrupt because WebSocket is not connected.')
      }
      return
    }
    setSteeringFlashKey((prev) => prev + 1)

    const isNewTask = !isWorking
    const action = isWorking ? 'steer' : 'navigate'
    console.info('[AegisUI] selected_mode=%s action=%s', selectedMode, action)
    // Only route to a sub-agent when actively steering an in-progress task.
    // When starting a new task (isWorking=false) there is no active parent task,
    // so sub-agent routing makes no sense and would silently swallow the send.
    const activeSubAgent = isWorking ? subAgents.find((a) => a.sub_id === selectedTaskId) : null
    if (activeSubAgent) {
      void messageSubAgent(activeSubAgent.sub_id, finalInstruction)
      return
    }

    const sent = send({ action, instruction: finalInstruction, metadata: { ...(metadata ?? {}), agent_mode: selectedAgentMode, target_subagents: mentionedAgents.map((a) => a.sub_id) } })
    if (!sent) {
      toastCtx.error('Connection issue', 'Task was not sent. Please wait for reconnect and retry.')
      return
    }
    mentionedAgents.forEach((agent) => { void messageSubAgent(agent.sub_id, finalInstruction) })

    // ── Update browser tab title for steering state ────────────────
    if (action === 'steer') {
      // Clear any pending timer to avoid stacked timeouts from rapid steers
      if (titleTimeoutRef.current !== null) window.clearTimeout(titleTimeoutRef.current)
      setTitleMode('steering')
      // Flash "Steering…" for 3 s then revert to "Working…"
      titleTimeoutRef.current = window.setTimeout(() => {
        setTitleMode('working')
        titleTimeoutRef.current = null
      }, 3000)
    }

    // Save to task history optimistically at send-time so the title always reflects
    // the real user instruction. We generate a stable taskId from a UUID that the
    // WebSocket hook will also assign synchronously for 'navigate' (it calls
    // crypto.randomUUID() internally). We capture it immediately after send().
    // We save regardless of WS state so the history entry is never lost - if the
    // WS was closed the agent won't respond but the user still sees their input.
    if (isNewTask) {
      const taskId = activeTaskIdRef.current !== 'idle'
        ? activeTaskIdRef.current
        : `pending-${crypto.randomUUID()}`
      const now = new Date()
      const dateLabel = now.toLocaleDateString([], { month: 'short', day: 'numeric' })
      const labelSource = metadata?.task_label_source === 'browser' ? 'browser' : 'chat'
      const lockedTitle = typeof metadata?.task_label === 'string' && metadata.task_label.trim()
        ? metadata.task_label.trim()
        : finalInstruction
      const newEntry: TaskHistoryItem = { id: taskId, title: lockedTitle, dateLabel, instruction: finalInstruction, labelSource }
      setOptimisticMessagesByTask((prev) => {
        const existing = prev[taskId] ?? []
        if (existing.some((msg) => msg.role === 'user' && msg.content.trim() === finalInstruction.trim())) {
          return prev
        }
        const optimisticMessage: ServerMessage = {
          id: `optimistic-${taskId}-${existing.length + 1}`,
          role: 'user',
          content: finalInstruction,
          metadata: null,
          created_at: new Date().toISOString(),
        }
        return {
          ...prev,
          [taskId]: [...existing, optimisticMessage],
        }
      })
      setTaskHistory((prev) => {
        if (prev.some((t) => t.id === taskId)) return prev
        const next = [newEntry, ...prev]
        try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(next)) } catch { /* quota */ }
        return next
      })
      setSelectedTaskId(taskId)
    }
  }

  const dispatchPromptFromUI = (instruction: string, metadata?: Record<string, unknown>) => {
    const selectedMode = isWorking ? mode : 'auto'
    const websocketAction = isWorking
      ? selectedMode === 'interrupt'
        ? 'interrupt'
        : selectedMode === 'queue'
          ? 'queue'
          : 'steer'
      : 'navigate'
    console.info('[AegisUI] dispatch_source=chat_input selected_mode=%s websocket_action=%s', selectedMode, websocketAction)
    handleSend(instruction, selectedMode, metadata)
  }

  const submitUrl = () => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    handleSend(normalized, isWorking ? mode : 'auto', { task_label_source: 'browser', task_label: normalized })
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

  const onDeleteTask = (id: string) => {
    removeFrameForThread(id)
    setTaskHistory((prev) => {
      const next = prev.filter((t) => t.id !== id)
      try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(next)) } catch { /* ok */ }
      return next
    })
    // Also delete server-side conversation if we have a mapping
    const convId = taskToConvRef.current.get(id)
    if (convId) { void deleteConversation(convId); taskToConvRef.current.delete(id) }
    if (selectedTaskId === id) setSelectedTaskId(null)
    setOptimisticMessagesByTask((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const newSession = () => {
    send({ action: 'stop' })
    setTaskStartedAt(null)
    setDurationSeconds(0)
    resetClientState()
    resetUsageSession()
    contextMeter.reset()
    setSelectedTaskId(null)
    setOptimisticMessagesByTask({})
    setShowWorkflow(false)
    void stopVoice()
  }

  const saveWorkflow = () => {
    if (!visibleLogs.length) return

    const selectedTaskInstruction = selectedTaskId
      ? taskHistory.find((item) => item.id === selectedTaskId)?.instruction
      : null

    const fallbackInstruction = visibleLogs.find(
      (entry) =>
        entry.type === 'step' &&
        entry.stepKind === 'navigate' &&
        !entry.message.toLowerCase().includes('session settings updated') &&
        !entry.message.toLowerCase().includes('queued instruction'),
    )?.message

    const instruction = selectedTaskInstruction ?? fallbackInstruction ?? 'Saved workflow instruction'

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
          <button type='button' onClick={() => { newSession(); setShowAutomations(false); setShowSettings(false) }} className='mb-2 w-full rounded-lg border border-[#2a2a2a] bg-[#111]/60 px-3 py-2 text-left text-sm text-zinc-200'>
            ⌁ New thread
          </button>
          <button type='button' onClick={() => setShowAutomations(true)} className='mb-2 w-full rounded-lg border border-[#2a2a2a] bg-[#111]/30 px-3 py-2 text-left text-sm text-zinc-400'>◷ Automations</button>
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Threads' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm md:text-xl' />

          {/* ── Task list — Codex-style text-only threads ── */}
          <div className='min-h-0 flex-1 overflow-y-auto scrollbar-thin'>
            {['Today', 'Yesterday'].map((group) => {
              const items = filteredHistory.filter((item) => item.dateLabel === group)
              if (!items.length) return null
              return (
                <div key={group} className='mb-4'>
                  <p className='mb-1 px-1 text-[11px] uppercase tracking-wide text-zinc-500'>{group}</p>
                  <div className='space-y-0'>
                    {items.map((item) => {
                      const agentsForTask = subAgents.filter((agent) => agent.parent_task_id === item.id)
                      const isActive = selectedTaskId === item.id
                      return (
                        <div key={item.id}>
                          {/* Parent thread row */}
                          <div className='group relative flex items-center'>
                            <button
                              type='button'
                              onClick={() => { setSelectedTaskId(item.id); setSidebarOpen(false) }}
                              className={`flex-1 min-w-0 px-2 py-1 text-left transition-colors ${isActive ? 'text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
                            >
                              <p className={`truncate text-sm font-normal ${isActive ? 'text-zinc-100' : ''}`}>
                                {item.title || item.instruction.slice(0, 40) || 'Untitled'}
                              </p>
                            </button>
                            <button
                              type='button'
                              onClick={(e) => { e.stopPropagation(); onDeleteTask(item.id) }}
                              className='mr-1 hidden rounded p-0.5 text-zinc-600 hover:bg-zinc-700 hover:text-zinc-300 group-hover:flex flex-shrink-0'
                              aria-label='Delete task'
                              title='Delete task'
                            >
                              {Icons.trash({ className: 'h-3 w-3' })}
                            </button>
                          </div>

                          {/* Sub-agent child threads — nested under parent */}
                          {agentsForTask.length > 0 && (
                            <div className='ml-3 border-l border-[#252525] pl-2'>
                              {agentsForTask.map((agent, aIdx) => {
                                const nameColors = ['text-orange-400','text-green-400','text-sky-400','text-violet-400','text-rose-400']
                                const nc = nameColors[aIdx % nameColors.length]
                                const taskTitle = agent.instruction.split(' ').slice(0, 6).join(' ').slice(0, 36) || 'Sub-task'
                                const isLive = agent.status === 'spawning' || agent.status === 'running'
                                const shortName = subAgentDisplayName(agent).slice(0, 12) || `Agent ${aIdx + 1}`
                                return (
                                  <button
                                    key={agent.sub_id}
                                    type='button'
                                    onClick={() => { setSelectedTaskId(agent.sub_id); setSidebarOpen(false) }}
                                    className={`flex w-full items-baseline gap-1.5 px-2 py-1 text-left transition-colors ${selectedTaskId === agent.sub_id ? 'text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
                                  >
                                    <span className={`text-[11px] font-semibold flex-shrink-0 ${nc} ${isLive ? 'agent-name-shimmer' : ''}`}>
                                      {shortName}
                                    </span>
                                    <span className='truncate text-[11px] flex-1'>
                                      — {taskTitle}{taskTitle.length < agent.instruction.length ? '…' : ''}
                                    </span>
                                  </button>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          {/* ── Bottom section: Usage → Workflows → Settings → User ── */}
          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            {/* Usage dropdown (Botpress-style) - above workflow templates */}
            <UsageDropdown
              balance={balance}
              context={{
                current: contextMeter.current,
                percent: contextMeter.percent,
                isCompacting: contextMeter.isCompacting,
              }}
              modelLabel={currentModelLabel}
            />
            <button type='button' onClick={() => { navigateTo('/automations'); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left ${showAutomations ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a]'}`}>
              {Icons.clock({ className: 'h-3.5 w-3.5' })}
              <span>Automations</span>
            </button>
            <button type='button' onClick={() => { navigateTo('/settings/workflows'); setSidebarOpen(false) }} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.workflows({ className: 'h-3.5 w-3.5' })}
              <span>Workflow templates ({settings.workflowTemplates.length})</span>
            </button>
            <button type='button' onClick={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.settings({ className: 'h-3.5 w-3.5' })}
              <span>Settings</span>
            </button>
            {isAdmin && (
              <button
                type='button'
                onClick={() => { navigateTo('/admin'); setSidebarOpen(false) }}
                className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800'
              >
                <LuShield className='h-3.5 w-3.5' />
                <span>Admin Panel</span>
              </button>
            )}
            <UserMenu
              name={authUser?.name ?? settings.displayName}
              avatarUrl={authUser?.avatar_url ?? settings.avatarUrl}
              onOpenSettings={() => { navigateTo('/settings/profile'); setSidebarOpen(false) }}
              onSignOut={async () => {
                await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
                clearFrameCache()
                setAuthUser(null)
                setIsAuthenticated(false)
                setTaskHistory([])
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
                      onClick={() => setAppMode('browser')}
                      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${appMode === 'browser' ? 'bg-[#2a2a2a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
                    >
                      {Icons.globe({ className: 'h-3 w-3' })}
                      <span className='hidden xs:inline'>Browser</span>
                    </button>
                    <button
                      type='button'
                      onClick={() => setAppMode('chat')}
                      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${appMode === 'chat' ? 'bg-[#2a2a2a] text-white' : 'text-zinc-500 hover:text-zinc-300'}`}
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

          {!showSettings && !showAutomations && appMode === 'browser' && (
            <section className='flex items-center gap-1 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:gap-2 sm:rounded-2xl sm:px-3 sm:py-2'>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go back' })} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Back'>
                {Icons.back({ className: 'h-4 w-4' })}
              </button>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go forward' })} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Forward'>
                {Icons.chevronRight({ className: 'h-4 w-4' })}
              </button>
              <span className='text-xs text-zinc-400'>{Icons.globe({ className: 'h-3.5 w-3.5' })}</span>
              <input aria-label='URL address' value={urlInput} onChange={(event) => setUrlInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submitUrl()} className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs outline-none focus:border-blue-500/70 sm:text-sm md:text-xl' />
              <button type='button' onClick={submitUrl} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800 sm:px-3'>Go</button>
            </section>
          )}

          <div className='min-h-0 flex-1'>
            {showSettings || isAdminPath ? (
              <SettingsPage
                onBack={() => { setShowSettings(false); setSettingsInitialTab(undefined); navigateTo('/') }}
                onRunWorkflow={(instruction) => handleSend(instruction, 'steer')}
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
            ) : appMode === 'chat' ? (
              <ChatPanel
                logs={enrichedLogs}
                isWorking={isWorking}
                mode={mode}
                queuedMessages={queuedMessages}
                onModeChange={setMode}
                onPrimarySend={dispatchPromptFromUI}
                onSend={handleSend}
                onDecomposePlan={handleDecomposePlan}
                connectionStatus={connectionStatus}
                transcripts={transcripts.map((t) => t.text)}
                onSwitchToBrowser={() => { setShowBrowseHandoffPrompt(false); setAppMode('browser') }}
                latestFrame={latestFrame}
                voiceActive={voiceActive}
                onToggleVoice={toggleVoice}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                activeTaskId={selectedTaskId}
                serverMessages={mergedChatMessages}
                onStop={() => send({ action: 'stop' })}
                onUserInputResponse={handleUserInputResponse}
                onPlanConfirm={handlePlanConfirm}
                onPlanReject={handlePlanReject}
                activityStatusLabel={activityStatusLabel}
                activityDetail={activityDetailWithMode}
                isActivityVisible={isActivityVisible}
                provider={settings.provider}
                model={settings.model}
                agentMode={settings.agentMode}
                onProviderChange={(nextProvider) => {
                  const providerMeta = PROVIDERS.find((item) => item.id === nextProvider) ?? PROVIDERS[0]
                  patchSettings({ provider: nextProvider, model: providerMeta.models[0].id })
                }}
                onModelChange={(nextModel) => patchSettings({ model: nextModel })}
                onAgentModeChange={(nextMode) => patchSettings({ agentMode: nextMode })}
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
                      steeringFlashKey={steeringFlashKey}
                      onExampleClick={(prompt) => {
                        console.info('[AegisUI] example_click -> pre-fill composer')
                        setAppMode('chat')
                        setPendingPrompt(prompt)
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
          {!showSettings && !showAutomations && appMode === 'browser' && isWorking && (
            <div className='flex justify-end pb-1 pr-1'>
              <button
                type='button'
                onClick={() => { send({ action: 'stop' }) }}
                className='flex items-center gap-1.5 rounded-full border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/20 hover:border-red-400/60'
                title='Stop current task'
              >
                <span className='inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-red-300 border-t-transparent' />
                Stop
              </button>
            </div>
          )}

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
            handleSend('spawn sub-agents: ', 'steer', { task_label_source: 'chat', task_label: 'spawn sub-agents' })
          }}
        />
      )}
      </main>
    </>
  )
}

export default App
