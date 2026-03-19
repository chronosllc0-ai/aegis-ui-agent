import { useEffect, useMemo, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { AuthPage } from './components/AuthPage'
import { CostEstimator } from './components/CostEstimator'
import { InputBar } from './components/InputBar'
import { LandingPage } from './components/LandingPage'
import { ScreenView } from './components/ScreenView'
import { SpendingAlert } from './components/SpendingAlert'
import { UsageMeterBar } from './components/UsageMeterBar'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { Icons } from './components/icons'
import { SettingsPage } from './components/settings/SettingsPage'
import { useSettingsContext } from './context/useSettingsContext'
import { useMicrophone } from './hooks/useMicrophone'
import { useUsage } from './hooks/useUsage'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { apiUrl } from './lib/api'
import { PROVIDERS, providerById } from './lib/models'
import { docsPath, navigateTo, usePathname } from './lib/routes'
import { getStandaloneDocUrl } from './lib/site'
import { EmbeddedDocsPage, slugFromDocsPath } from './public/EmbeddedDocsPage'

type TaskHistoryItem = {
  id: string
  title: string
  dateLabel: string
  instruction: string
}

function App() {
  const { balance, sessionCredits, sessionMessages, streaming, rates, handleUsageMessage, resetSession: resetUsageSession } = useUsage()
  const { connectionStatus, isWorking, latestFrame, logs, workflowSteps, currentUrl, transcripts, send, sendAudioChunk, resetClientState } = useWebSocket(handleUsageMessage)
  const { settings, patchSettings, wsConfig } = useSettingsContext()
  const pathname = usePathname()

  const [mode, setMode] = useState<SteeringMode>('steer')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [steeringFlashKey, setSteeringFlashKey] = useState(0)
  const [showSettings, setShowSettings] = useState(false)
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
  const [authUser, setAuthUser] = useState<{ name: string; email: string; avatar_url?: string | null } | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [draftInput, setDraftInput] = useState('')
  // draftInput is wired from InputBar's onChange → CostEstimator for pre-send cost preview
  void setDraftInput // suppress unused warning — InputBar doesn't expose onChange yet

  const docsSlug = slugFromDocsPath(pathname)
  const isDocsRoute = pathname === '/docs' || pathname.startsWith('/docs/')
  const isAuthRoute = pathname === '/auth'

  const { isActive: voiceActive, error: voiceError, isSupported: voiceSupported, toggle: toggleVoice, stop: stopVoice } =
    useMicrophone({ onChunk: (payload) => sendAudioChunk(payload) })

  useEffect(() => {
    if (connectionStatus !== 'connected' && voiceActive) {
      void stopVoice()
    }
  }, [connectionStatus, voiceActive, stopVoice])

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
    document.body.style.overflow = isAuthenticated && !isDocsRoute ? 'hidden' : 'auto'
    return () => {
      document.body.style.overflow = 'auto'
    }
  }, [isAuthenticated, isDocsRoute])

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
          setAuthUser(data.user)
          setIsAuthenticated(true)
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

  const filteredHistory = useMemo(
    () => taskHistory.filter((item) => item.title.toLowerCase().includes(historySearch.toLowerCase())),
    [historySearch, taskHistory],
  )

  const visibleLogs: LogEntry[] = useMemo(() => {
    if (!selectedTaskId) return logs
    return logs.filter((entry) => entry.taskId === selectedTaskId)
  }, [logs, selectedTaskId])

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
    if (!isAuthRoute) {
      return (
        <LandingPage
          onGetStarted={openAuth}
          onOpenDocsHome={openDocsHome}
          onOpenDoc={openDoc}
          docsPortalHref={getStandaloneDocUrl()}
        />
      )
    }
    return (
      <AuthPage
        onAuthenticated={(user) => {
          setAuthUser(user)
          setIsAuthenticated(true)
          navigateTo('/')
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

  return (
    <main className='h-screen bg-[#111] p-3 text-zinc-100'>
      <div className='mx-auto flex h-full max-w-[1750px] gap-3'>
        <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] md:translate-x-0'} fixed inset-y-3 left-3 z-30 w-[280px] rounded-2xl border border-[#2a2a2a] bg-[#171717] p-3 transition md:static md:translate-x-0 flex min-h-0 flex-col`}>
          <button type='button' onClick={newSession} className='mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium'>
            New Task
          </button>
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Search task history' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm' />
          <div className='min-h-0 flex-1 overflow-y-auto space-y-3'>
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
          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            <button type='button' onClick={() => setShowSettings(true)} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.workflows({ className: 'h-3.5 w-3.5' })}
              <span>Workflow templates ({settings.workflowTemplates.length})</span>
            </button>
            <button type='button' onClick={() => setShowSettings(true)} className='flex w-full items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-left'>
              {Icons.settings({ className: 'h-3.5 w-3.5' })}
              <span>Settings</span>
            </button>
            <UserMenu
              name={authUser?.name ?? settings.displayName}
              avatarUrl={authUser?.avatar_url ?? settings.avatarUrl}
              onOpenSettings={() => setShowSettings(true)}
              onSignOut={async () => {
                await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
                setAuthUser(null)
                setIsAuthenticated(false)
                navigateTo('/')
              }}
            />
          </div>
        </aside>

        <section className='flex min-h-0 flex-1 flex-col gap-3 md:ml-0'>
          <header className='space-y-2'>
            <div className='flex items-center justify-between rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2'>
              <div className='flex items-center gap-2'>
                <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs md:hidden' aria-label='Toggle sidebar'>
                  {Icons.menu({ className: 'h-4 w-4' })}
                </button>
                <img src='/shield.svg' alt='Aegis' className='h-5 w-5' />
                <h1 className='text-lg font-semibold'>Aegis</h1>
              </div>
              <div className='flex items-center gap-3 text-xs text-zinc-300'>
                <span className='inline-flex items-center gap-1 rounded-full border border-[#2a2a2a] px-2 py-1'>
                  <span className={`h-2.5 w-2.5 rounded-full ${connectionLabel.cls}`} /> {connectionLabel.label}
                </span>
                <span>Session {Math.floor(durationSeconds / 60)}:{String(durationSeconds % 60).padStart(2, '0')}</span>
                <button type='button' onClick={newSession} className='rounded-md border border-[#2a2a2a] px-3 py-1.5 hover:border-blue-500/60 hover:bg-zinc-900'>New Session</button>
              </div>
            </div>
            {isAuthenticated && (
              <UsageMeterBar balance={balance} sessionCredits={sessionCredits} sessionMessages={sessionMessages} streaming={streaming} />
            )}
          </header>

          {!showSettings && (
            <section className='flex items-center gap-2 rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2'>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go back' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800' aria-label='Back'>
                {Icons.back({ className: 'h-4 w-4' })}
              </button>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go forward' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800' aria-label='Forward'>
                {Icons.chevronRight({ className: 'h-4 w-4' })}
              </button>
              <span className='text-xs text-zinc-400'>{Icons.globe({ className: 'h-3.5 w-3.5' })}</span>
              <input aria-label='URL address' value={urlInput} onChange={(event) => setUrlInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submitUrl()} className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-sm outline-none focus:border-blue-500/70' />
              <button type='button' onClick={submitUrl} className='rounded border border-[#2a2a2a] px-3 py-1 text-xs hover:bg-zinc-800'>Go</button>
            </section>
          )}

          <div className='min-h-0 flex-1'>
            {showSettings ? (
              <SettingsPage onBack={() => setShowSettings(false)} onRunWorkflow={(instruction) => handleSend(instruction, 'steer')} />
            ) : (
              <div className='grid h-full min-h-0 grid-cols-1 gap-3 xl:grid-cols-[2.2fr_1fr]'>
                {showWorkflow ? (
                  <WorkflowView steps={workflowSteps} />
                ) : (
                  <ScreenView frameSrc={latestFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} onExampleClick={(prompt) => setExamplePrompt(prompt)} />
                )}
                <ActionLog entries={visibleLogs} showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} />
              </div>
            )}
          </div>

          {!showSettings && (
            <>
              <InputBar
                mode={mode}
                voiceActive={voiceActive}
                voiceDisabled={!voiceSupported || connectionStatus !== 'connected'}
                voiceError={voiceError}
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
                rates={rates}
              />
              <CostEstimator text={draftInput} provider={settings.provider} model={settings.model} rates={rates} />
            </>
          )}
          <SpendingAlert balance={balance} />
        </section>
      </div>
    </main>
  )
}

export default App
