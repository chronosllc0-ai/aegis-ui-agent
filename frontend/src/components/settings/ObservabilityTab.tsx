import { useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../../lib/api'
import { HeaderBar, PanelCard, StatusBadge } from '../ui/DesignSystem'

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

type RuntimeEvent = {
  id: string
  ts: number
  created_at: string
  category: string
  subsystem: string
  level: string
  message: string
  session_id: string | null
  request_id: string | null
  task_id: string | null
  details: Record<string, unknown>
}

type RuntimeEventResponse = {
  events: RuntimeEvent[]
  pagination: {
    cursor: number
    next_cursor: number | null
    limit: number
    total: number
    has_more: boolean
  }
  retention: {
    ttl_seconds: number
    max_events: number
  }
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <PanelCard className='p-3'>
      <p className='text-[11px] text-zinc-500'>{label}</p>
      <p className='mt-1 text-lg font-semibold text-zinc-100'>{value}</p>
    </PanelCard>
  )
}

export function ObservabilityTab() {
  const [tasks, setTasks] = useState<AgentTask[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, AgentTaskDetail>>({})

  const [eventsLoading, setEventsLoading] = useState(false)
  const [events, setEvents] = useState<RuntimeEvent[]>([])
  const [eventsPagination, setEventsPagination] = useState<RuntimeEventResponse['pagination'] | null>(null)
  const [retention, setRetention] = useState<RuntimeEventResponse['retention'] | null>(null)
  const [sessionFilter, setSessionFilter] = useState('')
  const [subsystemFilter, setSubsystemFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [platformFilter, setPlatformFilter] = useState('')
  const [integrationFilter, setIntegrationFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

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

  const loadEvents = async (cursor = 0) => {
    setEventsLoading(true)
    try {
      const query = new URLSearchParams({ limit: '50', cursor: String(cursor) })
      const trimmedSession = sessionFilter.trim()
      const trimmedSubsystem = subsystemFilter.trim().toLowerCase()
      const trimmedLevel = levelFilter.trim().toLowerCase()
      if (trimmedSession) query.set('session_id', trimmedSession)
      if (trimmedSubsystem) query.set('subsystem', trimmedSubsystem)
      if (trimmedLevel) query.set('level', trimmedLevel)
      if (platformFilter.trim()) query.set('platform', platformFilter.trim().toLowerCase())
      if (integrationFilter.trim()) query.set('integration', integrationFilter.trim())
      if (userFilter.trim()) query.set('user', userFilter.trim())
      if (statusFilter.trim()) query.set('status', statusFilter.trim().toLowerCase())
      const response = await fetch(apiUrl(`/api/observability/events?${query.toString()}`), { credentials: 'include' })
      if (!response.ok) throw new Error(`Failed to load event log (${response.status})`)
      const data = await response.json() as RuntimeEventResponse
      setEvents(data.events ?? [])
      setEventsPagination(data.pagination ?? null)
      setRetention(data.retention ?? null)
    } catch (err) {
      console.error('Failed to load event log:', err)
      setEvents([])
      setEventsPagination(null)
    } finally {
      setEventsLoading(false)
    }
  }

  useEffect(() => {
    void loadEvents(0)
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

  const eventSubsystems = useMemo(() => {
    return Array.from(new Set(events.map((event) => event.subsystem).filter(Boolean))).sort()
  }, [events])

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
    <div className='page-sections'>
      <HeaderBar
        left={(
          <div>
            <h3 className='text-base font-semibold text-white'>Observability</h3>
            <p className='text-xs text-zinc-400'>Per-user runtime telemetry for agent tasks, tool calls, and failure reasons.</p>
          </div>
        )}
      />

      <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-4'>
        <Stat label='Total tasks' value={tasks.length} />
        <Stat label='Completed' value={stats.byStatus.completed ?? 0} />
        <Stat label='Failed' value={stats.byStatus.failed ?? 0} />
        <Stat label='Credits used' value={stats.totalCredits.toLocaleString()} />
      </div>

      <PanelCard className='p-3'>
        <div className='mb-3 flex flex-wrap items-end gap-2'>
          <div className='min-w-[180px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Session ID</label>
            <input value={sessionFilter} onChange={(e) => setSessionFilter(e.target.value)} placeholder='agent:main:main' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
          </div>
          <div className='min-w-[140px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Subsystem</label>
            <input list='observability-subsystems' value={subsystemFilter} onChange={(e) => setSubsystemFilter(e.target.value)} placeholder='runtime' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
            <datalist id='observability-subsystems'>
              {eventSubsystems.map((subsystem) => <option key={subsystem} value={subsystem} />)}
            </datalist>
          </div>
          <div className='min-w-[120px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Severity</label>
            <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)} className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200'>
              <option value=''>All</option>
              <option value='debug'>debug</option>
              <option value='info'>info</option>
              <option value='warning'>warning</option>
              <option value='error'>error</option>
            </select>
          </div>
          <div className='min-w-[120px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Platform</label>
            <input value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)} placeholder='telegram' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
          </div>
          <div className='min-w-[160px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Integration</label>
            <input value={integrationFilter} onChange={(e) => setIntegrationFilter(e.target.value)} placeholder='integration-id' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
          </div>
          <div className='min-w-[140px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>User</label>
            <input value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder='user or external user id' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
          </div>
          <div className='min-w-[140px]'>
            <label className='mb-1 block text-[11px] text-zinc-400'>Status</label>
            <input value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} placeholder='approved / blocked / denied' className='w-full rounded border border-zinc-700 bg-[#0d0d0d] px-2 py-1.5 text-xs text-zinc-200' />
          </div>
          <button type='button' onClick={() => void loadEvents(0)} className='min-h-11 rounded border border-zinc-600 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800'>Apply filters</button>
          <button type='button' onClick={() => { setSessionFilter(''); setSubsystemFilter(''); setLevelFilter(''); setPlatformFilter(''); setIntegrationFilter(''); setUserFilter(''); setStatusFilter(''); void loadEvents(0) }} className='min-h-11 rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800'>Reset</button>
        </div>

        <div className='mb-2 flex items-center justify-between text-[11px] text-zinc-500'>
          <span>Event Log</span>
          <span>
            {retention ? `TTL ${Math.floor(retention.ttl_seconds / 3600)}h · cap ${retention.max_events}` : 'Retention unavailable'}
            {sessionFilter.trim() ? ' · scoped by session' : ''}
          </span>
        </div>

        {eventsLoading ? (
          <p className='text-xs text-zinc-500'>Loading event log...</p>
        ) : (
          <>
            <div className='max-h-72 space-y-1 overflow-y-auto pr-1'>
              {events.map((event) => (
                <div key={event.id} className='rounded border border-zinc-800 bg-[#0d0d0d] px-2 py-2 text-[11px]'>
                  <div className='flex flex-wrap items-center justify-between gap-2'>
                    <div className='flex items-center gap-1.5'>
                      <StatusBadge label={event.level} tone={event.level === 'error' ? 'danger' : event.level === 'warning' ? 'warning' : event.level === 'info' ? 'info' : 'default'} />
                      <span className='text-zinc-400'>{event.subsystem}</span>
                      <span className='text-zinc-600'>/</span>
                      <span className='text-zinc-500'>{event.category}</span>
                    </div>
                    <span className='text-zinc-500'>{new Date(event.created_at).toLocaleTimeString()}</span>
                  </div>
                  <p className='mt-1 text-zinc-200'>{event.message}</p>
                  <p className='mt-1 text-zinc-500'>session_id={event.session_id ?? 'n/a'} · request_id={event.request_id ?? 'n/a'} · task_id={event.task_id ?? 'n/a'}</p>
                </div>
              ))}
              {!events.length && <p className='text-xs text-zinc-500'>No matching internal events.</p>}
            </div>
            <div className='mt-2 flex items-center justify-between text-[11px]'>
              <span className='text-zinc-500'>Showing {events.length} of {eventsPagination?.total ?? 0}</span>
              <div className='flex gap-2'>
                <button
                  type='button'
                  disabled={!eventsPagination || eventsPagination.cursor <= 0}
                  onClick={() => {
                    if (!eventsPagination) return
                    const previousCursor = Math.max(0, eventsPagination.cursor - eventsPagination.limit)
                    void loadEvents(previousCursor)
                  }}
                  className='rounded border border-zinc-700 px-2 py-1 text-zinc-300 disabled:cursor-not-allowed disabled:opacity-50'
                >
                  Prev
                </button>
                <button
                  type='button'
                  disabled={!eventsPagination?.has_more || eventsPagination.next_cursor === null}
                  onClick={() => {
                    if (eventsPagination?.next_cursor === null || eventsPagination?.next_cursor === undefined) return
                    void loadEvents(eventsPagination.next_cursor)
                  }}
                  className='rounded border border-zinc-700 px-2 py-1 text-zinc-300 disabled:cursor-not-allowed disabled:opacity-50'
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </PanelCard>

      {loading ? (
        <p className='text-xs text-zinc-500'>Loading telemetry...</p>
      ) : (
        <div className='space-y-2'>
          {tasks.map((task) => {
            const detail = details[task.id]
            const expanded = expandedTaskId === task.id
            return (
              <PanelCard key={task.id} className='p-3'>
                <button
                  type='button'
                  className='w-full min-h-11 text-left'
                  onClick={() => {
                    const next = expanded ? null : task.id
                    setExpandedTaskId(next)
                    if (next) void loadTaskDetails(next)
                  }}
                >
                  <div className='flex items-center justify-between gap-2'>
                    <p className='truncate text-sm font-medium text-zinc-200'>{task.instruction}</p>
                    <StatusBadge label={task.status} tone={task.status === 'failed' ? 'danger' : task.status === 'completed' ? 'success' : 'default'} />
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
              </PanelCard>
            )
          })}
          {!tasks.length && <p className='text-xs text-zinc-500'>No agent activity yet.</p>}
        </div>
      )}
    </div>
  )
}
