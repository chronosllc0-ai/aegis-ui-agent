import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import type { LogEntry } from '../hooks/useWebSocket'
import { Icons } from './icons'

type ActionLogProps = {
  dataTour?: string
  entries: LogEntry[]
  showWorkflow: boolean
  onToggleWorkflow: () => void
  onSaveWorkflow: () => void
}

const STEP_ICON: Record<LogEntry['stepKind'], (className?: string) => ReactElement> = {
  analyze: (className) => Icons.search({ className }),
  click: (className) => Icons.chevronRight({ className }),
  type: (className) => Icons.edit({ className }),
  scroll: (className) => Icons.chevronDown({ className }),
  navigate: (className) => Icons.globe({ className }),
  other: (className) => Icons.workflows({ className }),
}

const STATUS_CLASS: Record<LogEntry['status'], string> = {
  in_progress: 'text-blue-300 border-blue-500/30',
  completed: 'text-emerald-300 border-emerald-500/30',
  failed: 'text-red-300 border-red-500/30',
  steered: 'text-amber-300 border-amber-500/30',
}

export function ActionLog({ entries, showWorkflow, onToggleWorkflow, onSaveWorkflow, dataTour }: ActionLogProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [collapsedTasks, setCollapsedTasks] = useState<Record<string, boolean>>({})

  const grouped = useMemo(() => {
    const map = new Map<string, LogEntry[]>()
    for (const entry of entries) {
      if (!map.has(entry.taskId)) map.set(entry.taskId, [])
      map.get(entry.taskId)?.push(entry)
    }
    return Array.from(map.entries()).reverse()
  }, [entries])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [entries])

  const copyLog = async () => {
    const blob = entries.map((entry) => `[${entry.timestamp}] (${entry.taskId}) ${entry.message} (${entry.elapsedSeconds.toFixed(1)}s)`).join('\n')
    await navigator.clipboard.writeText(blob)
  }

  return (
    <section data-tour={dataTour} className='h-full min-h-0 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-2 sm:rounded-2xl sm:p-3'>
      <div className='mb-2 flex items-center justify-between sm:mb-3'>
        <h2 className='text-xs font-semibold text-zinc-200 sm:text-sm md:text-xl'>Action Log</h2>
        <div className='flex items-center gap-1 text-[10px] sm:gap-2 sm:text-xs md:text-lg'>
          <button type='button' onClick={copyLog} className='rounded-md border border-[#2a2a2a] px-1.5 py-0.5 hover:bg-zinc-800 sm:px-2 sm:py-1'>Copy</button>
          <button type='button' onClick={onToggleWorkflow} className='rounded-md border border-[#2a2a2a] px-1.5 py-0.5 hover:bg-zinc-800 sm:px-2 sm:py-1'>{showWorkflow ? 'List' : 'Workflow'}</button>
          <button type='button' onClick={onSaveWorkflow} className='rounded-md border border-[#2a2a2a] px-1.5 py-0.5 hover:bg-zinc-800 sm:px-2 sm:py-1'>Save</button>
        </div>
      </div>
      <div ref={containerRef} className='h-[calc(100%-2.4rem)] overflow-y-auto font-mono text-xs md:text-lg'>
        {grouped.map(([taskId, taskEntries], idx) => {
          const title = taskEntries[0]?.message ?? `Task ${idx + 1}`
          const isTaskCollapsed = collapsedTasks[taskId] ?? false
          return (
            <div key={taskId} className='mb-2 rounded-md border border-[#2a2a2a] bg-[#111]'>
              <button type='button' onClick={() => setCollapsedTasks((prev) => ({ ...prev, [taskId]: !isTaskCollapsed }))} className='flex w-full items-center justify-between px-3 py-2 text-left text-zinc-300 hover:bg-zinc-900'>
                <span className='truncate'>{title}</span>
                <span>{isTaskCollapsed ? Icons.chevronRight({ className: 'h-3.5 w-3.5' }) : Icons.chevronDown({ className: 'h-3.5 w-3.5' })}</span>
              </button>
              {!isTaskCollapsed && (
                <div className='space-y-1 px-2 pb-2'>
                  {taskEntries.map((entry) => (
                    <div key={entry.id} className={`rounded border px-2 py-1 ${STATUS_CLASS[entry.status]}`}>
                      <div className='mb-1 flex items-center justify-between text-[10px] text-zinc-500'>
                        <span>{entry.timestamp}</span>
                        <span>{entry.elapsedSeconds.toFixed(1)}s</span>
                      </div>
                      <div>
                        <span className='mr-1 inline-flex align-middle'>{STEP_ICON[entry.stepKind]('h-3.5 w-3.5')}</span>
                        {entry.type === 'interrupt' ? 'Task interrupted: ' : ''}
                        {entry.message}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
