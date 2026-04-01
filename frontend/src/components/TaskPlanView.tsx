import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../lib/api'
import { AgentActivityFeed } from './AgentActivityFeed'
import { usePlanExecution } from '../hooks/usePlanExecution'

type TaskStep = {
  id: string
  parent_step_id: string | null
  step_index: number
  title: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  assigned_provider: string
  assigned_model: string
  depends_on: string[]
  result_text: string | null
  error_message: string | null
  tokens_used: number
  credits_used: number
  started_at: string | null
  completed_at: string | null
}

type Plan = {
  id: string
  title: string
  status: 'draft' | 'approved' | 'running' | 'completed' | 'failed' | 'cancelled'
  original_prompt: string
  provider: string
  model: string
  steps: TaskStep[]
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

type TaskPlanViewProps = {
  planId: string
  onClose?: () => void
}

const STATUS_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  pending: { icon: '○', color: 'text-zinc-500', bg: 'bg-zinc-800' },
  running: { icon: '◉', color: 'text-blue-400', bg: 'bg-blue-900/30' },
  completed: { icon: '✓', color: 'text-emerald-400', bg: 'bg-emerald-900/30' },
  failed: { icon: '✗', color: 'text-red-400', bg: 'bg-red-900/30' },
  skipped: { icon: '-', color: 'text-zinc-600', bg: 'bg-zinc-800/50' },
}

const PLAN_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-zinc-700 text-zinc-300',
  approved: 'bg-blue-900/50 text-blue-300',
  running: 'bg-blue-600 text-white',
  completed: 'bg-emerald-900/50 text-emerald-300',
  failed: 'bg-red-900/50 text-red-300',
  cancelled: 'bg-zinc-800 text-zinc-500',
}

export function TaskPlanView({ planId, onClose }: TaskPlanViewProps) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set())
  const [actionBusy, setActionBusy] = useState(false)

  const { executing, error: execError, executePlan, stopPlan } = usePlanExecution()

  const fetchPlan = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl(`/api/plans/${planId}`), { credentials: 'include' })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok && data?.ok) {
        setPlan(data.plan as Plan)
        setError(null)
      } else {
        setError(typeof data?.detail === 'string' ? data.detail : 'Failed to load plan')
      }
    } catch {
      setError('Failed to load plan')
    } finally {
      setLoading(false)
    }
  }, [planId])

  useEffect(() => {
    void fetchPlan()
  }, [fetchPlan])

  // Poll for updates while running
  useEffect(() => {
    if (!plan || plan.status !== 'running') return
    const interval = window.setInterval(() => {
      void fetchPlan()
    }, 3000)
    return () => window.clearInterval(interval)
  }, [plan, fetchPlan])

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(stepId)) next.delete(stepId)
      else next.add(stepId)
      return next
    })
  }

  const handleApprove = async () => {
    if (!plan) return
    setActionBusy(true)
    try {
      const resp = await fetch(apiUrl(`/api/plans/${plan.id}/approve`), { method: 'POST', credentials: 'include' })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok && data?.ok) await fetchPlan()
      else setError(typeof data?.detail === 'string' ? data.detail : 'Failed to approve')
    } catch {
      setError('Failed to approve plan')
    } finally {
      setActionBusy(false)
    }
  }

  const handleExecute = async () => {
    if (!plan) return
    const ok = await executePlan(plan.id)
    if (ok) void fetchPlan()
  }

  const handleStop = async () => {
    if (!plan) return
    const ok = await stopPlan(plan.id)
    if (ok) void fetchPlan()
  }

  const handleCancel = async () => {
    if (!plan) return
    setActionBusy(true)
    try {
      const resp = await fetch(apiUrl(`/api/plans/${plan.id}/cancel`), { method: 'POST', credentials: 'include' })
      const data = await resp.json().catch(() => ({}))
      if (resp.ok && data?.ok) await fetchPlan()
      else setError(typeof data?.detail === 'string' ? data.detail : 'Failed to cancel')
    } catch {
      setError('Failed to cancel plan')
    } finally {
      setActionBusy(false)
    }
  }

  const rootSteps = useMemo(() => (plan ? plan.steps.filter((s) => !s.parent_step_id) : []), [plan])
  const completedCount = useMemo(() => (plan ? plan.steps.filter((s) => s.status === 'completed').length : 0), [plan])
  const totalCount = plan?.steps.length ?? 0

  if (loading) {
    return (
      <div className='flex items-center justify-center py-12'>
        <div className='h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent' />
      </div>
    )
  }

  if (error || !plan) {
    return <div className='rounded-lg border border-red-800/50 bg-red-900/20 p-4 text-sm text-red-300'>{error || 'Plan not found'}</div>
  }

  const childrenFor = (parentId: string) => plan.steps.filter((s) => s.parent_step_id === parentId)
  const isLive = plan.status === 'running'

  return (
    <div className='space-y-3'>
      <div className='rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4'>
        <div className='mb-4 flex items-start justify-between'>
          <div className='min-w-0 flex-1'>
            <div className='flex items-center gap-2'>
              <h3 className='text-base font-semibold text-white'>{plan.title}</h3>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${PLAN_STATUS_COLORS[plan.status] || ''}`}>{plan.status}</span>
            </div>
            <p className='mt-1 text-xs text-zinc-500'>{plan.original_prompt}</p>
            <div className='mt-2 flex items-center gap-2'>
              <div className='h-1.5 flex-1 rounded-full bg-zinc-800'>
                <div className='h-1.5 rounded-full bg-blue-500 transition-all' style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }} />
              </div>
              <span className='text-[11px] text-zinc-500'>
                {completedCount}/{totalCount}
              </span>
            </div>
          </div>
          {onClose && (
            <button type='button' onClick={onClose} className='ml-2 text-zinc-500 hover:text-zinc-300'>
              ✕
            </button>
          )}
        </div>

        <div className='space-y-1.5'>
          {rootSteps.map((step) => {
            const ss = STATUS_STYLES[step.status] || STATUS_STYLES.pending
            const expanded = expandedSteps.has(step.id)
            const children = childrenFor(step.id)
            return (
              <div key={step.id}>
                <button
                  type='button'
                  onClick={() => toggleStep(step.id)}
                  className={`flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-colors ${ss.bg} hover:bg-zinc-800`}
                >
                  <span className={`mt-0.5 text-sm font-mono ${ss.color} ${step.status === 'running' ? 'animate-pulse' : ''}`}>{ss.icon}</span>
                  <div className='min-w-0 flex-1'>
                    <span className='text-sm text-zinc-200'>{step.title}</span>
                    <div className='mt-0.5 flex items-center gap-2'>
                      <span className='rounded bg-zinc-700 px-1.5 py-0.5 text-[9px] text-zinc-400'>
                        {step.assigned_provider}/{step.assigned_model}
                      </span>
                      {step.depends_on.length > 0 && <span className='text-[9px] text-zinc-600'>depends on: {step.depends_on.join(', ')}</span>}
                    </div>
                  </div>
                  <span className='text-[10px] text-zinc-600'>{expanded ? '▾' : '▸'}</span>
                </button>
                {expanded && (
                  <div className='ml-8 mt-1 space-y-1'>
                    {step.description && <p className='text-xs text-zinc-400'>{step.description}</p>}
                    {step.result_text && <div className='rounded-lg bg-zinc-800/50 p-2 text-xs text-zinc-300'>{step.result_text}</div>}
                    {step.error_message && <div className='rounded-lg bg-red-900/20 p-2 text-xs text-red-300'>{step.error_message}</div>}
                    {children.map((child) => {
                      const cs = STATUS_STYLES[child.status] || STATUS_STYLES.pending
                      return (
                        <div key={child.id} className={`flex items-start gap-2 rounded-lg px-2 py-1.5 ${cs.bg}`}>
                          <span className={`text-xs font-mono ${cs.color} ${child.status === 'running' ? 'animate-pulse' : ''}`}>{cs.icon}</span>
                          <div className='min-w-0 flex-1'>
                            <span className='text-xs text-zinc-300'>{child.title}</span>
                            <span className='ml-2 rounded bg-zinc-700 px-1 py-0.5 text-[8px] text-zinc-500'>{child.assigned_provider}</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {(execError) && (
          <div className='mt-3 rounded-lg border border-red-800/50 bg-red-900/20 p-2 text-xs text-red-300'>{execError}</div>
        )}

        <div className='mt-4 flex gap-2'>
          {plan.status === 'draft' && (
            <button
              type='button'
              onClick={handleApprove}
              disabled={actionBusy}
              className='rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50'
            >
              {actionBusy ? 'Approving...' : 'Approve Plan'}
            </button>
          )}
          {plan.status === 'approved' && (
            <button
              type='button'
              onClick={handleExecute}
              disabled={executing}
              className='rounded-lg bg-emerald-600 px-4 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50'
            >
              {executing ? 'Starting...' : 'Execute Plan'}
            </button>
          )}
          {plan.status === 'running' && (
            <button
              type='button'
              onClick={handleStop}
              className='rounded-lg bg-amber-600 px-4 py-2 text-xs font-medium text-white hover:bg-amber-500'
            >
              Stop Execution
            </button>
          )}
          {['draft', 'approved', 'running'].includes(plan.status) && (
            <button
              type='button'
              onClick={handleCancel}
              disabled={actionBusy}
              className='rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50'
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Live activity feed shown while plan is running */}
      {isLive && <AgentActivityFeed planId={planId} />}
    </div>
  )
}
