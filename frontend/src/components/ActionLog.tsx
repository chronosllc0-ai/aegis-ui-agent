import { useMemo } from 'react'
import type { LogEntry } from '../hooks/useWebSocket'

type ActionLogProps = {
  entries: LogEntry[]
  showWorkflow: boolean
  onToggleWorkflow: () => void
  onSaveWorkflow: () => void
}

export function ActionLog({ entries, showWorkflow, onToggleWorkflow, onSaveWorkflow }: ActionLogProps) {
  const reversed = useMemo(() => [...entries].reverse(), [entries])

  return (
    <section className='h-full rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='mb-3 flex items-center justify-between'>
        <h2 className='text-sm font-semibold'>Action Log</h2>
        <div className='flex gap-2 text-xs'>
          <button type='button' onClick={onToggleWorkflow} className='rounded border border-[#2a2a2a] px-2 py-1'>
            {showWorkflow ? 'List View' : 'Workflow'}
          </button>
          <button type='button' onClick={onSaveWorkflow} className='rounded border border-[#2a2a2a] px-2 py-1'>
            Save as Workflow
          </button>
        </div>
      </div>
      <div className='h-[calc(100%-2rem)] overflow-y-auto space-y-2 text-xs'>
        {reversed.map((entry) => (
          <article key={entry.id} className='rounded border border-[#2a2a2a] bg-[#111] p-2'>
            <div className='mb-1 text-[10px] text-zinc-500'>{entry.timestamp}</div>
            <p>{entry.message}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
