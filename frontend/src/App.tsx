import { useMemo, useState } from 'react'
import { ActionLog } from './components/ActionLog'
import { InputBar } from './components/InputBar'
import { ScreenView } from './components/ScreenView'
import { UserMenu } from './components/UserMenu'
import { WorkflowView } from './components/WorkflowView'
import { SettingsPage } from './components/settings/SettingsPage'
import { useSettingsContext } from './context/SettingsContext'
import { useWebSocket, type SteeringMode } from './hooks/useWebSocket'

function App() {
  const { connectionStatus, isWorking, latestFrame, logs, workflowSteps, send } = useWebSocket()
  const { settings, patchSettings, wsConfig } = useSettingsContext()

  const [mode, setMode] = useState<SteeringMode>('steer')
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])
  const [showSettings, setShowSettings] = useState(false)
  const [showWorkflow, setShowWorkflow] = useState(false)

  const historyCount = useMemo(() => logs.filter((item) => item.type === 'result').length, [logs])

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
    send({ action: 'config', settings: wsConfig })
    send({ action: isWorking ? 'steer' : 'navigate', instruction })
  }

  const saveWorkflow = () => {
    if (!logs.length) return
    const firstStep = logs.find((entry) => entry.type === 'step')
    patchSettings({
      workflowTemplates: [
        ...settings.workflowTemplates,
        {
          id: crypto.randomUUID(),
          name: `Workflow ${settings.workflowTemplates.length + 1}`,
          instruction: firstStep?.message ?? 'Saved workflow',
          stepCount: logs.length,
          lastRunAt: new Date().toISOString(),
        },
      ],
    })
  }

  return (
    <main className='h-screen bg-[#111] p-3 text-zinc-100'>
      <div className='mx-auto grid h-full max-w-[1700px] grid-cols-[260px_1fr] gap-3'>
        <aside className='flex flex-col rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
          <button type='button' onClick={() => send({ action: 'stop' })} className='mb-3 rounded bg-blue-600 px-3 py-2 text-sm'>New Task</button>
          <input placeholder='Search task history' className='mb-3 rounded border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm' />
          <div className='min-h-0 flex-1 overflow-y-auto text-xs text-zinc-400'>Task history ({historyCount})</div>
          <div className='mt-3 space-y-2 border-t border-[#2a2a2a] pt-3 text-xs'>
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>🧩 Workflow templates ({settings.workflowTemplates.length})</button>
            <button type='button' onClick={() => setShowSettings(true)} className='block w-full rounded border border-[#2a2a2a] px-2 py-2 text-left'>⚙️ Settings</button>
            <UserMenu name={settings.displayName} avatarUrl={settings.avatarUrl} onOpenSettings={() => setShowSettings(true)} />
          </div>
        </aside>

        <section className='flex min-h-0 flex-col gap-3'>
          <header className='flex items-center justify-between rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2 text-xs'>
            <h1 className='text-sm font-semibold'>Aegis UI Navigator</h1>
            <span>{connectionStatus}</span>
          </header>

          <div className='min-h-0 flex-1'>
            {showSettings ? (
              <SettingsPage onBack={() => setShowSettings(false)} onRunWorkflow={(instruction) => handleSend(instruction, 'steer')} />
            ) : (
              <div className='grid h-full min-h-0 grid-cols-[2fr_1fr] gap-3'>
                {showWorkflow ? <WorkflowView steps={workflowSteps} /> : <ScreenView frameSrc={latestFrame} isWorking={isWorking} />}
                <ActionLog entries={logs} showWorkflow={showWorkflow} onToggleWorkflow={() => setShowWorkflow((prev) => !prev)} onSaveWorkflow={saveWorkflow} />
              </div>
            )}
          </div>

          {!showSettings && <InputBar mode={mode} onModeChange={setMode} onSend={handleSend} queuedMessages={queuedMessages} sending={false} />}
        </section>
      </div>
    </main>
  )
}

export default App
