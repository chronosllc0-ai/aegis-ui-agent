import { useEffect, useState, useCallback } from 'react'
import { Icons } from './icons'
import { apiUrl } from '../lib/api'
import { useSettingsContext } from '../context/useSettingsContext'

// ── Types ─────────────────────────────────────────────────────────────────

type TaskStatus = 'pending' | 'running' | 'success' | 'failed'

interface ScheduledTask {
  id: string
  name: string
  description?: string
  prompt: string
  cron_expr: string
  timezone: string
  enabled: boolean
  last_run_at?: string
  next_run_at?: string
  last_status: TaskStatus
  last_error?: string
  run_count: number
  created_at: string
}

// ── Cron helpers ─────────────────────────────────────────────────────────

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
  const match = PRESETS.find((p) => p.value === expr)
  if (match && match.value !== '__custom__') return match.label
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr
  const [min, hour, dom, , dow] = parts
  const hourNum = parseInt(hour, 10)
  const minNum = parseInt(min, 10)
  const pad = (n: number) => String(n).padStart(2, '0')
  const timeStr = !isNaN(hourNum) && !isNaN(minNum) ? `${pad(hourNum)}:${pad(minNum)}` : null
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  if (dow === '*' && dom === '*') {
    if (timeStr) return `Every day at ${timeStr}`
    return 'Every day'
  }
  if (dow === '1-5' && timeStr) return `Weekdays at ${timeStr}`
  if (dow !== '*' && !dow.includes('-') && !dow.includes(',')) {
    const d = parseInt(dow, 10)
    if (!isNaN(d) && d >= 0 && d <= 6) {
      return timeStr ? `Every ${days[d]} at ${timeStr}` : `Every ${days[d]}`
    }
  }
  return expr
}

function relativeTime(isoStr?: string): string {
  if (!isoStr) return '—'
  const dt = new Date(isoStr)
  const diffMs = dt.getTime() - Date.now()
  const absDiff = Math.abs(diffMs)
  const past = diffMs < 0
  if (absDiff < 60_000) return past ? 'just now' : 'in a few seconds'
  const mins = Math.round(absDiff / 60_000)
  if (mins < 60) return past ? `${mins}m ago` : `in ${mins}m`
  const hours = Math.round(absDiff / 3_600_000)
  if (hours < 24) return past ? `${hours}h ago` : `in ${hours}h`
  const days = Math.round(absDiff / 86_400_000)
  return past ? `${days}d ago` : `in ${days}d`
}

// ── Status badge ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: TaskStatus }) {
  const map: Record<TaskStatus, { cls: string; label: string }> = {
    pending: { cls: 'bg-zinc-700 text-zinc-300', label: 'Pending' },
    running: { cls: 'bg-yellow-500/20 text-yellow-300', label: 'Running' },
    success: { cls: 'bg-emerald-500/20 text-emerald-300', label: 'Success' },
    failed: { cls: 'bg-red-500/20 text-red-300', label: 'Failed' },
  }
  const { cls, label } = map[status] ?? map.pending
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────

interface ModalProps {
  initial?: Partial<ScheduledTask>
  onSave: (data: {
    name: string
    description: string
    prompt: string
    cron_expr: string
    timezone: string
  }) => Promise<void>
  onClose: () => void
}

function AutomationModal({ initial, onSave, onClose }: ModalProps) {
  const { settings } = useSettingsContext()
  const workflows = settings.workflowTemplates ?? []

  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [prompt, setPrompt] = useState(initial?.prompt ?? '')
  // triggerType: 'prompt' = describe task manually; 'workflow' = pick a saved workflow
  const [triggerType, setTriggerType] = useState<'prompt' | 'workflow'>('prompt')
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>('')
  const [preset, setPreset] = useState(() => {
    if (!initial?.cron_expr) return PRESETS[1].value
    const found = PRESETS.find((p) => p.value === initial.cron_expr)
    return found ? found.value : '__custom__'
  })
  const [customCron, setCustomCron] = useState(initial?.cron_expr ?? '')
  const [timezone, setTimezone] = useState(initial?.timezone ?? 'UTC')
  const [tzSearch, setTzSearch] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // When a workflow is selected, auto-fill the name and prompt
  const handleWorkflowSelect = (workflowId: string) => {
    setSelectedWorkflowId(workflowId)
    const wf = workflows.find((w) => w.id === workflowId)
    if (wf) {
      if (!name || name === '') setName(wf.name)
      setPrompt(wf.instruction)
    }
  }

  const cronExpr = preset === '__custom__' ? customCron : preset

  const filteredTz = COMMON_TIMEZONES.filter((tz) =>
    tz.toLowerCase().includes(tzSearch.toLowerCase()),
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    // Resolve final prompt
    let resolvedPrompt = prompt.trim()
    if (triggerType === 'workflow') {
      const wf = workflows.find((w) => w.id === selectedWorkflowId)
      if (!wf) { setError('Please select a workflow'); return }
      resolvedPrompt = wf.instruction
    }
    if (!name.trim()) { setError('Name is required'); return }
    if (!resolvedPrompt) { setError('Prompt is required'); return }
    if (!cronExpr.trim()) { setError('Schedule is required'); return }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), description: description.trim(), prompt: resolvedPrompt, cron_expr: cronExpr.trim(), timezone })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4' onClick={onClose}>
      <div
        className='w-full max-w-lg rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a] p-6 shadow-2xl'
        onClick={(e) => e.stopPropagation()}
      >
        <div className='mb-5 flex items-center justify-between'>
          <h2 className='text-base font-semibold text-zinc-100'>
            {initial?.id ? 'Edit automation' : 'New automation'}
          </h2>
          <button type='button' onClick={onClose} className='text-zinc-500 hover:text-zinc-200'>
            {Icons.close({ className: 'h-4 w-4' })}
          </button>
        </div>

        {error && (
          <div className='mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300'>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className='space-y-4'>
          {/* Name */}
          <div>
            <label className='mb-1 block text-xs text-zinc-400'>Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='Morning email summary'
              className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
          </div>

          {/* Description */}
          <div>
            <label className='mb-1 block text-xs text-zinc-400'>Description (optional)</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='Summarizes unread Gmail emails every Monday morning'
              className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
          </div>

          {/* Trigger type toggle */}
          <div>
            <label className='mb-1.5 block text-xs text-zinc-400'>Trigger type *</label>
            <div className='flex gap-1 rounded-lg border border-[#2a2a2a] bg-[#111] p-1'>
              <button
                type='button'
                onClick={() => setTriggerType('prompt')}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  triggerType === 'prompt' ? 'bg-[#2a2a2a] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Describe task
              </button>
              <button
                type='button'
                onClick={() => setTriggerType('workflow')}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  triggerType === 'workflow' ? 'bg-[#2a2a2a] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Run workflow
              </button>
            </div>
          </div>

          {/* Conditional: prompt text OR workflow selector */}
          {triggerType === 'workflow' ? (
            <div>
              <label className='mb-1 block text-xs text-zinc-400'>Select workflow *</label>
              {workflows.length === 0 ? (
                <p className='rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-3 text-xs text-zinc-500'>
                  No saved workflows yet. Run a task from the dashboard and save it as a Workflow first.
                </p>
              ) : (
                <select
                  value={selectedWorkflowId}
                  onChange={(e) => handleWorkflowSelect(e.target.value)}
                  className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                >
                  <option value=''>— choose a workflow —</option>
                  {workflows.map((wf) => (
                    <option key={wf.id} value={wf.id}>{wf.name}</option>
                  ))}
                </select>
              )}
              {selectedWorkflowId && (() => {
                const wf = workflows.find((w) => w.id === selectedWorkflowId)
                return wf ? (
                  <p className='mt-1.5 rounded-lg border border-[#2a2a2a] bg-[#0a0a0a] px-3 py-2 text-[11px] text-zinc-400 line-clamp-2'>
                    {wf.instruction}
                  </p>
                ) : null
              })()}
            </div>
          ) : (
            <div>
              <label className='mb-1 block text-xs text-zinc-400'>What should Aegis do? *</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder='Open Gmail, find all unread emails from today, and summarize them in a list.'
                rows={4}
                className='w-full resize-none rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
              />
            </div>
          )}

          {/* Schedule */}
          <div>
            <label className='mb-1 block text-xs text-zinc-400'>Schedule *</label>
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value)}
              className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              {PRESETS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>

            {preset === '__custom__' && (
              <div className='mt-2'>
                <input
                  value={customCron}
                  onChange={(e) => setCustomCron(e.target.value)}
                  placeholder='0 9 * * 1'
                  className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
                />
                <p className='mt-1 text-[11px] text-zinc-500'>
                  5-field cron: minute hour day-of-month month day-of-week
                </p>
              </div>
            )}

            {cronExpr && preset !== '__custom__' && (
              <p className='mt-1 text-[11px] text-zinc-500'>
                {humanizeCron(cronExpr)} — <span className='font-mono'>{cronExpr}</span>
              </p>
            )}
            {cronExpr && preset === '__custom__' && customCron && (
              <p className='mt-1 text-[11px] text-zinc-500'>
                Preview: {humanizeCron(customCron)}
              </p>
            )}
          </div>

          {/* Timezone */}
          <div>
            <label className='mb-1 block text-xs text-zinc-400'>Timezone</label>
            <input
              value={tzSearch}
              onChange={(e) => setTzSearch(e.target.value)}
              placeholder='Search timezone…'
              className='mb-1.5 w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            />
            <select
              value={timezone}
              onChange={(e) => { setTimezone(e.target.value); setTzSearch('') }}
              size={4}
              className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-2 py-1 text-sm text-zinc-100 outline-none focus:border-cyan-500/60'
            >
              {filteredTz.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
            <p className='mt-1 text-[11px] text-zinc-500'>Selected: {timezone}</p>
          </div>

          {/* Actions */}
          <div className='flex justify-end gap-2 pt-1'>
            <button
              type='button'
              onClick={onClose}
              className='rounded-lg border border-[#2a2a2a] px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200'
            >
              Cancel
            </button>
            <button
              type='submit'
              disabled={saving}
              className='rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500 disabled:opacity-50'
            >
              {saving ? 'Saving…' : initial?.id ? 'Save changes' : 'Create automation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Task card ─────────────────────────────────────────────────────────────

interface TaskCardProps {
  task: ScheduledTask
  onToggle: (id: string, enabled: boolean) => void
  onDelete: (id: string) => void
  onRun: (id: string) => void
  onEdit: (task: ScheduledTask) => void
}

function TaskCard({ task, onToggle, onDelete, onRun, onEdit }: TaskCardProps) {
  return (
    <div className='rounded-xl border border-[#2a2a2a] bg-[#171717] p-4'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <h3 className='truncate text-sm font-medium text-zinc-100'>{task.name}</h3>
            <StatusBadge status={task.last_status} />
          </div>
          {task.description && (
            <p className='mt-0.5 truncate text-xs text-zinc-500'>{task.description}</p>
          )}
          <p className='mt-1.5 text-xs text-zinc-400'>
            {Icons.clock({ className: 'mr-1 inline h-3 w-3' })}
            {humanizeCron(task.cron_expr)}
            <span className='mx-1.5 text-zinc-600'>·</span>
            <span className='text-zinc-500'>{task.timezone}</span>
          </p>
          <div className='mt-1.5 flex items-center gap-3 text-[11px] text-zinc-500'>
            {task.next_run_at && (
              <span>Next: {relativeTime(task.next_run_at)}</span>
            )}
            {task.last_run_at && (
              <span>Last: {relativeTime(task.last_run_at)}</span>
            )}
            <span>Runs: {task.run_count}</span>
          </div>
        </div>

        {/* Controls */}
        <div className='flex shrink-0 items-center gap-1.5'>
          {/* Enable/disable toggle */}
          <button
            type='button'
            onClick={() => onToggle(task.id, !task.enabled)}
            title={task.enabled ? 'Disable' : 'Enable'}
            className={`relative h-5 w-9 rounded-full transition-colors ${task.enabled ? 'bg-cyan-600' : 'bg-zinc-700'}`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${task.enabled ? 'translate-x-4' : 'translate-x-0.5'}`}
            />
          </button>

          {/* Run now */}
          <button
            type='button'
            onClick={() => onRun(task.id)}
            title='Run now'
            className='rounded-md border border-[#2a2a2a] p-1.5 text-zinc-400 hover:border-cyan-500/50 hover:text-cyan-300'
          >
            {Icons.play({ className: 'h-3.5 w-3.5' })}
          </button>

          {/* Edit */}
          <button
            type='button'
            onClick={() => onEdit(task)}
            title='Edit'
            className='rounded-md border border-[#2a2a2a] p-1.5 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200'
          >
            {Icons.edit({ className: 'h-3.5 w-3.5' })}
          </button>

          {/* Delete */}
          <button
            type='button'
            onClick={() => onDelete(task.id)}
            title='Delete'
            className='rounded-md border border-[#2a2a2a] p-1.5 text-zinc-400 hover:border-red-500/50 hover:text-red-400'
          >
            {Icons.trash({ className: 'h-3.5 w-3.5' })}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export function AutomationsPage() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [editingTask, setEditingTask] = useState<ScheduledTask | undefined>(undefined)
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set())

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/automation/tasks'), { credentials: 'include' })
      if (!res.ok) throw new Error(`Failed to load automations (${res.status})`)
      const data = await res.json()
      setTasks(data.tasks ?? [])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load automations')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks()
  }, [fetchTasks])

  const handleCreate = async (data: {
    name: string
    description: string
    prompt: string
    cron_expr: string
    timezone: string
  }) => {
    const res = await fetch(apiUrl('/api/automation/tasks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail ?? `Error ${res.status}`)
    }
    setShowModal(false)
    await fetchTasks()
  }

  const handleUpdate = async (data: {
    name: string
    description: string
    prompt: string
    cron_expr: string
    timezone: string
  }) => {
    if (!editingTask) return
    const res = await fetch(apiUrl(`/api/automation/tasks/${editingTask.id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail ?? `Error ${res.status}`)
    }
    setEditingTask(undefined)
    await fetchTasks()
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    await fetch(apiUrl(`/api/automation/tasks/${id}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    })
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, enabled } : t)))
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this automation?')) return
    await fetch(apiUrl(`/api/automation/tasks/${id}`), {
      method: 'DELETE',
      credentials: 'include',
    })
    setTasks((prev) => prev.filter((t) => t.id !== id))
  }

  const handleRun = async (id: string) => {
    setRunningIds((prev) => new Set(prev).add(id))
    try {
      await fetch(apiUrl(`/api/automation/tasks/${id}/run`), {
        method: 'POST',
        credentials: 'include',
      })
      // Refresh after a short delay to pick up status change
      setTimeout(() => { void fetchTasks() }, 1500)
    } finally {
      setRunningIds((prev) => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  return (
    <div className='flex h-full flex-col overflow-hidden rounded-xl border border-[#2a2a2a] bg-[#171717]'>
      {/* Header */}
      <div className='flex items-center justify-between border-b border-[#2a2a2a] px-5 py-4'>
        <div className='flex items-center gap-2'>
          {Icons.clock({ className: 'h-4 w-4 text-cyan-400' })}
          <h2 className='text-sm font-semibold text-zinc-100'>Automations</h2>
          {tasks.length > 0 && (
            <span className='rounded-full bg-cyan-600/20 px-2 py-0.5 text-[11px] font-medium text-cyan-300'>
              {tasks.length}
            </span>
          )}
        </div>
        <button
          type='button'
          onClick={() => { setEditingTask(undefined); setShowModal(true) }}
          className='flex items-center gap-1.5 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500'
        >
          {Icons.plus({ className: 'h-3.5 w-3.5' })}
          New automation
        </button>
      </div>

      {/* Body */}
      <div className='min-h-0 flex-1 overflow-y-auto p-5'>
        {loading && (
          <div className='flex items-center justify-center py-20 text-sm text-zinc-500'>
            Loading automations…
          </div>
        )}

        {!loading && error && (
          <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300'>
            {error}
          </div>
        )}

        {!loading && !error && tasks.length === 0 && (
          <div className='flex flex-col items-center justify-center py-24 text-center'>
            <div className='mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-[#2a2a2a] bg-[#111]'>
              {Icons.clock({ className: 'h-8 w-8 text-zinc-600' })}
            </div>
            <h3 className='mb-1 text-sm font-medium text-zinc-300'>
              Schedule your first automation
            </h3>
            <p className='max-w-xs text-xs text-zinc-500'>
              Automations let Aegis run tasks on a schedule — daily reports, weekly
              summaries, recurring checks, and more.
            </p>
            <button
              type='button'
              onClick={() => { setEditingTask(undefined); setShowModal(true) }}
              className='mt-5 flex items-center gap-1.5 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500'
            >
              {Icons.plus({ className: 'h-4 w-4' })}
              New automation
            </button>
          </div>
        )}

        {!loading && !error && tasks.length > 0 && (
          <div className='space-y-3'>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={runningIds.has(task.id) ? { ...task, last_status: 'running' } : task}
                onToggle={handleToggle}
                onDelete={handleDelete}
                onRun={handleRun}
                onEdit={(t) => { setEditingTask(t); setShowModal(true) }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <AutomationModal
          initial={editingTask}
          onSave={editingTask ? handleUpdate : handleCreate}
          onClose={() => { setShowModal(false); setEditingTask(undefined) }}
        />
      )}
    </div>
  )
}
