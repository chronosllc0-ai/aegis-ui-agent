import { useEffect, useMemo, useRef, useState } from 'react'
import { useMemo, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { InputBar } from './components/InputBar'
import { ScreenView } from './components/ScreenView'
import { useWebSocket, type SteeringMode } from './hooks/useWebSocket'

type Toast = { id: string; kind: 'success' | 'error'; message: string }

function App() {
  const { connectionStatus, isWorking, latestFrame, logs, currentUrl, send, resetClientState } = useWebSocket()
  const [mode, setMode] = useState<SteeringMode>('steer')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [steeringFlashKey, setSteeringFlashKey] = useState<number>(0)
  const [panelRatio, setPanelRatio] = useState<number>(67)
  const [logCollapsed, setLogCollapsed] = useState<boolean>(false)
  const [urlInput, setUrlInput] = useState<string>('about:blank')
  const [taskStartedAt, setTaskStartedAt] = useState<number | null>(null)
  const [durationSeconds, setDurationSeconds] = useState<number>(0)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [sending, setSending] = useState<boolean>(false)
  const [examplePrompt, setExamplePrompt] = useState<string | null>(null)
  const dragRef = useRef<boolean>(false)

  const connectionLabel = useMemo(() => {
    if (connectionStatus === 'connected') return { cls: 'bg-emerald-400', label: 'Connected' }
    if (connectionStatus === 'connecting') return { cls: 'bg-yellow-400', label: 'Reconnecting...' }
    return { cls: 'bg-red-400', label: 'Disconnected' }
  }, [connectionStatus])

  useEffect(() => {
    setUrlInput(currentUrl)
  }, [currentUrl])

  useEffect(() => {
    document.title = isWorking ? 'Aegis · Working...' : 'Aegis'
  }, [isWorking])

  useEffect(() => {
    if (isWorking && taskStartedAt === null) {
      setTaskStartedAt(Date.now())
      setDurationSeconds(0)
    }
    if (!isWorking) {
      return
    }
    const timer = window.setInterval(() => {
      if (taskStartedAt !== null) {
        setDurationSeconds(Math.floor((Date.now() - taskStartedAt) / 1000))
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isWorking, taskStartedAt])

  useEffect(() => {
    const latest = logs[logs.length - 1]
    if (!latest) return
    if (latest.type === 'result') {
      const toast: Toast = { id: crypto.randomUUID(), kind: 'success', message: 'Task completed successfully' }
      setToasts((prev) => [...prev, toast])
      window.setTimeout(() => setToasts((prev) => prev.filter((item) => item.id !== toast.id)), 3000)
    }
    if (latest.type === 'error') {
      const toast: Toast = { id: crypto.randomUUID(), kind: 'error', message: latest.message }
      setToasts((prev) => [...prev, toast])
      window.setTimeout(() => setToasts((prev) => prev.filter((item) => item.id !== toast.id)), 3000)
    }
  }, [logs])

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragRef.current) return
      const nextRatio = Math.max(45, Math.min(80, (event.clientX / window.innerWidth) * 100))
      setPanelRatio(nextRatio)
    }
    const onMouseUp = () => {
      dragRef.current = false
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const handleSend = (instruction: string, selectedMode: SteeringMode) => {
    setSending(true)
    window.setTimeout(() => setSending(false), 250)
function App() {
  const { connectionStatus, isWorking, latestFrame, logs, send } = useWebSocket()
  const [mode, setMode] = useState<SteeringMode>('steer')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [steeringFlashKey, setSteeringFlashKey] = useState<number>(0)

  const statusColor = useMemo(() => {
    if (connectionStatus === 'connected') return 'bg-green-400'
    if (connectionStatus === 'connecting') return 'bg-yellow-400'
    return 'bg-red-400'
  }, [connectionStatus])

  const handleSend = (instruction: string, selectedMode: SteeringMode) => {
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
    const action = isWorking ? 'steer' : 'navigate'
    send({ action, instruction })
  }

  const submitUrl = () => {
    const normalized = /^https?:\/\//i.test(urlInput) ? urlInput : `https://${urlInput}`
    if (isWorking) {
      handleSend(normalized, 'steer')
      return
    }
    setSending(true)
    window.setTimeout(() => setSending(false), 250)
    send({ action: 'navigate', instruction: normalized })
  }

  const newSession = () => {
    send({ action: 'stop' })
    setQueuedMessages([])
    setTaskStartedAt(null)
    setDurationSeconds(0)
    setUrlInput('about:blank')
    resetClientState()
  }

  return (
    <main className='h-screen bg-[#111] p-4 text-zinc-100'>
      <div className='mx-auto flex h-full max-w-[1700px] flex-col gap-3'>
        <header className='flex items-center justify-between rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2'>
          <div className='flex items-center gap-2'>
            <span className='text-xl'>🛡️</span>
            <h1 className='text-xl font-bold'>Aegis</h1>
          </div>
          <div className='flex items-center gap-4 text-xs text-zinc-300'>
            <div className='flex items-center gap-2'>
              <span className={`h-2.5 w-2.5 rounded-full ${connectionLabel.cls}`} />
              {connectionLabel.label}
            </div>
            <div>Session {Math.floor(durationSeconds / 60)}:{String(durationSeconds % 60).padStart(2, '0')}</div>
            <button type='button' onClick={newSession} className='rounded-md border border-[#2a2a2a] px-3 py-1.5 text-zinc-200 hover:border-blue-500/60 hover:bg-zinc-900'>
              New Session
            </button>
          </div>
        </header>

        <section className='flex items-center gap-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-3 py-2'>
          <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go back' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800'>←</button>
          <button type='button' onClick={() => send({ action: 'navigate', instruction: 'go forward' })} className='rounded border border-[#2a2a2a] px-2 hover:bg-zinc-800'>→</button>
          <span className='text-xs text-zinc-400'>🌐</span>
          <input
            value={urlInput}
            onChange={(event) => setUrlInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') submitUrl()
            }}
            className='w-full rounded-md border border-[#2a2a2a] bg-[#111] px-2 py-1 text-sm outline-none focus:border-blue-500/70'
          />
          <button type='button' onClick={submitUrl} className='rounded border border-[#2a2a2a] px-3 py-1 text-xs hover:bg-zinc-800'>Go</button>
        </section>

        <section className='flex min-h-0 flex-1 gap-2'>
          <div className='min-h-0' style={{ width: logCollapsed ? '100%' : `${panelRatio}%` }}>
            <ScreenView frameSrc={latestFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} onExampleClick={(prompt) => setExamplePrompt(prompt)} />
          </div>
          {!logCollapsed && (
            <button
              type='button'
              onMouseDown={() => {
                dragRef.current = true
              }}
              className='hidden w-1 cursor-col-resize rounded bg-[#2a2a2a] hover:bg-blue-500/70 lg:block'
              aria-label='Resize panels'
            />
          )}
          <div className={`${logCollapsed ? 'hidden' : 'block'} min-h-0 flex-1 max-lg:w-[40%] max-md:hidden`}>
            <ActionLog entries={logs} isCollapsed={false} onToggleCollapse={() => setLogCollapsed(true)} />
          </div>
          <div className='block min-h-0 md:hidden'>
            <ActionLog entries={logs} isCollapsed={logCollapsed} onToggleCollapse={() => setLogCollapsed((prev) => !prev)} />
          </div>
  return (
    <main className='h-screen bg-[#111] p-4 text-zinc-100'>
      <div className='mx-auto flex h-full max-w-[1600px] flex-col gap-3'>
        <header className='flex items-center justify-between rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2'>
          <h1 className='text-lg font-semibold'>Aegis UI Navigator</h1>
          <div className='flex items-center gap-2 text-xs text-zinc-300'>
            <span className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
            {connectionStatus}
          </div>
        </header>

        <section className='grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[2fr_1fr]'>
          <ScreenView frameSrc={latestFrame} isWorking={isWorking} steeringFlashKey={steeringFlashKey} />
          <ActionLog entries={logs} />
        </section>

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
      </div>

      <div className='pointer-events-none fixed right-4 top-4 z-50 space-y-2'>
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-lg border px-3 py-2 text-sm shadow-lg ${toast.kind === 'success' ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-100' : 'border-red-500/40 bg-red-500/20 text-red-100'}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
        />
      </div>
    </main>
  )
}

export default App
