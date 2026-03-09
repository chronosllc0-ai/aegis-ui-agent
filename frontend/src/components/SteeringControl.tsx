import type { SteeringMode } from '../hooks/useWebSocket'

type SteeringControlProps = {
  mode: SteeringMode
  onChange: (mode: SteeringMode) => void
}

const MODES: SteeringMode[] = ['steer', 'interrupt', 'queue']

export function SteeringControl({ mode, onChange }: SteeringControlProps) {
  return (
    <div className='inline-flex rounded-lg border border-[#2a2a2a] bg-[#111] p-1 text-xs'>
      {MODES.map((option) => (
        <button
          key={option}
          type='button'
          onClick={() => onChange(option)}
          className={`rounded-md px-3 py-1 capitalize transition ${mode === option ? 'bg-blue-500 text-white' : 'text-zinc-300 hover:bg-zinc-800'}`}
        >
          {option}
        </button>
      ))}
    </div>
  )
}
