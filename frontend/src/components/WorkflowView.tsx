import { useMemo, useState, type ReactElement } from 'react'
import { Icons } from './icons'
import type { WorkflowStep } from '../hooks/useWebSocket'

type WorkflowViewProps = {
  steps: WorkflowStep[]
}

const STATUS_CLASSES: Record<WorkflowStep['status'], string> = {
  in_progress: 'border-blue-400 text-blue-200',
  completed: 'border-emerald-400 text-emerald-200',
  failed: 'border-red-400 text-red-200',
  steered: 'border-amber-400 text-amber-200',
}

const ACTION_ICON: Record<string, (className?: string) => ReactElement> = {
  navigate: (className) => Icons.globe({ className }),
  analyze: (className) => Icons.search({ className }),
  click: (className) => Icons.chevronRight({ className }),
  type: (className) => Icons.edit({ className }),
  scroll: (className) => Icons.chevronDown({ className }),
}

export function WorkflowView({ steps }: WorkflowViewProps) {
  const [selectedId, setSelectedId] = useState<string | null>(steps[0]?.step_id ?? null)

  const ordered = useMemo(() => {
    const roots = steps.filter((step) => !step.parent_step_id)
    const linear: Array<WorkflowStep & { depth: number }> = []
    const walk = (node: WorkflowStep, depth: number) => {
      linear.push({ ...node, depth })
      const children = steps.filter((step) => step.parent_step_id === node.step_id)
      children.forEach((child) => walk(child, depth + 1))
    }
    roots.forEach((root) => walk(root, 0))
    if (!roots.length) steps.forEach((step) => linear.push({ ...step, depth: 0 }))
    return linear
  }, [steps])

  const selected = ordered.find((step) => step.step_id === selectedId) ?? ordered[0]

  return (
    <section className='grid h-full min-h-[480px] grid-cols-[1.5fr_1fr] gap-3 rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='min-h-0 overflow-y-auto'>
        <div className='mb-3 flex items-center justify-between text-xs text-zinc-400'>
          <span>Workflow Execution Flow</span>
          <span>{ordered.length} steps</span>
        </div>
        <div className='space-y-2'>
          {ordered.map((step, index) => (
            <button key={step.step_id} type='button' onClick={() => setSelectedId(step.step_id)} className={`w-full rounded-xl border bg-[#111] p-3 text-left transition hover:border-blue-500/60 ${STATUS_CLASSES[step.status]} ${selected?.step_id === step.step_id ? 'ring-1 ring-blue-500/50' : ''}`}>
              <div className='mb-1 flex items-center justify-between text-[11px]'>
                <span>Step {index + 1}</span>
                <span>{step.duration_ms}ms</span>
              </div>
              <p className='font-medium text-zinc-100'>{step.action}</p>
              <p className='text-xs text-zinc-300'>{step.description}</p>
              <p className='mt-1 text-[10px] text-zinc-500'>Parent: {step.parent_step_id ?? 'none'}</p>
            </button>
          ))}
        </div>
      </div>

      <aside className='min-h-0 rounded-xl border border-[#2a2a2a] bg-[#111] p-3 text-xs'>
        <h3 className='mb-3 text-sm font-semibold text-zinc-200'>Step Details</h3>
        {selected ? (
          <div className='space-y-2'>
            <Detail label='Action' value={selected.action} />
            <Detail label='Status' value={selected.status} />
            <Detail label='Timestamp' value={selected.timestamp} />
            <Detail label='Duration' value={`${selected.duration_ms} ms`} />
            <Detail label='Parent Step' value={selected.parent_step_id ?? 'none'} />
            <Detail label='Description' value={selected.description.replace(/^↳\s*/g, '')} />
          </div>
        ) : (
          <p className='text-zinc-500'>No workflow data yet.</p>
        )}
      </aside>
    </section>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className='text-zinc-500'>{label}</p>
      <p className='text-zinc-200'>{value}</p>
    </div>
  )
}
