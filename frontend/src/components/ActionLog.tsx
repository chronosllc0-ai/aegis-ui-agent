import { useEffect, useRef } from 'react'
import type { LogEntry } from '../hooks/useWebSocket'

type ActionLogProps = {
  entries: LogEntry[]
}

export function ActionLog({ entries }: ActionLogProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [entries])

  return (
    <section className='h-full rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <h2 className='mb-3 text-sm font-semibold text-zinc-200'>Action Log</h2>
      <div ref={containerRef} className='h-[calc(100%-2rem)] overflow-y-auto font-mono text-xs'>
        {entries.map((entry) => (
          <div key={entry.id} className='mb-2 rounded-md border border-[#2a2a2a] bg-[#111] p-2 text-zinc-300'>
            <div className='mb-1 text-[10px] text-zinc-500'>{entry.timestamp}</div>
            <div className={entry.type === 'interrupt' ? 'text-red-300' : ''}>
              {entry.type === 'interrupt' ? 'Task interrupted: ' : ''}
              {entry.message}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
