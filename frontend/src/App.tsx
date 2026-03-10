import { useEffect, useMemo, useRef, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { InputBar } from './components/InputBar'
import { ScreenView } from './components/ScreenView'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { SettingsPage } from './components/settings/SettingsPage'
import { useSettingsContext } from './context/SettingsContext'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { DEMO_AUTH_USER, DEMO_FRAME, DEMO_LOGS, DEMO_TASKS, DEMO_WORKFLOW_STEPS, type TaskHistoryItem } from './lib/demoData'

function App() {
  const { connectionStatus, isWorking, latestFrame, logs, workflowSteps, currentUrl, send, resetClientState, setLogs, setWorkflowSteps } = useWebSocket()
  const { settings, patchSettings, wsConfig } = useSettingsContext()

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
  const [authState, setAuthState] = useState<'signed_out' | 'loading' | 'signed_in' | 'error'>('signed_in')
  const [authError, setAuthError] = useState<string>('')
  const seededRef = useRef(false)

  useEffect(() => {
    const demoMode = import.meta.env.DEV
    if (!demoMode || seededRef.current) return
    seededRef.current = true
    setLogs(DEMO_LOGS)
    setWorkflowSteps(DEMO_WORKFLOW_STEPS)
    setTaskHistory(DEMO_TASKS)
    setSelectedTaskId(DEMO_TASKS[0].id)
    patchSettings({ displayName: DEMO_AUTH_USER.name, email: DEMO_AUTH_USER.email, avatarUrl: DEMO_AUTH_USER.avatarUrl })
  }, [setLogs, setWorkflowSteps, patchSettings])

  useEffect(() => {
    setUrlInput(currentUrl)
  }, [currentUrl])

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
    const existingTaskIds = new Set(taskHistory.map((item) => item.id))
    const fromLogs = logs
      .map((entry) => entry.taskId)
      .filter((taskId) => taskId !== 'idle' && !existingTaskIds.has(taskId))
      .map((taskId) => ({
        id: taskId,
        title: logs.find((entry) => entry.taskId === taskId)?.message ?? 'Task',
        dateLabel: 'Today',
        instruction: logs.find((entry) => entry.taskId === taskId)?.message ?? 'Task',
        summary: 'Session captured from live logs.',
      }))
    if (fromLogs.length) setTaskHistory((prev) => [...fromLogs, ...prev])
  }, [logs, taskHistory])

  const filteredHistory = useMemo(
    () => taskHistory.filter((item) => item.title.toLowerCase().includes(historySearch.toLowerCase()) || item.instruction.toLowerCase().includes(historySearch.toLowerCase())),
    [historySearch, taskHistory],
  )

  const visibleLogs: LogEntry[] = useMemo(() => {
    if (!selectedTaskId) return logs
    return logs.filter((entry) => entry.taskId === selectedTaskId)
  }, [logs, selectedTaskId])

  const connectionLabel = useMemo(() => {
    if (connectionStatus === 'connected') return { cls: 'bg-emerald-400', label: 'Connected' }
    if (connectionStatus === 'connecting') return { cls: 'bg-yellow-400', label: 'Reconnecting…' }
    return { cls: 'bg-red-400', label: 'Disconnected' }
  }, [connectionStatus])

  const displayFrame = latestFrame || (import.meta.env.DEV && selectedTaskId ? DEMO_FRAME : '')

  const handleSend = (instruction: string, selectedMode: SteeringMode) => {
    setSending(true)
    window.setTimeout(() => setSending(false), 260)
    if (selectedMode === 'queue') {
      setQueuedMessages((prev) => [...prev, instruction])
      send({ action: 'queue', instruction })
      return
    }
    if (selectedMode === 'interrupt') {
      send({ action: 'interrupt', instruction })
      return
    }
    setSteeringFlashKey((prev) => prev + 1)
    send({ action: 'config', settings: wsConfig })
    send({ action: isWorking ? 'steer' : 'navigate', instruction })
  }

  const submitUrl = () => {
    const normalized = /^https?:\/\//i.test(urlInput) ? urlInput : `https://${urlInput}`
    handleSend(normalized, 'steer')
  }

  const newSession = () => {
    send({ action: 'stop' })
    setQueuedMessages([])
    setTaskStartedAt(null)
    setDurationSeconds(0)
    resetClientState()
    setSelectedTaskId(null)
    setShowWorkflow(false)
  }

  const saveWorkflow = () => {
    if (!visibleLogs.length) return
    const selectedTask = selectedTaskId ? taskHistory.find((item) => item.id === selectedTaskId) : null
    const fallbackInstruction = visibleLogs.find((entry) => entry.type === 'step' && entry.stepKind === 'navigate' && !entry.message.toLowerCase().includes('session settings updated'))?.message

    patchSettings({
      workflowTemplates: [
        {
          id: crypto.randomUUID(),
          name: selectedTask?.title ?? `Workflow ${settings.workflowTemplates.length + 1}`,
          description: selectedTask?.summary ?? 'Saved from dashboard run.',
          instruction: selectedTask?.instruction ?? fallbackInstruction ?? 'Saved workflow instruction',
          tags: ['saved', 'dashboard'],
          usesIntegrations: settings.integrations.filter((item) => item.enabled).map((item) => item.name),
          stepCount: visibleLogs.length,
          favorite: false,
          lastRunAt: new Date().toISOString(),
        },
        ...settings.workflowTemplates,
      ],
    })
  }


  const handleSignOut = () => {
    send({ action: 'stop' })
    resetClientState()
    setQueuedMessages([])
    setShowSettings(false)
    setShowWorkflow(false)
    setSelectedTaskId(null)
    setTaskStartedAt(null)
    setDurationSeconds(0)
    setAuthState('signed_out')
  }

  const signIn = () => {
    setAuthState('loading')
    setAuthError('')
    window.setTimeout(() => {
      if (Math.random() > 0.05) {
        setAuthState('signed_in')
      } else {
        setAuthState('error')
        setAuthError('Could not reach auth provider. Please try again.')
      }
    }, 700)
  }

  if (authState !== 'signed_in') {
    return (
      <main className='flex h-screen items-center justify-center bg-[#0f1115] px-4 text-zinc-100'>
        <section className='w-full max-w-3xl rounded-2xl border border-[#2a2a2a] bg-gradient-to-br from-[#161a22] to-[#12151c] p-8 shadow-2xl'>
          <div className='grid gap-8 md:grid-cols-[1.2fr_1fr]'>
            <div>
              <img src='/shield.svg' alt='Aegis logo' className='mb-5 h-14 w-14' />
              <h1 className='text-3xl font-semibold'>Operate any interface with Aegis</h1>
              <p className='mt-3 text-sm text-zinc-400'>A multimodal UI navigator for cross-app workflows, messaging automation, and visual task execution.</p>
              <ul className='mt-5 space-y-2 text-sm text-zinc-300'>
                <li>• Visual browser control with step-by-step action logs</li>
                <li>• Workflow templates, replay, and integration-aware automations</li>
                <li>• MCP-enabled extensions for messaging and tools</li>
              </ul>
            </div>

            <div className='rounded-xl border border-[#2a2a2a] bg-[#10131a] p-5'>
              <h2 className='text-lg font-semibold'>Sign in</h2>
              <p className='mt-1 text-xs text-zinc-500'>Use your Google account to access settings, workflows, and session history.</p>
              <button type='button' onClick={signIn} disabled={authState === 'loading'} className='mt-5 w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium disabled:opacity-70'>
                {authState === 'loading' ? 'Connecting…' : 'Continue with Google'}
              </button>
              {authState === 'error' && <p className='mt-3 text-xs text-red-300'>{authError}</p>}
              <button type='button' className='mt-3 w-full rounded-lg border border-[#2a2a2a] px-4 py-2 text-sm text-zinc-300'>Use email instead</button>
            </div>
          </div>
        </section>
      </main>
    )
  }

  return (
    <main className='h-screen overflow-hidden bg-[#111] p-3 text-zinc-100'>
      <div className='mx-auto flex h-full max-w-[1780px] gap-3'>
        <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] md:translate-x-0'} fixed inset-y-3 left-3 z-30 w-[300px] rounded-2xl border border-[#2a2a2a] bg-[#171717] p-3 transition md:static md:translate-x-0`}>
          <button type='button' onClick={newSession} className='mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium'>New Task</button>
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Search task history' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm' />

          <div className='h-[calc(100%-190px)] overflow-y-auto space-y-3'>
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
                        <p className='truncate text-zinc-500'>{item.summary}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>🧩 Workflow templates ({settings.workflowTemplates.length})</button>
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>⚙️ Settings</button>
            <UserMenu name={settings.displayName} avatarUrl={settings.avatarUrl} onOpenSettings={() => setShowSettings(true)} onSignOut={handleSignOut} />
          </div>
        </aside>

        <section className='flex min-h-0 flex-1 flex-col gap-3'>
          <header className='flex items-center justify-between rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2'>
            <div className='flex items-center gap-2'>
              <button type='button' onClick={() => setSidebarOpen((prev) => !prev)} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs md:hidden'>☰</button>
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
          </header>

          {!showSettings && (
            <section className='flex items-center gap-2 rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2'>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go back' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800'>←</button>
              <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go forward' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800'>→</button>
              <span className='text-xs text-zinc-400'>🌐</span>
              <input value={urlInput} onChange={(event) => setUrlInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submitUrl()} className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-sm outline-none focus:border-blue-500/70' />
              <button type='button' onClick={submitUrl} className='rounded border border-[#2a2a2a] px-3 py-1 text-xs hover:bg-zinc-800'>Go</button>
            </section>
          )}

          <div className='min-h-0 flex-1'>
            {showSettings ? (
              <SettingsPage onBack={() => setShowSettings(false)} onRunWorkflow={(instruction) => handleSend(instruction, 'steer')} />
            ) : (
              <div className='grid h-full min-h-0 grid-cols-1 gap-3 xl:grid-cols-[2.1fr_1fr]'>
                {showWorkflow ? (
                  <WorkflowView steps={workflowSteps} />
                ) : (
                  <ScreenView frameSrc={displayFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} onExampleClick={(prompt) => setExamplePrompt(prompt)} />
                )}
                <ActionLog entries={visibleLogs} showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} />
              </div>
            )}
          </div>

          {!showSettings && (
            <InputBar
              mode={mode}
              voiceActive={false}
              sending={sending}
              onModeChange={setMode}
              onSend={handleSend}
              queuedMessages={queuedMessages}
              onDeleteQueueItem={(index) => setQueuedMessages((prev) => prev.filter((_, i) => i !== index))}
              examplePrompt={examplePrompt}
              onExampleHandled={() => setExamplePrompt(null)}
            />
          )}
        </section>
      </div>
    </main>
  )
}

export default App
