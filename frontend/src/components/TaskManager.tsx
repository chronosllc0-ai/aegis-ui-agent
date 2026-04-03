import { useState } from 'react'
import { useBackgroundTasks } from '../hooks/useBackgroundTasks'

export function TaskManager() {
  const { tasks, loading, load, runResearchTask, cancel } = useBackgroundTasks()
  const [topic, setTopic] = useState('')

  const enqueue = async () => {
    const value = topic.trim()
    if (!value) return
    await runResearchTask(value)
    setTopic('')
  }

  return (
    <section className='space-y-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold text-zinc-100'>Background Tasks</h3>
        <button type='button' onClick={() => void load()} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800'>Refresh</button>
      </div>
      <div className='flex gap-2'>
        <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder='Queue research topic...' className='w-full rounded border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-100' />
        <button type='button' onClick={() => void enqueue()} className='rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500'>Queue</button>
      </div>
      {loading && <p className='text-xs text-zinc-400'>Loading tasks…</p>}
      <div className='space-y-2'>
        {tasks.map((task) => (
          <div key={task.id} className='rounded border border-[#2a2a2a] bg-[#111] p-2'>
            <div className='flex items-center justify-between'>
              <p className='text-xs font-medium text-zinc-100'>{task.title}</p>
              <button type='button' onClick={() => void cancel(task.id)} className='text-[10px] text-red-400 hover:text-red-300'>Cancel</button>
            </div>
            <p className='text-[11px] text-zinc-500'>{task.status} · {task.progress_pct}%</p>
          </div>
        ))}
        {!loading && tasks.length === 0 && <p className='text-xs text-zinc-500'>No tasks yet.</p>}
      </div>
    </section>
  )
}
