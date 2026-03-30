import { useCallback, useEffect } from 'react'
import { useBackgroundTasks } from '../hooks/useBackgroundTasks'
import type { BackgroundTaskEntry } from '../hooks/useBackgroundTasks'

type TaskManagerProps = { isOpen: boolean; onToggle: () => void }

const STATUS_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  queued: { icon: '◎', color: 'text-zinc-400', bg: 'bg-zinc-800' },
  running: { icon: '◉', color: 'text-blue-400', bg: 'bg-blue-900/20' },
  paused: { icon: '⏸', color: 'text-amber-400', bg: 'bg-amber-900/20' },
  completed: { icon: '✓', color: 'text-emerald-400', bg: 'bg-emerald-900/20' },
  failed: { icon: '✗', color: 'text-red-400', bg: 'bg-red-900/20' },
  cancelled: { icon: '—', color: 'text-zinc-500', bg: 'bg-zinc-800/50' },
}

export function TaskManager({ isOpen, onToggle }: TaskManagerProps) {
  const { tasks, badgeCount, loading, fetchTasks, fetchBadge, clearBadge, cancelTask, pauseTask, resumeTask } = useBackgroundTasks()

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (isOpen) {
        void fetchTasks()
        void clearBadge()
      }
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [isOpen, fetchTasks, clearBadge])

  useEffect(() => {
    const interval = window.setInterval(() => { void fetchBadge() }, 30000)
    void fetchBadge()
    return () => window.clearInterval(interval)
  }, [fetchBadge])

  useEffect(() => {
    if (!isOpen) return
    const hasRunning = tasks.some((t) => t.status === 'running' || t.status === 'queued')
    if (!hasRunning) return
    const interval = window.setInterval(() => { void fetchTasks() }, 5000)
    return () => window.clearInterval(interval)
  }, [isOpen, tasks, fetchTasks])

  const renderActions = useCallback((task: BackgroundTaskEntry) => {
    const actions: { label: string; onClick: () => void; color: string }[] = []
    if (task.status === 'running' || task.status === 'queued') actions.push({ label: 'Cancel', onClick: () => void cancelTask(task.id), color: 'text-red-400 hover:text-red-300' })
    if (task.status === 'queued') actions.push({ label: 'Pause', onClick: () => void pauseTask(task.id), color: 'text-amber-400 hover:text-amber-300' })
    if (task.status === 'paused') actions.push({ label: 'Resume', onClick: () => void resumeTask(task.id), color: 'text-blue-400 hover:text-blue-300' })
    return actions
  }, [cancelTask, pauseTask, resumeTask])

  if (!isOpen) {
    return <button type='button' onClick={onToggle} className='relative rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-zinc-400 hover:bg-zinc-700'>Tasks{badgeCount > 0 && <span className='absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-[9px] font-bold text-white'>{badgeCount}</span>}</button>
  }

  return (
    <div className='flex h-full w-80 shrink-0 flex-col border-l border-[#2a2a2a] bg-[#1a1a1a]'>
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3'>
        <h3 className='text-xs font-semibold uppercase tracking-wider text-zinc-400'>Background Tasks</h3>
        <button type='button' onClick={onToggle} className='text-zinc-500 hover:text-zinc-300'>✕</button>
      </div>
      <div className='flex-1 overflow-y-auto p-3'>
        {loading && tasks.length === 0 ? <div className='flex justify-center py-8'><div className='h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' /></div> : (
          tasks.length === 0 ? <p className='py-8 text-center text-xs text-zinc-600'>No background tasks</p> : (
            <div className='space-y-2'>
              {tasks.map((task) => {
                const ss = STATUS_STYLES[task.status] || STATUS_STYLES.queued
                const actions = renderActions(task)
                return (
                  <div key={task.id} className={`rounded-lg border border-zinc-800 ${ss.bg} p-2.5`}>
                    <div className='flex items-start gap-2'>
                      <span className={`mt-0.5 text-sm font-mono ${ss.color} ${task.status === 'running' ? 'animate-pulse' : ''}`}>{ss.icon}</span>
                      <div className='min-w-0 flex-1'>
                        <p className='text-xs font-medium text-zinc-200'>{task.title}</p>
                        {task.status === 'running' && <div className='mt-1.5 h-1 rounded-full bg-zinc-800'><div className='h-1 rounded-full bg-blue-500' style={{ width: `${task.progress_pct}%` }} /></div>}
                      </div>
                    </div>
                    {actions.length > 0 && <div className='mt-1.5 flex gap-2 pl-6'>{actions.map((a) => <button key={a.label} type='button' onClick={a.onClick} className={`text-[10px] ${a.color}`}>{a.label}</button>)}</div>}
                  </div>
                )
              })}
            </div>
          )
        )}
      </div>
    </div>
  )
}
