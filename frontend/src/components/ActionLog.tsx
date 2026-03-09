import { useEffect, useMemo, useRef, useState } from 'react'
import type { LogEntry } from '../hooks/useWebSocket'

type ActionLogProps = {
  entries: LogEntry[]
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}

const STEP_ICON: Record<LogEntry['stepKind'], string> = {
  analyze: '🔍',
  click: '🖱️',
  type: '⌨️',
  scroll: '📜',
  navigate: '🌐',
  other: '•',
}

const STATUS_CLASS: Record<LogEntry['status'], string> = {
  in_progress: 'text-blue-300 border-blue-500/30',
  completed: 'text-emerald-300 border-emerald-500/30',
  failed: 'text-red-300 border-red-500/30',
  steered: 'text-amber-300 border-amber-500/30',
}

export function ActionLog({ entries, isCollapsed = false, onToggleCollapse }: ActionLogProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [collapsedTasks, setCollapsedTasks] = useState<Record<string, boolean>>({})

  const grouped = useMemo(() => {
    const map = new Map<string, LogEntry[]>()
    for (const entry of entries) {
      if (!map.has(entry.taskId)) {
        map.set(entry.taskId, [])
      }
      map.get(entry.taskId)?.push(entry)
    }
    return Array.from(map.entries())
  }, [entries])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [entries])

  const copyLog = async () => {
    const blob = entries
      .map((entry) => `[${entry.timestamp}] (${entry.taskId}) ${entry.message} (${entry.elapsedSeconds.toFixed(1)}s)`)
      .join('\n')
    await navigator.clipboard.writeText(blob)
  }

  if (isCollapsed) {
    return (
      <button
        type='button'
        onClick={onToggleCollapse}
        className='flex h-full min-h-[420px] w-full items-center justify-center rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] text-xl hover:border-blue-500/70'
      >
        📋
      </button>
    )
  }

  return (
    <section className='h-full rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='mb-3 flex items-center justify-between'>
        <h2 className='text-sm font-semibold text-zinc-200'>Action Log</h2>
        <div className='flex items-center gap-2'>
          <button type='button' onClick={copyLog} className='rounded-md border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800'>Copy Log</button>
          {onToggleCollapse && (
            <button type='button' onClick={onToggleCollapse} className='rounded-md border border-[#2a2a2a] px-2 py-1 text-xs hover:bg-zinc-800 lg:hidden'>Hide</button>
          )}
        </div>
      </div>
      <div ref={containerRef} className='h-[calc(100%-2.4rem)] overflow-y-auto font-mono text-xs'>
        {grouped.map(([taskId, taskEntries], idx) => {
          const title = taskEntries[0]?.message ?? `Task ${idx + 1}`
          const isTaskCollapsed = collapsedTasks[taskId] ?? false
          return (
            <div key={taskId} className='mb-2 rounded-md border border-[#2a2a2a] bg-[#111]'>
              <button
                type='button'
                onClick={() => setCollapsedTasks((prev) => ({ ...prev, [taskId]: !isTaskCollapsed }))}
                className='flex w-full items-center justify-between px-3 py-2 text-left text-zinc-300 hover:bg-zinc-900'
              >
                <span className='truncate'>{title}</span>
                <span>{isTaskCollapsed ? '▸' : '▾'}</span>
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
                        <span className='mr-1'>{STEP_ICON[entry.stepKind]}</span>
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
