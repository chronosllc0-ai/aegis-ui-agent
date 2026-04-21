import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../lib/api'
import { useSettingsContext } from '../context/useSettingsContext'

type TaskStatus = 'pending' | 'running' | 'success' | 'failed'

interface ScheduledTask {
  id: string
  name: string
  description?: string
  prompt: string
  cron_expr: string
  timezone: string
  session_scope?: 'main' | 'isolated'
  wake_mode?: 'now' | 'next-heartbeat' | 'scheduled'
  delivery_channel?: string
  enabled: boolean
  last_run_at?: string
  next_run_at?: string
  last_status: TaskStatus
  last_run_status?: TaskStatus
  last_error?: string
  run_count: number
  created_at: string
}

interface TaskRun {
  taskId: string
  taskName: string
  started_at?: string
  finished_at?: string
  status: TaskStatus
  error?: string | null
  session_scope?: 'main' | 'isolated'
  wake_mode?: string
  delivery_channel?: string
  last_run_status?: TaskStatus
  last_run_at?: string
  next_run_at?: string
  reflection_candidate?: boolean
}

interface TaskMutationPayload {
  name: string
  description: string
  execution_mode: 'run_assistant_prompt' | 'run_saved_workflow'
  assistant_task_prompt?: string
  workflow_id?: string
  workflow_version?: string
  cron_expr: string
  timezone: string
  enabled: boolean
}

interface TaskApiPayload {
  name: string
  description: string
  prompt: string
  cron_expr: string
  timezone: string
  session_scope: 'main' | 'isolated'
  wake_mode: 'now' | 'next-heartbeat' | 'scheduled'
  delivery_channel: string
}

const PRESETS: { label: string; value: string }[] = [
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every day at 9 am', value: '0 9 * * *' },
  { label: 'Every Monday at 9 am', value: '0 9 * * 1' },
  { label: 'Every weekday at 9 am', value: '0 9 * * 1-5' },
  { label: 'Every Sunday at midnight', value: '0 0 * * 0' },
  { label: 'Custom', value: '__custom__' },
]

const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Vancouver',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Amsterdam',
  'Europe/Stockholm',
  'Europe/Moscow',
  'Africa/Algiers',
  'Africa/Cairo',
  'Africa/Johannesburg',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Dhaka',
  'Asia/Bangkok',
  'Asia/Singapore',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Australia/Sydney',
  'Australia/Melbourne',
  'Pacific/Auckland',
  'Pacific/Honolulu',
]

function humanizeCron(expr: string): string {
  const match = PRESETS.find((preset) => preset.value === expr)
  if (match && match.value !== '__custom__') return match.label

  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr
  const [minute, hour, dayOfMonth, , dayOfWeek] = parts
  const hourNum = parseInt(hour, 10)
  const minNum = parseInt(minute, 10)
  const pad = (value: number) => String(value).padStart(2, '0')
  const time = !Number.isNaN(hourNum) && !Number.isNaN(minNum) ? `${pad(hourNum)}:${pad(minNum)}` : null
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  if (dayOfWeek === '*' && dayOfMonth === '*') return time ? `Every day at ${time}` : 'Every day'
  if (dayOfWeek === '1-5' && time) return `Weekdays at ${time}`
  if (!dayOfWeek.includes('-') && !dayOfWeek.includes(',')) {
    const day = parseInt(dayOfWeek, 10)
    if (!Number.isNaN(day) && day >= 0 && day <= 6) {
      return time ? `Every ${days[day]} at ${time}` : `Every ${days[day]}`
    }
  }
  return expr
}

function relativeTime(isoStr?: string): string {
  if (!isoStr) return '-'
  const date = new Date(isoStr)
  const diffMs = date.getTime() - Date.now()
  const absMs = Math.abs(diffMs)
  const past = diffMs < 0
  if (absMs < 60_000) return past ? 'just now' : 'in a few seconds'
  const mins = Math.round(absMs / 60_000)
  if (mins < 60) return past ? `${mins}m ago` : `in ${mins}m`
  const hours = Math.round(absMs / 3_600_000)
  if (hours < 24) return past ? `${hours}h ago` : `in ${hours}h`
  const days = Math.round(absMs / 86_400_000)
  return past ? `${days}d ago` : `in ${days}d`
}

function formatDateTime(value?: string): string {
  if (!value) return 'n/a'
  return new Date(value).toLocaleString()
}

function StatusBadge({ status }: { status: TaskStatus }) {
  const map: Record<TaskStatus, { cls: string; label: string }> = {
    pending: { cls: 'bg-zinc-700 text-zinc-300', label: 'Pending' },
    running: { cls: 'bg-yellow-500/20 text-yellow-300', label: 'Running' },
    success: { cls: 'bg-emerald-500/20 text-emerald-300', label: 'Success' },
    failed: { cls: 'bg-red-500/20 text-red-300', label: 'Failed' },
  }
  const { cls, label } = map[status] ?? map.pending
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>
}

function SectionShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className='rounded-xl border border-[#232734] bg-[#111827]/65 p-4 sm:p-5'>
      <h4 className='text-sm font-semibold text-zinc-100'>{title}</h4>
      <p className='mt-1 text-xs text-zinc-400'>{description}</p>
      <div className='mt-3.5 space-y-3'>{children}</div>
    </section>
  )
}

function FieldLabel({ label, required = false }: { label: string; required?: boolean }) {
  return (
    <label className='mb-1 block text-xs text-zinc-300'>
      {label}
      {required && <span className='ml-1 text-rose-400'>*</span>}
    </label>
  )
}

function AutomationWizard({
  initial,
  saving,
  lastExecutionMode,
  onLastExecutionModeChange,
  onSubmit,
  onCancelEdit,
}: {
  initial?: ScheduledTask
  saving: boolean
  lastExecutionMode: 'run_assistant_prompt' | 'run_saved_workflow'
  onLastExecutionModeChange: (mode: 'run_assistant_prompt' | 'run_saved_workflow') => void
  onSubmit: (data: TaskMutationPayload) => Promise<void>
  onCancelEdit: () => void
}) {
  const { settings } = useSettingsContext()
  const workflows = settings.workflowTemplates ?? []

  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [prompt, setPrompt] = useState(initial?.prompt ?? '')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [executionMode, setExecutionMode] = useState<'run_assistant_prompt' | 'run_saved_workflow'>(lastExecutionMode)
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('')
  const [workflowVersionPin, setWorkflowVersionPin] = useState('')
  const [preset, setPreset] = useState(() => {
    if (!initial?.cron_expr) return PRESETS[1].value
    const found = PRESETS.find((p) => p.value === initial.cron_expr)
    return found ? found.value : '__custom__'
  })
  const [customCron, setCustomCron] = useState(initial?.cron_expr ?? '')
  const [timezone, setTimezone] = useState(initial?.timezone ?? 'UTC')
  const [tzSearch, setTzSearch] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setName(initial?.name ?? '')
    setDescription(initial?.description ?? '')
    setPrompt(initial?.prompt ?? '')
    setEnabled(initial?.enabled ?? true)
    setPreset(() => {
      if (!initial?.cron_expr) return PRESETS[1].value
      const found = PRESETS.find((p) => p.value === initial.cron_expr)
      return found ? found.value : '__custom__'
    })
    setCustomCron(initial?.cron_expr ?? '')
    setTimezone(initial?.timezone ?? 'UTC')
    if (!initial) {
      setExecutionMode(lastExecutionMode)
      setSelectedWorkflowId('')
    } else {
      const matchedWorkflow = workflows.find((workflow) => workflow.instruction === initial.prompt)
      if (matchedWorkflow) {
        setExecutionMode('run_saved_workflow')
        setSelectedWorkflowId(matchedWorkflow.id)
      } else {
        setExecutionMode('run_assistant_prompt')
        setSelectedWorkflowId('')
      }
    }
    setWorkflowVersionPin('')
    setError(null)
  }, [initial, lastExecutionMode, workflows])

  const cronExpr = preset === '__custom__' ? customCron : preset

  const filteredTimezones = useMemo(
    () => COMMON_TIMEZONES.filter((tz) => tz.toLowerCase().includes(tzSearch.toLowerCase())),
    [tzSearch],
  )

  const handleWorkflowSelect = (workflowId: string) => {
    setSelectedWorkflowId(workflowId)
    const workflow = workflows.find((wf) => wf.id === workflowId)
    if (workflow) {
      if (!name.trim()) setName(workflow.name)
      setPrompt(workflow.instruction)
    }
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Name is required')
      return
    }
    if (executionMode === 'run_assistant_prompt' && !prompt.trim()) {
      setError('Assistant task prompt is required')
      return
    }
    if (executionMode === 'run_saved_workflow' && !selectedWorkflowId) {
      setError('Please select a workflow')
      return
    }
    if (!cronExpr.trim()) {
      setError('Schedule is required')
      return
    }

    if (executionMode === 'run_saved_workflow') {
      const workflow = workflows.find((wf) => wf.id === selectedWorkflowId)
      if (!workflow) {
        setError('Selected workflow no longer exists. Please pick another workflow.')
        return
      }
      if (!workflow.instruction.trim()) {
        setError('Selected workflow has an empty instruction. Please update the workflow or choose another one.')
        return
      }
    }

    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim(),
        execution_mode: executionMode,
        assistant_task_prompt: executionMode === 'run_assistant_prompt' ? prompt.trim() : undefined,
        workflow_id: executionMode === 'run_saved_workflow' ? selectedWorkflowId : undefined,
        workflow_version: executionMode === 'run_saved_workflow' && workflowVersionPin.trim() ? workflowVersionPin.trim() : undefined,
        cron_expr: cronExpr.trim(),
        timezone,
        enabled,
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save automation job')
      return
    }

    if (!initial?.id) {
      setName('')
      setDescription('')
      setPrompt('')
      setPreset(PRESETS[1].value)
      setCustomCron('')
      setTimezone('UTC')
      setTzSearch('')
      setEnabled(true)
      setAdvancedOpen(false)
      setSelectedWorkflowId('')
      setWorkflowVersionPin('')
    }
  }

  return (
    <section className='rounded-2xl border border-[#273044] bg-[#0e1422] p-4 sm:p-5'>
      <div className='mb-4'>
        <h3 className='text-base font-semibold text-zinc-100'>{initial?.id ? 'Edit job' : 'New Job'}</h3>
        <p className='mt-1 text-xs text-zinc-400'>Create a scheduled wakeup or agent run.</p>
        <p className='mt-1 text-xs text-zinc-500'>Required fields are marked with an asterisk.</p>
      </div>

      {error && <div className='mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300'>{error}</div>}

      <form onSubmit={handleSubmit} className='space-y-4'>
        <SectionShell title='Basics' description='Name it, choose the assistant input, and set enabled state.'>
          <div>
            <FieldLabel label='Name' required />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
              placeholder='Morning brief'
            />
          </div>
          <div>
            <FieldLabel label='Description' />
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
              placeholder='Optional context for this job'
            />
          </div>
          <label className='flex min-h-11 items-center gap-2 text-sm text-zinc-200'>
            <input
              type='checkbox'
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
              className='h-4 w-4 rounded border-[#38445f] bg-[#0b1220]'
            />
            Enabled
          </label>
        </SectionShell>

        <SectionShell title='Schedule' description='Control when this job runs.'>
          <div>
            <FieldLabel label='Schedule preset' required />
            <select
              value={preset}
              onChange={(event) => setPreset(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              {PRESETS.map((presetItem) => (
                <option key={presetItem.value} value={presetItem.value}>
                  {presetItem.label}
                </option>
              ))}
            </select>
          </div>
          {preset === '__custom__' && (
            <div>
              <FieldLabel label='Cron expression' required />
              <input
                value={customCron}
                onChange={(event) => setCustomCron(event.target.value)}
                className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                placeholder='0 9 * * 1'
              />
            </div>
          )}
          <p className='text-xs text-zinc-500'>Preview: {humanizeCron(cronExpr)}</p>
        </SectionShell>

        <SectionShell title='Execution' description='Choose what is executed when the wake event fires.'>
          <div>
            <FieldLabel label='What should run?' required />
            <select
              value={executionMode}
              onChange={(event) => {
                const selectedMode = event.target.value as 'run_assistant_prompt' | 'run_saved_workflow'
                setExecutionMode(selectedMode)
                onLastExecutionModeChange(selectedMode)
              }}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='run_assistant_prompt'>Assistant prompt</option>
              <option value='run_saved_workflow'>Saved workflow</option>
            </select>
          </div>
          {executionMode === 'run_assistant_prompt' ? (
            <div>
              <FieldLabel label='Assistant task prompt' required />
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={5}
                className='min-h-32 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
              />
            </div>
          ) : (
            <>
              <div>
                <FieldLabel label='Workflow' required />
                <select
                  value={selectedWorkflowId}
                  onChange={(event) => handleWorkflowSelect(event.target.value)}
                  className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                >
                  <option value=''>Select workflow</option>
                  {workflows.map((workflow) => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.name}
                    </option>
                  ))}
                </select>
                {workflows.length === 0 && <p className='mt-1 text-xs text-zinc-500'>No saved workflows yet.</p>}
              </div>
              <div>
                <FieldLabel label='Workflow version pin (optional)' />
                <input
                  value={workflowVersionPin}
                  onChange={(event) => setWorkflowVersionPin(event.target.value)}
                  className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                  placeholder='latest, v2, sha, or tag'
                />
              </div>
            </>
          )}
          <p className='text-xs text-zinc-500'>Compatible mapping: both modes still resolve into the backend task prompt payload shape.</p>
        </SectionShell>

        <SectionShell title='Delivery' description='Control where run updates are visible.'>
          <p className='text-xs text-zinc-500'>Runs update task status and appear in run history after execution.</p>
        </SectionShell>

        <details
          open={advancedOpen}
          onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
          className='rounded-xl border border-[#2a334a] bg-[#111827]/55 p-4 sm:p-5'
        >
          <summary className='cursor-pointer text-sm font-semibold text-zinc-100'>Advanced</summary>
          <p className='mt-1 text-xs text-zinc-400'>Timezone controls next wake calculations.</p>
          <div className='mt-3 space-y-3'>
            <div>
              <FieldLabel label='Search timezone' />
              <input
                value={tzSearch}
                onChange={(event) => setTzSearch(event.target.value)}
                className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                placeholder='Type timezone name'
              />
            </div>
            <div>
              <FieldLabel label='Timezone' required />
              <select
                value={timezone}
                onChange={(event) => {
                  setTimezone(event.target.value)
                  setTzSearch('')
                }}
                className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
              >
                {filteredTimezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </details>

        <div className='sticky bottom-0 z-10 -mx-4 border-t border-[#2a334a] bg-[#0e1422]/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:border-none sm:bg-transparent sm:p-0'>
          <div className='flex flex-col gap-2 sm:flex-row sm:justify-end'>
            {initial?.id && (
              <button
                type='button'
                onClick={onCancelEdit}
                className='min-h-11 w-full rounded-lg border border-[#2a334a] px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 sm:w-auto'
              >
                Cancel edit
              </button>
            )}
            <button
              type='submit'
              disabled={saving}
              className='min-h-11 w-full rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-60 sm:w-auto'
            >
              {saving ? 'Saving…' : initial?.id ? 'Save job' : 'Add job'}
            </button>
          </div>
        </div>
      </form>
    </section>
  )
}

export function AutomationsPage() {
  const { settings } = useSettingsContext()
  const workflows = settings.workflowTemplates ?? []
  const [tasks, setTasks] = useState<ScheduledTask[]>([])
  const [runHistoryByTask, setRunHistoryByTask] = useState<Record<string, TaskRun[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [runHistoryLoading, setRunHistoryLoading] = useState(false)
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set())
  const [editingTask, setEditingTask] = useState<ScheduledTask | undefined>(undefined)
  const [lastExecutionMode, setLastExecutionMode] = useState<'run_assistant_prompt' | 'run_saved_workflow'>(() => {
    const storedValue = typeof window !== 'undefined' ? window.localStorage.getItem('aegis.automation.lastExecutionMode') : null
    return storedValue === 'run_saved_workflow' ? 'run_saved_workflow' : 'run_assistant_prompt'
  })

  const [jobSearch, setJobSearch] = useState('')
  const [enabledFilter, setEnabledFilter] = useState<'all' | 'enabled' | 'disabled'>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | TaskStatus>('all')

  const [runScope, setRunScope] = useState<'all' | string>('all')
  const [runStatus, setRunStatus] = useState<'all' | TaskStatus>('all')
  const [runScopeFilter, setRunScopeFilter] = useState<'all' | 'main' | 'isolated'>('all')
  const [runDeliveryFilter, setRunDeliveryFilter] = useState<'all' | string>('all')
  const [runDateFrom, setRunDateFrom] = useState('')
  const [runDateTo, setRunDateTo] = useState('')
  const [runSort, setRunSort] = useState<'started_desc' | 'started_asc' | 'finished_desc' | 'finished_asc'>('started_desc')
  const [runSearch, setRunSearch] = useState('')
  const [runPage, setRunPage] = useState(1)
  const runPageSize = 5

  useEffect(() => {
    window.localStorage.setItem('aegis.automation.lastExecutionMode', lastExecutionMode)
  }, [lastExecutionMode])

  const toTaskApiPayload = useCallback((data: TaskMutationPayload): TaskApiPayload => {
    let prompt = data.assistant_task_prompt ?? ''
    if (data.execution_mode === 'run_saved_workflow') {
      const selectedWorkflow = workflows.find((workflow) => workflow.id === data.workflow_id)
      if (!selectedWorkflow) {
        throw new Error('Selected workflow no longer exists. Please pick another workflow.')
      }
      if (!selectedWorkflow.instruction.trim()) {
        throw new Error('Selected workflow has an empty instruction. Please update the workflow or choose another one.')
      }
      prompt = selectedWorkflow.instruction
    }

    return {
      name: data.name,
      description: data.description,
      prompt,
      cron_expr: data.cron_expr,
      timezone: data.timezone,
      session_scope: 'main',
      wake_mode: 'now',
      delivery_channel: 'chat',
    }
  }, [workflows])

  const loadRunHistoryForTask = useCallback(async (task: ScheduledTask, force = false) => {
    if (!force && runHistoryByTask[task.id]) return
    setRunHistoryLoading(true)
    try {
      const params = new URLSearchParams()
      if (runStatus !== 'all') params.set('status', runStatus)
      if (runScopeFilter !== 'all') params.set('scope', runScopeFilter)
      if (runDeliveryFilter !== 'all') params.set('delivery_channel', runDeliveryFilter)
      if (runDateFrom) params.set('date_from', new Date(runDateFrom).toISOString())
      if (runDateTo) params.set('date_to', new Date(`${runDateTo}T23:59:59.999Z`).toISOString())
      const query = params.toString()
      const response = await fetch(apiUrl(`/api/automation/tasks/${task.id}/runs${query ? `?${query}` : ''}`), { credentials: 'include' })
      if (!response.ok) return
      const body = await response.json()
      const items = Array.isArray(body.runs) ? body.runs : []
      const runs = items.map((entry: Omit<TaskRun, 'taskId' | 'taskName'>) => ({
        ...entry,
        taskId: task.id,
        taskName: task.name,
      }))
      setRunHistoryByTask((previous) => ({ ...previous, [task.id]: runs }))
    } finally {
      setRunHistoryLoading(false)
    }
  }, [runHistoryByTask, runStatus, runScopeFilter, runDeliveryFilter, runDateFrom, runDateTo])

  const fetchTasks = useCallback(async () => {
    try {
      setError(null)
      const response = await fetch(apiUrl('/api/automation/tasks'), { credentials: 'include' })
      if (!response.ok) throw new Error(`Failed to load automations (${response.status})`)
      const body = await response.json()
      const nextTasks: ScheduledTask[] = body.tasks ?? []
      setTasks(nextTasks)
      setRunHistoryByTask((previous) => {
        const validTaskIds = new Set(nextTasks.map((task) => task.id))
        return Object.fromEntries(Object.entries(previous).filter(([taskId]) => validTaskIds.has(taskId)))
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load automations')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks()
  }, [fetchTasks])

  const handleCreate = async (data: TaskMutationPayload) => {
    setSaving(true)
    try {
      const taskApiPayload = toTaskApiPayload(data)
      const response = await fetch(apiUrl('/api/automation/tasks'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(taskApiPayload),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(body?.detail ?? `Error ${response.status}`)
      }
      const createdTaskId = body?.task?.id as string | undefined
      if (createdTaskId && !data.enabled) {
        const toggleResponse = await fetch(apiUrl(`/api/automation/tasks/${createdTaskId}`), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ enabled: false }),
        })
        if (!toggleResponse.ok) {
          const toggleBody = await toggleResponse.json().catch(() => ({}))
          throw new Error(toggleBody?.detail ?? `Error ${toggleResponse.status}`)
        }
      }
      await fetchTasks()
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async (data: TaskMutationPayload) => {
    if (!editingTask) return
    setSaving(true)
    try {
      const taskApiPayload = toTaskApiPayload(data)
      const response = await fetch(apiUrl(`/api/automation/tasks/${editingTask.id}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          ...taskApiPayload,
          enabled: data.enabled,
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body?.detail ?? `Error ${response.status}`)
      }
      setEditingTask(undefined)
      await fetchTasks()
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (task: ScheduledTask, enabled: boolean) => {
    await fetch(apiUrl(`/api/automation/tasks/${task.id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    })
    setTasks((previous) => previous.map((row) => (row.id === task.id ? { ...row, enabled } : row)))
  }

  const handleDelete = async (taskId: string) => {
    if (!window.confirm('Delete this automation job?')) return
    await fetch(apiUrl(`/api/automation/tasks/${taskId}`), {
      method: 'DELETE',
      credentials: 'include',
    })
    await fetchTasks()
  }

  const handleRun = async (taskId: string) => {
    setRunningIds((previous) => new Set(previous).add(taskId))
    try {
      await fetch(apiUrl(`/api/automation/tasks/${taskId}/run`), {
        method: 'POST',
        credentials: 'include',
      })
      setTimeout(() => {
        const ranTask = tasks.find((task) => task.id === taskId)
        if (ranTask) void loadRunHistoryForTask(ranTask, true)
        void fetchTasks()
      }, 1200)
    } finally {
      setRunningIds((previous) => {
        const next = new Set(previous)
        next.delete(taskId)
        return next
      })
    }
  }

  const enabledCount = useMemo(() => tasks.filter((task) => task.enabled).length, [tasks])
  const nextWake = useMemo(() => {
    const next = tasks
      .filter((task) => task.enabled && task.next_run_at)
      .sort((a, b) => new Date(a.next_run_at ?? '').getTime() - new Date(b.next_run_at ?? '').getTime())[0]
    return next?.next_run_at
  }, [tasks])

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchesSearch =
        !jobSearch.trim() ||
        `${task.name} ${task.description ?? ''} ${task.prompt}`.toLowerCase().includes(jobSearch.toLowerCase())
      const matchesEnabled =
        enabledFilter === 'all' ||
        (enabledFilter === 'enabled' ? task.enabled : !task.enabled)
      const effectiveStatus = runningIds.has(task.id) ? 'running' : task.last_status
      const matchesStatus = statusFilter === 'all' || statusFilter === effectiveStatus
      return matchesSearch && matchesEnabled && matchesStatus
    })
  }, [tasks, jobSearch, enabledFilter, statusFilter, runningIds])

  const flattenedRuns = useMemo(() => Object.values(runHistoryByTask).flat(), [runHistoryByTask])

  const scopedRuns = useMemo(() => {
    const filtered = flattenedRuns.filter((run) => {
      const matchesScope = runScope === 'all' || run.taskId === runScope
      const matchesStatus = runStatus === 'all' || run.status === runStatus
      const matchesSessionScope = runScopeFilter === 'all' || run.session_scope === runScopeFilter
      const matchesDelivery = runDeliveryFilter === 'all' || run.delivery_channel === runDeliveryFilter
      const runStarted = run.started_at ? new Date(run.started_at).getTime() : null
      const fromBoundary = runDateFrom ? new Date(runDateFrom).getTime() : null
      const toBoundary = runDateTo ? new Date(`${runDateTo}T23:59:59.999Z`).getTime() : null
      const matchesDateFrom = fromBoundary === null || (runStarted !== null && runStarted >= fromBoundary)
      const matchesDateTo = toBoundary === null || (runStarted !== null && runStarted <= toBoundary)
      const haystack = `${run.taskName} ${run.error ?? ''}`.toLowerCase()
      const matchesSearch = !runSearch.trim() || haystack.includes(runSearch.toLowerCase())
      return matchesScope && matchesStatus && matchesSessionScope && matchesDelivery && matchesDateFrom && matchesDateTo && matchesSearch
    })
    const sorted = [...filtered].sort((a, b) => {
      const aStarted = new Date(a.started_at ?? a.finished_at ?? 0).getTime()
      const bStarted = new Date(b.started_at ?? b.finished_at ?? 0).getTime()
      const aFinished = new Date(a.finished_at ?? a.started_at ?? 0).getTime()
      const bFinished = new Date(b.finished_at ?? b.started_at ?? 0).getTime()
      if (runSort === 'started_asc') return aStarted - bStarted
      if (runSort === 'finished_desc') return bFinished - aFinished
      if (runSort === 'finished_asc') return aFinished - bFinished
      return bStarted - aStarted
    })
    return sorted
  }, [flattenedRuns, runScope, runStatus, runScopeFilter, runDeliveryFilter, runDateFrom, runDateTo, runSearch, runSort])

  const totalPages = Math.max(1, Math.ceil(scopedRuns.length / runPageSize))
  const pagedRuns = scopedRuns.slice((runPage - 1) * runPageSize, runPage * runPageSize)

  useEffect(() => {
    setRunPage(1)
  }, [runScope, runStatus, runScopeFilter, runDeliveryFilter, runDateFrom, runDateTo, runSort, runSearch])

  useEffect(() => {
    if (runScope === 'all') return
    const task = tasks.find((row) => row.id === runScope)
    if (!task) return
    void loadRunHistoryForTask(task)
  }, [runScope, tasks, loadRunHistoryForTask])

  if (loading) {
    return <div className='flex h-full items-center justify-center text-sm text-zinc-400'>Loading automations…</div>
  }

  return (
    <div className='h-full overflow-y-auto bg-[#0a0f1d] p-3 sm:p-5'>
      <div className='space-y-4'>
        <section className='rounded-2xl border border-[#273044] bg-[#0e1422] p-4 sm:p-5'>
          <div className='mb-3 flex items-center justify-between'>
            <h2 className='text-base font-semibold text-zinc-100'>Automations</h2>
            <button
              type='button'
              onClick={() => void fetchTasks()}
              className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 text-xs text-zinc-300 hover:text-zinc-100'
            >
              Refresh
            </button>
          </div>
          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4'>
            <div className='rounded-xl border border-[#2a334a] bg-[#0b1220] p-3'>
              <p className='text-[11px] uppercase tracking-wide text-zinc-500'>Enabled</p>
              <p className='mt-2 text-sm font-semibold text-emerald-300'>{enabledCount}</p>
            </div>
            <div className='rounded-xl border border-[#2a334a] bg-[#0b1220] p-3'>
              <p className='text-[11px] uppercase tracking-wide text-zinc-500'>Jobs count</p>
              <p className='mt-2 text-sm font-semibold text-zinc-100'>{tasks.length}</p>
            </div>
            <div className='rounded-xl border border-[#2a334a] bg-[#0b1220] p-3 sm:col-span-2 lg:col-span-1'>
              <p className='text-[11px] uppercase tracking-wide text-zinc-500'>Next wake</p>
              <p className='mt-2 text-sm font-semibold text-zinc-100'>{formatDateTime(nextWake)}</p>
              <p className='mt-1 text-xs text-zinc-500'>{relativeTime(nextWake)}</p>
            </div>
            <div className='rounded-xl border border-[#2a334a] bg-[#0b1220] p-3'>
              <p className='text-[11px] uppercase tracking-wide text-zinc-500'>Refresh action</p>
              <button
                type='button'
                onClick={() => void fetchTasks()}
                className='mt-2 min-h-11 w-full rounded-lg bg-cyan-600 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-500'
              >
                Reload jobs + history
              </button>
            </div>
          </div>
        </section>

        <AutomationWizard
          initial={editingTask}
          saving={saving}
          lastExecutionMode={lastExecutionMode}
          onLastExecutionModeChange={setLastExecutionMode}
          onSubmit={editingTask ? handleUpdate : handleCreate}
          onCancelEdit={() => setEditingTask(undefined)}
        />

        <section className='rounded-2xl border border-[#273044] bg-[#0e1422] p-4 sm:p-5'>
          <div className='mb-4 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between'>
            <div>
              <h3 className='text-base font-semibold text-zinc-100'>Jobs</h3>
              <p className='text-xs text-zinc-400'>All scheduled jobs stored in the gateway.</p>
            </div>
            <p className='text-xs text-zinc-500'>{filteredTasks.length} shown of {tasks.length}</p>
          </div>

          <div className='grid grid-cols-1 gap-2 md:grid-cols-4'>
            <input
              value={jobSearch}
              onChange={(event) => setJobSearch(event.target.value)}
              placeholder='Search jobs'
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
            <select
              value={enabledFilter}
              onChange={(event) => setEnabledFilter(event.target.value as 'all' | 'enabled' | 'disabled')}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All enabled states</option>
              <option value='enabled'>Enabled</option>
              <option value='disabled'>Disabled</option>
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as 'all' | TaskStatus)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All statuses</option>
              <option value='pending'>Pending</option>
              <option value='running'>Running</option>
              <option value='success'>Success</option>
              <option value='failed'>Failed</option>
            </select>
          </div>

          <div className='mt-4 space-y-3'>
            {filteredTasks.length === 0 && <p className='text-sm text-zinc-500'>No matching jobs.</p>}
            {filteredTasks.map((task) => {
              const effectiveStatus: TaskStatus = runningIds.has(task.id) ? 'running' : task.last_status
              return (
                <article key={task.id} className='rounded-xl border border-[#2a334a] bg-[#0b1220] p-3 sm:p-4'>
                  <div className='flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between'>
                    <div className='min-w-0'>
                      <div className='flex flex-wrap items-center gap-2'>
                        <h4 className='text-sm font-semibold text-zinc-100'>{task.name}</h4>
                        <StatusBadge status={effectiveStatus} />
                        <span className={`rounded-full px-2 py-0.5 text-[10px] ${task.enabled ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-700 text-zinc-300'}`}>
                          {task.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </div>
                      {task.description && <p className='mt-1 text-xs text-zinc-400'>{task.description}</p>}
                      <p className='mt-2 text-xs text-zinc-500'>{humanizeCron(task.cron_expr)} · {task.timezone}</p>
                      <p className='mt-1 text-xs text-zinc-500'>
                        Next: {formatDateTime(task.next_run_at)} ({relativeTime(task.next_run_at)})
                      </p>
                      <p className='mt-1 text-xs text-zinc-500'>Last run: {formatDateTime(task.last_run_at)} · Runs: {task.run_count}</p>
                    </div>

                    <div className='grid grid-cols-2 gap-2 sm:grid-cols-3 lg:w-[360px]'>
                      <button
                        type='button'
                        onClick={() => setEditingTask(task)}
                        className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 text-sm text-zinc-200 hover:text-zinc-100'
                      >
                        Edit
                      </button>
                      <button
                        type='button'
                        onClick={() => void handleToggle(task, !task.enabled)}
                        className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 text-sm text-zinc-200 hover:text-zinc-100'
                      >
                        {task.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        type='button'
                        onClick={() => void handleRun(task.id)}
                        className='min-h-11 rounded-lg border border-cyan-500/40 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-500/10'
                      >
                        Run now
                      </button>
                      <button
                        type='button'
                        onClick={() => setRunScope(task.id)}
                        className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 text-sm text-zinc-200 hover:text-zinc-100'
                      >
                        View history
                      </button>
                      <button
                        type='button'
                        onClick={() => void handleDelete(task.id)}
                        className='min-h-11 rounded-lg border border-red-500/30 px-3 py-2 text-sm text-red-300 hover:bg-red-500/10'
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        <section className='rounded-2xl border border-[#273044] bg-[#0e1422] p-4 sm:p-5'>
          <div className='mb-4 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between'>
            <div>
              <h3 className='text-base font-semibold text-zinc-100'>Run history</h3>
              <p className='text-xs text-zinc-400'>Latest runs across scheduled jobs.</p>
            </div>
            <p className='text-xs text-zinc-500'>{scopedRuns.length} matching runs</p>
          </div>

          <div className='grid grid-cols-1 gap-2 md:grid-cols-3'>
            <select
              value={runScope}
              onChange={(event) => setRunScope(event.target.value as 'all' | string)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All jobs</option>
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.name}
                </option>
              ))}
            </select>
            <select
              value={runStatus}
              onChange={(event) => setRunStatus(event.target.value as 'all' | TaskStatus)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All statuses</option>
              <option value='pending'>Pending</option>
              <option value='running'>Running</option>
              <option value='success'>Success</option>
              <option value='failed'>Failed</option>
            </select>
            <input
              value={runSearch}
              onChange={(event) => setRunSearch(event.target.value)}
              placeholder='Search error or job'
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
            <select
              value={runScopeFilter}
              onChange={(event) => setRunScopeFilter(event.target.value as 'all' | 'main' | 'isolated')}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All session scopes</option>
              <option value='main'>Main</option>
              <option value='isolated'>Isolated</option>
            </select>
            <select
              value={runDeliveryFilter}
              onChange={(event) => setRunDeliveryFilter(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='all'>All channels</option>
              <option value='chat'>chat</option>
            </select>
            <input
              type='date'
              value={runDateFrom}
              onChange={(event) => setRunDateFrom(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
            <input
              type='date'
              value={runDateTo}
              onChange={(event) => setRunDateTo(event.target.value)}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
            <select
              value={runSort}
              onChange={(event) => setRunSort(event.target.value as 'started_desc' | 'started_asc' | 'finished_desc' | 'finished_asc')}
              className='min-h-11 w-full rounded-lg border border-[#2a334a] bg-[#0b1220] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              <option value='started_desc'>Started (newest)</option>
              <option value='started_asc'>Started (oldest)</option>
              <option value='finished_desc'>Finished (newest)</option>
              <option value='finished_asc'>Finished (oldest)</option>
            </select>
          </div>

          <div className='mt-4 space-y-2'>
            {runHistoryLoading && <p className='text-sm text-zinc-500'>Loading run history…</p>}
            {!runHistoryLoading && runScope === 'all' && flattenedRuns.length === 0 && (
              <p className='text-sm text-zinc-500'>Select a job scope to load detailed run history.</p>
            )}
            {!runHistoryLoading && !(runScope === 'all' && flattenedRuns.length === 0) && pagedRuns.length === 0 && (
              <p className='text-sm text-zinc-500'>No matching runs.</p>
            )}
            {pagedRuns.map((run, index) => (
              <article key={`${run.taskId}-${run.started_at ?? run.finished_at}-${index}`} className='rounded-lg border border-[#2a334a] bg-[#0b1220] p-3'>
                <div className='flex flex-wrap items-center justify-between gap-2'>
                  <p className='text-sm font-medium text-zinc-100'>{run.taskName}</p>
                  <StatusBadge status={run.status} />
                </div>
                <p className='mt-1 text-xs text-zinc-500'>Started: {formatDateTime(run.started_at)}</p>
                <p className='mt-1 text-xs text-zinc-500'>Finished: {formatDateTime(run.finished_at)}</p>
                <p className='mt-1 text-xs text-zinc-500'>Scope: {run.session_scope ?? 'main'} · Delivery: {run.delivery_channel ?? 'chat'} · Wake: {run.wake_mode ?? 'now'}</p>
                <p className='mt-1 text-xs text-zinc-500'>Last run status: {run.last_run_status ?? run.status} · Last run at: {formatDateTime(run.last_run_at)} · Next run at: {formatDateTime(run.next_run_at)}</p>
                {run.reflection_candidate && (
                  <p className='mt-1 inline-flex rounded-full bg-violet-500/20 px-2 py-0.5 text-[11px] text-violet-200'>reflection_candidate</p>
                )}
                {run.error && <p className='mt-1 text-xs text-red-300'>Error: {run.error}</p>}
              </article>
            ))}
          </div>

          <div className='mt-4 flex items-center justify-between border-t border-[#2a334a] pt-3 text-xs text-zinc-400'>
            <p>Page {runPage} of {totalPages}</p>
            <div className='flex gap-2'>
              <button
                type='button'
                disabled={runPage <= 1}
                onClick={() => setRunPage((page) => Math.max(1, page - 1))}
                className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 disabled:opacity-50'
              >
                Previous
              </button>
              <button
                type='button'
                disabled={runPage >= totalPages}
                onClick={() => setRunPage((page) => Math.min(totalPages, page + 1))}
                className='min-h-11 rounded-lg border border-[#2a334a] px-3 py-2 disabled:opacity-50'
              >
                Next
              </button>
            </div>
          </div>
        </section>

        {error && <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300'>{error}</div>}
      </div>
    </div>
  )
}
