import type { SteeringMode } from '../hooks/useWebSocket'

type SteeringControlProps = {
  mode: SteeringMode
  queueCount: number
  onChange: (mode: SteeringMode) => void
  compact?: boolean
}

const MODES: SteeringMode[] = ['steer', 'interrupt', 'queue']

export function SteeringControl({ mode, queueCount, onChange, compact = false }: SteeringControlProps) {
  return (
    <div className={`inline-flex rounded-lg border border-[#2a2a2a] bg-[#111] text-xs ${compact ? 'p-0.5' : 'p-1'}`}>
      {MODES.map((option) => (
        <button
          key={option}
          type='button'
          onClick={() => onChange(option)}
          className={`relative rounded-md capitalize transition ${compact ? 'px-2 py-0.5 text-[11px]' : 'px-3 py-1'} ${mode === option ? 'bg-blue-500 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}
        >
          {option}
          {option === 'queue' && queueCount > 0 && (
            <span className='ml-2 rounded-full bg-zinc-900 px-1.5 py-0.5 text-[10px] text-blue-200'>{queueCount}</span>
          )}
        </button>
      ))}
    </div>
  )
}
