import type { WorkflowTemplate } from '../../hooks/useSettings'

type WorkflowsTabProps = {
  workflows: WorkflowTemplate[]
  onRun: (instruction: string) => void
  onChange: (workflows: WorkflowTemplate[]) => void
}

export function WorkflowsTab({ workflows, onRun, onChange }: WorkflowsTabProps) {
  return (
    <div className='grid gap-3 md:grid-cols-2'>
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
            <button type='button' onClick={() => onRun(prompt('Edit instruction', workflow.instruction) ?? workflow.instruction)} className='rounded border border-[#2a2a2a] px-2 py-1'>Edit</button>
            <button type='button' onClick={() => onChange(workflows.filter((item) => item.id !== workflow.id))} className='rounded border border-red-500/40 px-2 py-1 text-red-300'>Delete</button>
          </div>
        </article>
      ))}
    </div>
  )
}
