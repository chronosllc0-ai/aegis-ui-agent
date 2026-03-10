import { useEffect, useMemo, useRef, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { InputBar } from './components/InputBar'
import { ScreenView } from './components/ScreenView'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { Icons } from './components/icons'
import { SettingsPage } from './components/settings/SettingsPage'
import { useSettingsContext } from './context/SettingsContext'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { DEMO_AUTH_USER, DEMO_FRAME, DEMO_LOGS, DEMO_TASKS, DEMO_WORKFLOW_STEPS, type TaskHistoryItem } from './lib/demoData'
import { SettingsPage } from './components/settings/SettingsPage'
import { useSettingsContext } from './context/SettingsContext'
import { useWebSocket, type LogEntry, type SteeringMode } from './hooks/useWebSocket'
import { DEMO_LOGS, DEMO_TASKS, DEMO_WORKFLOW_STEPS, type TaskHistoryItem } from './lib/demoData'

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
  const [isAuthenticated, setIsAuthenticated] = useState(true)
  const seededRef = useRef(false)

  useEffect(() => {
    const demoMode = import.meta.env.DEV
    if (!demoMode || seededRef.current) return
    seededRef.current = true
    setLogs(DEMO_LOGS)
    setWorkflowSteps(DEMO_WORKFLOW_STEPS)
    setTaskHistory(DEMO_TASKS)
    setSelectedTaskId(DEMO_TASKS[0].id)
  }, [setLogs, setWorkflowSteps])

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
      }))
    if (fromLogs.length) {
      setTaskHistory((prev) => [...fromLogs, ...prev])
    }
  }, [logs, taskHistory])

  const filteredHistory = useMemo(() => taskHistory.filter((item) => item.title.toLowerCase().includes(historySearch.toLowerCase())), [historySearch, taskHistory])

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
    window.setTimeout(() => setSending(false), 280)
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
    handleSend(normalized, isWorking ? 'steer' : 'steer')
  }

  const newSession = () => {
    send({ action: 'stop' })
    setQueuedMessages([])
    setTaskStartedAt(null)
    setDurationSeconds(0)
    resetClientState()
    setSelectedTaskId(null)
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

  if (!isAuthenticated) {
    return (
      <main className='flex h-screen items-center justify-center bg-[#111] text-zinc-100'>
        <section className='w-full max-w-md rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] p-6 text-center'>
          <img src='/shield.svg' alt='Aegis logo' className='mx-auto mb-4 h-14 w-14' />
          <h1 className='text-2xl font-semibold'>Welcome to Aegis</h1>
          <p className='mt-2 text-sm text-zinc-400'>Sign in to run live UI navigation sessions and manage workflows.</p>
          <button type='button' onClick={() => setIsAuthenticated(true)} className='mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm'>Continue with Google</button>
        </section>
      </main>
    )
  }

  return (
    <main className='h-screen bg-[#111] p-3 text-zinc-100'>
      <div className='mx-auto flex h-full max-w-[1750px] gap-3'>
        <aside className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-[110%] md:translate-x-0'} fixed inset-y-3 left-3 z-30 w-[280px] rounded-2xl border border-[#2a2a2a] bg-[#171717] p-3 transition md:static md:translate-x-0`}>
          <button type='button' onClick={newSession} className='mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium'>New Task</button>
          <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder='Search task history' className='mb-3 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm' />
          <div className='min-h-0 h-[calc(100%-170px)] overflow-y-auto space-y-3'>
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
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>🧩 Workflow templates ({settings.workflowTemplates.length})</button>
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>⚙️ Settings</button>
            <UserMenu name={settings.displayName} avatarUrl={settings.avatarUrl} onOpenSettings={() => setShowSettings(true)} onSignOut={() => setIsAuthenticated(false)} />
          </div>
        </aside>

        <section className='flex min-h-0 flex-1 flex-col gap-3 md:ml-0'>
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
