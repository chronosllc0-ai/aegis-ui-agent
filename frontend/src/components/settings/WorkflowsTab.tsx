import type { WorkflowTemplate } from '../../hooks/useSettings'

type WorkflowsTabProps = {
  workflows: WorkflowTemplate[]
  onRun: (instruction: string) => void
  onChange: (workflows: WorkflowTemplate[]) => void
}

export function WorkflowsTab({ workflows, onRun, onChange }: WorkflowsTabProps) {
  if (workflows.length === 0) {
    return (
      <div className='flex flex-col items-center justify-center py-16 text-center'>
        <div className='mb-4 rounded-full border border-[#2a2a2a] bg-[#111] p-4'>
          <svg className='h-8 w-8 text-zinc-500' fill='none' stroke='currentColor' viewBox='0 0 24 24'>
            <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={1.5} d='M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' />
          </svg>
        </div>
        <h3 className='mb-1 text-sm font-medium text-zinc-200'>No workflow templates yet</h3>
        <p className='max-w-xs text-xs text-zinc-500'>
          Run a task from the dashboard and click "Save as Workflow" in the action log to create your first template.
        </p>
      </div>
    )
  }

  return (
    <div className='grid gap-3 sm:grid-cols-2'>
      {workflows.map((workflow) => (
        <article key={workflow.id} className='rounded border border-[#2a2a2a] bg-[#111] p-3'>
          <input
            value={workflow.name}
            onChange={(event) => onChange(workflows.map((item) => (item.id === workflow.id ? { ...item, name: event.target.value } : item)))}
            className='mb-2 w-full rounded border border-[#2a2a2a] bg-[#0a0a0a] px-2 py-1 text-sm'
          />
          <p className='text-xs text-zinc-400'>{workflow.instruction}</p>
          <p className='mt-2 text-[11px] text-zinc-500'>{workflow.stepCount} steps · {workflow.lastRunAt}</p>
          <div className='mt-2 flex gap-2 text-xs'>
            <button type='button' onClick={() => onRun(workflow.instruction)} className='rounded border border-[#2a2a2a] px-2 py-1'>Run</button>
            <button
              type='button'
              onClick={() => {
                const edited = prompt('Edit instruction', workflow.instruction)
                if (edited === null) return
                onChange(workflows.map((item) => (item.id === workflow.id ? { ...item, instruction: edited } : item)))
              }}
              className='rounded border border-[#2a2a2a] px-2 py-1'
            >
              Edit
            </button>
            <button type='button' onClick={() => onChange(workflows.filter((item) => item.id !== workflow.id))} className='rounded border border-red-500/40 px-2 py-1 text-red-300'>Delete</button>
          </div>
        </article>
      ))}
    </div>
  )
}
