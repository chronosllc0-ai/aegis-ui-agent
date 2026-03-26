import { useEffect, useMemo, useRef, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { ChangelogModal, useChangelog } from './components/ChangelogModal'
import { NotificationBell } from './components/NotificationBell'
import { PrivacyPage } from './components/PrivacyPage'
import { TermsPage } from './components/TermsPage'
import { useNotifications } from './context/NotificationContext'
import { AuthPage } from './components/AuthPage'
// CostEstimator removed from main UI — credit details live in Settings > Usage
import { InputBar } from './components/InputBar'
import { LandingPage } from './components/LandingPage'
import { OnboardingWizard, isOnboardingComplete } from './components/OnboardingWizard'
import { ProductTour, isTourComplete } from './components/ProductTour'
import { ScreenView } from './components/ScreenView'
import { SpendingAlert } from './components/SpendingAlert'
import { UsageDropdown } from './components/UsageDropdown'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { Icons } from './components/icons'
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
import { apiUrl } from './lib/api'
import { LuShield } from 'react-icons/lu'
import { PROVIDERS, providerById, modelInfo } from './lib/models'
import { docsPath, navigateTo, usePathname, PRIVACY_PATH, TERMS_PATH } from './lib/routes'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
}

// Rough token estimate for context tracking (≈4 chars per token)
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4)
}

function App() {
  const { balance, handleUsageMessage, resetSession: resetUsageSession } = useUsage()
  const { show: showChangelog, dismiss: dismissChangelog, version: appVersion } = useChangelog()
  const toastCtx = useToast()
  const { addNotification } = useNotifications()
  const { connectionStatus, isWorking, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState } = useWebSocket(handleUsageMessage)
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
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const [historySearch, setHistorySearch] = useState('')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authUser, setAuthUser] = useState<{ name: string; email: string; avatar_url?: string | null; role?: string; impersonating?: boolean } | null>(null)
  const [, setPendingPlan] = useState<string | null>(() => {
    return sessionStorage.getItem('aegis.pendingPlan')
  })
  const [authLoading, setAuthLoading] = useState(true)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showTour, setShowTour] = useState(false)
  // draftInput reserved for future InputBar onChange wiring
  void useState

  const docsSlug = slugFromDocsPath(pathname)
  const isDocsRoute = pathname === '/docs' || pathname.startsWith('/docs/')
  const isAuthRoute = pathname === '/auth'
  const isPrivacyRoute = pathname === PRIVACY_PATH
  const isTermsRoute = pathname === TERMS_PATH

  const currentModelMeta = modelInfo(settings.model)
  const currentModelLabel = currentModelMeta?.label ?? settings.model
  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true
  const isAdminPath = isAdmin && pathname.startsWith('/admin')
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

  // Detect credit / quota errors in WebSocket log messages
  useEffect(() => {
    if (!logs.length) return
    const last = logs[logs.length - 1]
    if (last.type !== 'error') return
    const msg = last.message?.toLowerCase() ?? ''
    const isCreditError =
      msg.includes('insufficient') || msg.includes('quota') || msg.includes('credits') ||
      msg.includes('rate limit') || msg.includes('402') || msg.includes('429') ||
      msg.includes('billing') || msg.includes('out of credits') || msg.includes('usage limit')
    if (isCreditError) {
      addNotification({
        type: 'error',
        title: 'API credit / quota error',
        message: last.message,
        source: 'credit',
      })
    }
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

  useEffect(() => {
    document.title = isWorking ? 'Aegis - Working...' : 'Aegis'
  }, [isWorking])

  useEffect(() => {
    document.body.style.overflow = isAuthenticated && !isDocsRoute && !isPrivacyRoute && !isTermsRoute ? 'hidden' : 'auto'
    return () => {
      document.body.style.overflow = 'auto'
    }
  }, [isAuthenticated, isDocsRoute, isPrivacyRoute, isTermsRoute])

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

  useEffect(() => {
    setTaskHistory((prev) => {
      const existingTaskIds = new Set(prev.map((item) => item.id))
      const fromLogs = logs
        .map((entry) => entry.taskId)
        .filter((taskId) => taskId !== 'idle' && !existingTaskIds.has(taskId))
        .map((taskId) => ({
          id: taskId,
          title: logs.find((entry) => entry.taskId === taskId)?.message ?? 'Task',
          dateLabel: 'Today',
          instruction: logs.find((entry) => entry.taskId === taskId)?.message ?? 'Task',
        }))
      if (!fromLogs.length) return prev
      return [...fromLogs, ...prev]
    })
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

  const filteredHistory = useMemo(
    () => taskHistory.filter((item) => item.title.toLowerCase().includes(historySearch.toLowerCase())),
    [historySearch, taskHistory],
  )

  const visibleLogs: LogEntry[] = useMemo(() => {
    if (!selectedTaskId) return logs
    return logs.filter((entry) => entry.taskId === selectedTaskId)
  }, [logs, selectedTaskId])

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
    send({ action: isWorking ? 'steer' : 'navigate', instruction: trimmed })
  }

  const submitUrl = () => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    const normalized = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
    handleSend(normalized, 'steer')
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
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Search task history' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm' />

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
                      <button key={item.id} type='button' onClick={() => { setSelectedTaskId(item.id); setSidebarOpen(false) }} className={`w-full rounded-lg border px-2 py-2 text-left text-xs ${selectedTaskId === item.id ? 'border-blue-500/50 bg-blue-500/10' : 'border-[#2a2a2a] bg-[#111] hover:border-zinc-600'}`}>
                        <p className='truncate text-zinc-200'>{item.title}</p>
                        <p className='truncate text-zinc-500'>{item.instruction}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          {/* ── Bottom section: Usage → Workflows → Settings → User ── */}
          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            {/* Usage dropdown (Botpress-style) — above workflow templates */}
            <UsageDropdown
              balance={balance}
              context={{
                current: contextMeter.current,
                percent: contextMeter.percent,
                isCompacting: contextMeter.isCompacting,
              }}
              modelLabel={currentModelLabel}
            />
            <button type='button' onClick={() => { setShowAutomations(true); setShowSettings(false); setSidebarOpen(false) }} className={`flex w-full items-center gap-2 rounded border px-2 py-2 text-left ${showAutomations ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300' : 'border-[#2a2a2a]'}`}>
              {Icons.clock({ className: 'h-3.5 w-3.5' })}
              <span>Automations</span>
            </button>
            <button type='button' onClick={() => { setSettingsInitialTab('Workflows'); setShowSettings(true); setShowAutomations(false); setSidebarOpen(false) }} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.workflows({ className: 'h-3.5 w-3.5' })}
              <span>Workflow templates ({settings.workflowTemplates.length})</span>
            </button>
            <button type='button' onClick={() => { setSettingsInitialTab(undefined); setShowSettings(true); setShowAutomations(false); setSidebarOpen(false) }} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.settings({ className: 'h-3.5 w-3.5' })}
              <span>Settings</span>
            </button>
            {isAdmin && (
              <button
                type='button'
                onClick={() => { setSettingsInitialTab('Admin'); setShowSettings(true); setShowAutomations(false); setSidebarOpen(false) }}
                className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-800'
              >
                <LuShield className='h-3.5 w-3.5' />
                <span>Admin Panel</span>
              </button>
            )}
            <UserMenu
              name={authUser?.name ?? settings.displayName}
              avatarUrl={authUser?.avatar_url ?? settings.avatarUrl}
              onOpenSettings={() => { setShowSettings(true); setShowAutomations(false); setSidebarOpen(false) }}
              onSignOut={async () => {
                await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
                setAuthUser(null)
                setIsAuthenticated(false)
                navigateTo('/')
              }}
            />
          </div>
        </aside>

        {/* ───────────── Main content ───────────── */}
        <section className='flex min-h-0 flex-1 flex-col gap-1.5 sm:gap-2 lg:gap-3'>
          <header className='space-y-1.5 sm:space-y-2'>
            <div className='flex items-center justify-between gap-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:rounded-2xl sm:px-4 sm:py-2'>
              <div className='flex items-center gap-1.5 sm:gap-2'>
                <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] p-1.5 text-xs lg:hidden' aria-label='Toggle sidebar'>
                  {Icons.menu({ className: 'h-4 w-4' })}
                </button>
                <img src='/shield.svg' alt='Aegis' className='h-4 w-4 sm:h-5 sm:w-5' />
                <h1 className='text-sm font-semibold sm:text-lg'>Aegis</h1>
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

          {!showSettings && !showAutomations && (
            <section className='flex items-center gap-1 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-2 py-1.5 sm:gap-2 sm:rounded-2xl sm:px-3 sm:py-2'>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go back' })} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Back'>
                {Icons.back({ className: 'h-4 w-4' })}
              </button>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go forward' })} className='hidden rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800 sm:block' aria-label='Forward'>
                {Icons.chevronRight({ className: 'h-4 w-4' })}
              </button>
              <span className='text-xs text-zinc-400'>{Icons.globe({ className: 'h-3.5 w-3.5' })}</span>
              <input aria-label='URL address' value={urlInput} onChange={(event) => setUrlInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submitUrl()} className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs outline-none focus:border-blue-500/70 sm:text-sm' />
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
              />
            ) : showAutomations ? (
              <AutomationsPage />
            ) : (
              <div className='grid h-full min-h-0 grid-cols-1 grid-rows-[3fr_1fr] gap-1.5 sm:gap-2 md:grid-cols-[2.2fr_1fr] md:grid-rows-[1fr] lg:gap-3'>
                {showWorkflow ? (
                  <WorkflowView steps={workflowSteps} />
                ) : (
                  <ScreenView frameSrc={latestFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} onExampleClick={(prompt) => setExamplePrompt(prompt)} dataTour='screen-view' />
                )}
                <ActionLog entries={enrichedLogs} dataTour='action-log' showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} />
              </div>
            )}
          </div>

          {!showSettings && !showAutomations && (
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
      {showChangelog && <ChangelogModal onClose={dismissChangelog} />}
      </main>
    </>
  )
}

export default App
