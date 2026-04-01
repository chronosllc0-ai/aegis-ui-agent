import { useEffect, useMemo, useRef, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { ChangelogModal, SubAgentModal, useChangelog } from './components/ChangelogModal'
import { NotificationBell } from './components/NotificationBell'
import { PrivacyPage } from './components/PrivacyPage'
import { TermsPage } from './components/TermsPage'
import { useNotifications } from './context/NotificationContext'
import { AuthPage } from './components/AuthPage'
// CostEstimator removed from main UI - credit details live in Settings > Usage
import { InputBar } from './components/InputBar'
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
import { PROVIDERS, providerById, modelInfo } from './lib/models'
import { docsPath, navigateTo, usePathname, PRIVACY_PATH, TERMS_PATH } from './lib/routes'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

type AppMode = 'browser' | 'chat'

type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
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
  const { connectionStatus, isWorking, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState, activeTaskIdRef, activeConversationId, reasoningMap, subAgents, subAgentSteps, messageSubAgent, cancelSubAgent } = useWebSocket(handleUsageMessage)
  const prevConnectionStatus = useRef(connectionStatus)
  const { settings, patchSettings, wsConfig } = useSettingsContext()
  const pathname = usePathname()

  const contextMeter = useContextMeter(settings.model)

  const [mode, setMode] = useState<SteeringMode>('steer')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [steeringFlashKey, setSteeringFlashKey] = useState(0)
  const [showSettings, setShowSettings] = useState(false)
  const [showAutomations, setShowAutomations] = useState(false)
  const [settingsInitialTab, setSettingsInitialTab] = useState<SettingsTab | undefined>(undefined)
  const [showWorkflow, setShowWorkflow] = useState(false)
  const [urlInput, setUrlInput] = useState('about:blank')
  const [sending, setSending] = useState(false)
  const [examplePrompt, setExamplePrompt] = useState<string | null>(null)
  const [showSubAgentModal, setShowSubAgentModal] = useState(false)
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const [historySearch, setHistorySearch] = useState('')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  // Server-side conversation persistence - replaces localStorage for history + messages
  const [authUser, setAuthUser] = useState<{ uid?: string; name: string; email: string; avatar_url?: string | null; role?: string; impersonating?: boolean } | null>(null)
  const { conversations, fetchMessages, deleteConversation, onNewConversationId } = useConversations(authUser?.uid ?? null)
  // Map from clientTaskId → server conversationId (filled when WS emits conversation_id)
  const taskToConvRef = useRef<Map<string, string>>(new Map())
  // Server messages loaded for the selected conversation
  const [serverMessages, setServerMessages] = useState<ServerMessage[]>([])
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
  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true
  const isAdminPath = isAdmin && pathname.startsWith('/admin')
  const isSettingsPath = pathname.startsWith('/settings')
  const isAutomationsPath = pathname === '/automations'
  const { status: impersonationStatus, checkStatus } = useImpersonation()

  const { isActive: voiceActive, error: voiceError, isSupported: voiceSupported, toggle: toggleVoice, stop: stopVoice } =
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

  // ── Browser tab title: Working… / Steering… / Aegis ──────────────
  const titleTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null)
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
    onNewConversationId(activeConversationId, undefined)
  }, [activeConversationId, activeTaskIdRef, onNewConversationId])

  // When the selected task changes, load messages from server for that conversation
  // ── Seed taskHistory from server conversations so history survives refresh ──
  // When the server returns a conversation list (cross-device / post-refresh),
  // merge any server conversations that aren't already in the local history.
  useEffect(() => {
    if (!conversations.length) return
    setTaskHistory((prev) => {
      const existingIds = new Set(prev.map((t) => t.id))
      const toAdd: TaskHistoryItem[] = []
      for (const conv of conversations) {
        if (!existingIds.has(conv.id)) {
          const createdAt = conv.created_at ? new Date(conv.created_at) : new Date()
          const today = new Date()
          const yesterday = new Date(today)
          yesterday.setDate(today.getDate() - 1)
          let dateLabel = createdAt.toLocaleDateString([], { month: 'short', day: 'numeric' })
          if (createdAt.toDateString() === today.toDateString()) dateLabel = 'Today'
          else if (createdAt.toDateString() === yesterday.toDateString()) dateLabel = 'Yesterday'
          toAdd.push({ id: conv.id, title: conv.title ?? 'Task', dateLabel, instruction: conv.title ?? '' })
        }
      }
      if (!toAdd.length) return prev
      const merged = [...toAdd, ...prev].slice(0, 200) // keep max 200
      try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(merged)) } catch { /* quota */ }
      return merged
    })
  }, [conversations])

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

  const visibleLogs: LogEntry[] = useMemo(() => {
    if (!selectedTaskId) return logs
    const filtered = logs.filter((entry) => entry.taskId === selectedTaskId)
    // If the task was from a previous session, logs are empty (in-memory only).
    // Inject a synthetic entry so the panel isn't blank - shows the original instruction.
    if (filtered.length === 0) {
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
    }
    return filtered
  }, [logs, selectedTaskId, taskHistory])

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

  const handleSend = (instruction: string, selectedMode: SteeringMode) => {
    const trimmed = instruction.trim()
    if (!trimmed) return

    setSending(true)
    window.setTimeout(() => setSending(false), 280)
    send({ action: 'config', settings: wsConfig })

    if (selectedMode === 'queue') {
      setQueuedMessages((prev) => [...prev, trimmed])
      send({ action: 'queue', instruction: trimmed })
      return
    }
    if (selectedMode === 'interrupt') {
      send({ action: 'interrupt', instruction: trimmed })
      return
    }
    setSteeringFlashKey((prev) => prev + 1)

    const isNewTask = !isWorking
    const action = isWorking ? 'steer' : 'navigate'
    send({ action, instruction: trimmed })

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
      const newEntry = { id: taskId, title: trimmed, dateLabel, instruction: trimmed }
      setTaskHistory((prev) => {
        if (prev.some((t) => t.id === taskId)) return prev
        const next = [newEntry, ...prev]
        try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(next)) } catch { /* quota */ }
        return next
      })
      setSelectedTaskId(taskId)
    }
  }

  const submitUrl = () => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    handleSend(normalized, isWorking ? 'steer' : mode)
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

  const onDeleteTask = (id: string) => {
    setTaskHistory((prev) => {
      const next = prev.filter((t) => t.id !== id)
      try { localStorage.setItem(taskHistoryKey(authUser?.uid ?? null), JSON.stringify(next)) } catch { /* ok */ }
      return next
    })
    // Also delete server-side conversation if we have a mapping
    const convId = taskToConvRef.current.get(id)
    if (convId) { void deleteConversation(convId); taskToConvRef.current.delete(id) }
    if (selectedTaskId === id) setSelectedTaskId(null)
  }

  const newSession = () => {
    send({ action: 'stop' })
    setQueuedMessages([])
    setTaskStartedAt(null)
    setDurationSeconds(0)
    resetClientState()
    resetUsageSession()
    contextMeter.reset()
    setSelectedTaskId(null)
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
        <aside data-tour='sidebar' className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] lg:translate-x-0'} fixed inset-y-1.5 left-1.5 z-30 w-[260px] rounded-2xl border border-[#2a2a2a] bg-[#171717] p-3 transition sm:inset-y-2 sm:left-2 sm:w-[280px] lg:static lg:inset-y-3 lg:left-3 lg:translate-x-0 flex min-h-0 flex-col`}>
          <button type='button' onClick={() => { newSession(); setShowAutomations(false); setShowSettings(false) }} className='mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium'>
            New Task
          </button>
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Search task history' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm md:text-xl' />

          {/* ── Task list with independent scroll ── */}
          <div className='min-h-0 flex-1 overflow-y-auto space-y-3 scrollbar-thin'>
            {['Today', 'Yesterday'].map((group) => {
              const items = filteredHistory.filter((item) => item.dateLabel === group)
              if (!items.length) return null
              return (
                <div key={group}>
                  <p className='mb-1 text-[11px] uppercase tracking-wide text-zinc-500'>{group}</p>
                  <div className='space-y-1'>
                    {items.map((item) => (
                      <div key={item.id} className='group relative'>
                        <button type='button' onClick={() => { setSelectedTaskId(item.id); setSidebarOpen(false) }} className={`w-full rounded-lg border px-2 py-2 pr-7 text-left text-xs md:text-lg ${selectedTaskId === item.id ? 'border-blue-500/50 bg-blue-500/10' : 'border-[#2a2a2a] bg-[#111] hover:border-zinc-600'}`}>
                          <p className='truncate text-zinc-200'>{item.title}</p>
                          <p className='truncate text-zinc-500'>{item.instruction}</p>
                        </button>
                        <button
                          type='button'
                          onClick={(e) => { e.stopPropagation(); onDeleteTask(item.id) }}
                          className='absolute right-1.5 top-1/2 -translate-y-1/2 hidden rounded p-0.5 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-200 group-hover:flex'
                          aria-label='Delete task'
                          title='Delete task'
                        >
                          {Icons.trash({ className: 'h-3.5 w-3.5' })}
                        </button>
                      </div>
                    ))}
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
              <div className='flex items-center gap-1.5 sm:gap-2'>
                <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] p-1.5 text-xs lg:hidden' aria-label='Toggle sidebar'>
                  {Icons.menu({ className: 'h-4 w-4' })}
                </button>
                <img src='/aegis-owl-logo.svg' alt='Aegis' className='h-4 w-4 sm:h-5 sm:w-5' />
                <h1 className='text-sm font-semibold sm:text-lg'>Aegis</h1>
                {/* ── Chat ↔ Browser mode switcher ── */}
                {!showSettings && !showAutomations && (
                  <div className='ml-1 flex items-center gap-0.5 rounded-full border border-[#2a2a2a] bg-[#111] p-0.5'>
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
              <div className='flex items-center gap-1.5 text-[10px] text-zinc-300 sm:gap-3 sm:text-xs'>
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
                onSend={handleSend}
                onDecomposePlan={handleDecomposePlan}
                connectionStatus={connectionStatus}
                transcripts={transcripts.map((t) => t.text)}
                onSwitchToBrowser={() => setAppMode('browser')}
                latestFrame={latestFrame}
                voiceActive={voiceActive}
                onToggleVoice={toggleVoice}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                activeTaskId={selectedTaskId}
                serverMessages={serverMessages}
                onStop={() => send({ action: 'stop' })}
                reasoningMap={reasoningMap}
                enableReasoning={settings.enableReasoning}
                onToggleReasoning={(enabled) => patchSettings({ enableReasoning: enabled })}
                reasoningEffort={settings.reasoningEffort}
                onChangeReasoningEffort={(effort) => patchSettings({ reasoningEffort: effort })}
                currentModelSupportsReasoning={currentModelMeta?.reasoning ?? false}
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
                    <ScreenView frameSrc={latestFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} onExampleClick={(prompt) => setExamplePrompt(prompt)} dataTour='screen-view' lastClickCoords={lastClickCoords} />
                  )}
                </div>

                {/* Action log - stacked below the browser, full width on all screen sizes */}
                <div className='h-40 min-h-0 shrink-0 sm:h-48'>
                  <ActionLog entries={enrichedLogs} dataTour='action-log' showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} reasoningMap={reasoningMap} />
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

          {!showSettings && !showAutomations && subAgents.length > 0 && (
            <div className='flex justify-center px-4 pb-2'>
              <SubAgentPanel
                agents={subAgents}
                steps={subAgentSteps}
                onCancel={cancelSubAgent}
                onMessage={messageSubAgent}
              />
            </div>
          )}

          {!showSettings && !showAutomations && appMode === 'browser' && (
            <div data-tour='input-bar'>
              <InputBar
                mode={mode}
                voiceActive={voiceActive}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                voiceError={voiceError}
                isConnected={connectionStatus === 'connected'}
                isWorking={isWorking}
                onToggleVoice={toggleVoice}
                sending={sending}
                onModeChange={setMode}
                onSend={handleSend}
                onDecomposePlan={handleDecomposePlan}
                provider={settings.provider}
                model={settings.model}
                onProviderChange={(nextProvider) => {
                  const p = providerById(nextProvider) ?? PROVIDERS[0]
                  patchSettings({ provider: nextProvider, model: p.models[0].id })
                }}
                onModelChange={(nextModel) => patchSettings({ model: nextModel })}
                queuedMessages={queuedMessages}
                onDeleteQueueItem={(index) => {
                  setQueuedMessages((prev) => prev.filter((_, i) => i !== index))
                  send({ action: 'dequeue', index })
                }}
                examplePrompt={examplePrompt}
                onExampleHandled={() => setExamplePrompt(null)}
                transcripts={transcripts}
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
            setExamplePrompt('spawn sub-agents: ')
          }}
        />
      )}
      </main>
    </>
  )
}

export default App
