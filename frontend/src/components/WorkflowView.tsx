import type { WorkflowStep } from '../hooks/useWebSocket'

type WorkflowViewProps = {
  steps: WorkflowStep[]
}

const STATUS_BORDER: Record<WorkflowStep['status'], string> = {
  in_progress: 'border-blue-400',
  completed: 'border-emerald-400',
  failed: 'border-red-400',
  steered: 'border-yellow-400',
}

export function WorkflowView({ steps }: WorkflowViewProps) {
  return (
    <section className='h-full min-h-[420px] overflow-y-auto rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='mb-3 flex items-center justify-between text-xs text-zinc-400'>
        <span>Workflow Graph (fallback view)</span>
        <span>{steps.length} nodes</span>
      </div>
      <div className='space-y-3'>
        {steps.map((step) => (
          <article key={step.step_id} className={`rounded-xl border bg-[#111] p-3 ${STATUS_BORDER[step.status]}`}>
            <p className='text-xs text-zinc-400'>{step.timestamp}</p>
            <p className='font-medium'>{step.action}</p>
            <p className='text-sm text-zinc-300'>{step.description}</p>
            <p className='text-xs text-zinc-500'>duration {step.duration_ms}ms</p>
          </article>
        ))}
      </div>
    </section>
  )
}
