import type { WorkflowTemplate } from '../../hooks/useSettings'

type WorkflowsTabProps = {
  workflows: WorkflowTemplate[]
  onRun: (instruction: string) => void
  onChange: (workflows: WorkflowTemplate[]) => void
}

export function WorkflowsTab({ workflows, onRun, onChange }: WorkflowsTabProps) {
  const duplicate = (workflow: WorkflowTemplate) => {
    onChange([
      {
        ...workflow,
        id: crypto.randomUUID(),
        name: `${workflow.name} (Copy)`,
        lastRunAt: new Date().toISOString(),
      },
      ...workflows,
    ])
  }

  return (
    <div className='mx-auto max-w-5xl space-y-5'>
      <header>
        <h3 className='text-lg font-semibold'>Workflow Templates</h3>
        <p className='text-sm text-zinc-400'>Reusable automations that can be run, edited, duplicated, and pinned.</p>
      </header>

      <div className='grid gap-3 lg:grid-cols-2'>
        {workflows.map((workflow) => (
          <article key={workflow.id} className='rounded-2xl border border-[#2a2a2a] bg-[#111] p-4'>
            <div className='mb-2 flex items-start justify-between gap-3'>
              <input
                value={workflow.name}
                onChange={(event) => onChange(workflows.map((item) => (item.id === workflow.id ? { ...item, name: event.target.value } : item)))}
                className='w-full rounded-md border border-[#2a2a2a] bg-[#0a0a0a] px-2 py-1 text-sm'
              />
              <button
                type='button'
                onClick={() => onChange(workflows.map((item) => (item.id === workflow.id ? { ...item, favorite: !item.favorite } : item)))}
                className={`rounded-md border px-2 py-1 text-xs ${workflow.favorite ? 'border-amber-500/40 text-amber-300' : 'border-[#2a2a2a]'}`}
              >
                {workflow.favorite ? '★' : '☆'}
              </button>
            </div>

            <p className='text-xs text-zinc-400'>{workflow.description}</p>
            <p className='mt-2 text-[11px] text-zinc-500'>{workflow.stepCount} steps · Last run {workflow.lastRunAt}</p>

            <div className='mt-2 flex flex-wrap gap-1'>
              {workflow.tags.map((tag) => (
                <span key={tag} className='rounded-full border border-[#2a2a2a] px-2 py-0.5 text-[10px] text-zinc-400'>#{tag}</span>
              ))}
            </div>
            <p className='mt-2 text-[11px] text-zinc-500'>Uses: {workflow.usesIntegrations.join(', ') || 'None'}</p>

            <div className='mt-3 flex flex-wrap gap-2 text-xs'>
              <button type='button' onClick={() => onRun(workflow.instruction)} className='rounded-md border border-[#2a2a2a] px-2 py-1'>Run</button>
              <button
                type='button'
                onClick={() => {
                  const edited = prompt('Edit instruction', workflow.instruction)
                  if (edited === null) return
                  onChange(workflows.map((item) => (item.id === workflow.id ? { ...item, instruction: edited } : item)))
                }}
                className='rounded-md border border-[#2a2a2a] px-2 py-1'
              >
                Edit
              </button>
              <button type='button' onClick={() => duplicate(workflow)} className='rounded-md border border-[#2a2a2a] px-2 py-1'>Duplicate</button>
              <button type='button' onClick={() => onChange(workflows.filter((item) => item.id !== workflow.id))} className='rounded-md border border-red-500/40 px-2 py-1 text-red-300'>Delete</button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
