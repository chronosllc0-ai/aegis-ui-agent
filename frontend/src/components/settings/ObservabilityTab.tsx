import { useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../../lib/api'

type AgentTask = {
  id: string
  instruction: string
  status: string
  provider: string | null
  model: string | null
  credits_used: number
  created_at: string | null
}

type AgentTaskDetail = {
  id: string
  error_message: string | null
  actions: Array<{ id: string; action_type: string; description: string | null; duration_ms: number | null }>
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
      <p className='text-[11px] text-zinc-500'>{label}</p>
      <p className='mt-1 text-lg font-semibold text-zinc-100'>{value}</p>
    </div>
  )
}

export function ObservabilityTab() {
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, AgentTaskDetail>>({})

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const response = await fetch(apiUrl('/api/agents/tasks?limit=50'), { credentials: 'include' })
        if (!response.ok) throw new Error(`Failed to load task telemetry (${response.status})`)
        const data = await response.json() as { tasks?: AgentTask[] }
        if (!cancelled) setTasks(data.tasks ?? [])
      } catch (err) {
        console.error('Failed to load task telemetry:', err)
        if (!cancelled) setTasks([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  const stats = useMemo(() => {
    const byStatus: Record<string, number> = {}
    let totalCredits = 0
    for (const t of tasks) {
      byStatus[t.status] = (byStatus[t.status] ?? 0) + 1
      totalCredits += Number(t.credits_used ?? 0)
    }
    return { byStatus, totalCredits }
  }, [tasks])

  const loadTaskDetails = async (taskId: string) => {
    if (details[taskId]) return
    try {
      const response = await fetch(apiUrl(`/api/agents/tasks/${taskId}`), { credentials: 'include' })
      if (!response.ok) throw new Error('Failed')
      const data = await response.json() as AgentTaskDetail
      setDetails((prev) => ({ ...prev, [taskId]: data }))
    } catch {
      setDetails((prev) => ({ ...prev, [taskId]: { id: taskId, error_message: 'Unable to load details.', actions: [] } }))
    }
  }

  return (
    <div className='space-y-4'>
      <div>
        <h3 className='text-base font-semibold text-white'>Observability</h3>
        <p className='text-xs text-zinc-400'>Per-user runtime telemetry for agent tasks, tool calls, and failure reasons.</p>
      </div>

      <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>
        <Stat label='Total tasks' value={tasks.length} />
        <Stat label='Completed' value={stats.byStatus.completed ?? 0} />
        <Stat label='Failed' value={stats.byStatus.failed ?? 0} />
        <Stat label='Credits used' value={stats.totalCredits.toLocaleString()} />
      </div>

      {loading ? (
        <p className='text-xs text-zinc-500'>Loading telemetry...</p>
      ) : (
        <div className='space-y-2'>
          {tasks.map((task) => {
            const detail = details[task.id]
            const expanded = expandedTaskId === task.id
            return (
              <div key={task.id} className='rounded-lg border border-[#2a2a2a] bg-[#111] p-3'>
                <button
                  type='button'
                  className='w-full text-left'
                  onClick={() => {
                    const next = expanded ? null : task.id
                    setExpandedTaskId(next)
                    if (next) void loadTaskDetails(next)
                  }}
                >
                  <div className='flex items-center justify-between gap-2'>
                    <p className='truncate text-sm font-medium text-zinc-200'>{task.instruction}</p>
                    <span className='rounded border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400'>{task.status}</span>
                  </div>
                  <p className='mt-1 text-[11px] text-zinc-500'>{task.provider ?? 'n/a'} · {task.model ?? 'n/a'} · {task.created_at ? new Date(task.created_at).toLocaleString() : 'n/a'}</p>
                </button>
                {expanded && detail && (
                  <div className='mt-3 space-y-2 border-t border-zinc-800 pt-3'>
                    {detail.error_message && <p className='text-xs text-red-300'>Error reason: {detail.error_message}</p>}
                    <p className='text-xs text-zinc-400'>Tool/action calls: {detail.actions.length}</p>
                    <div className='max-h-44 space-y-1 overflow-y-auto pr-1'>
                      {detail.actions.map((action) => (
                        <div key={action.id} className='rounded border border-zinc-800 px-2 py-1.5 text-[11px] text-zinc-300'>
                          <p className='font-medium'>{action.action_type}</p>
                          {action.description && <p className='text-zinc-500'>{action.description}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          {!tasks.length && <p className='text-xs text-zinc-500'>No agent activity yet.</p>}
        </div>
      )}
    </div>
  )
}
