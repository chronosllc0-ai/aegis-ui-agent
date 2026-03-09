import { useMemo, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { InputBar } from './components/InputBar'
import { ScreenView } from './components/ScreenView'
import { useWebSocket, type SteeringMode } from './hooks/useWebSocket'

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
          onModeChange={setMode}
          onSend={handleSend}
          queuedMessages={queuedMessages}
          onDeleteQueueItem={(index) => setQueuedMessages((prev) => prev.filter((_, i) => i !== index))}
        />
      </div>
    </main>
  )
}

export default App
