import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type BackgroundTaskEntry = {
  id: string
  user_id: string
  task_type: string
  title: string
  description: string | null
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  priority: number
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error_message: string | null
  progress_pct: number
  progress_message: string | null
  max_retries: number
  retry_count: number
  scheduled_at: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

export function useBackgroundTasks() {
  const [tasks, setTasks] = useState<BackgroundTaskEntry[]>([])
  const [badgeCount, setBadgeCount] = useState(0)
  const [loading, setLoading] = useState(false)

  const fetchTasks = useCallback(async (status?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (status) params.set('status', status)
      const query = params.toString()
      const endpoint = query ? `/api/tasks/?${query}` : '/api/tasks/'
      const resp = await fetch(apiUrl(endpoint), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setTasks(data.tasks)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchBadge = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/tasks/badge'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setBadgeCount(data.count)
    } catch {
      // silent
    }
  }, [])

  const clearBadge = useCallback(async () => {
    try {
      await fetch(apiUrl('/api/tasks/badge/clear'), { method: 'POST', credentials: 'include' })
      setBadgeCount(0)
    } catch {
      // silent
    }
  }, [])

  const enqueueTask = useCallback(async (taskType: string, title: string, payload: Record<string, unknown>, priority?: number): Promise<BackgroundTaskEntry | null> => {
    try {
      const resp = await fetch(apiUrl('/api/tasks/'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_type: taskType, title, payload, priority }),
      })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => [data.task, ...prev])
        return data.task
      }
      return null
    } catch {
      return null
    }
  }, [])

  const cancelTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/cancel`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'cancelled' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const pauseTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/pause`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'paused' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const resumeTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/resume`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'queued' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  return { tasks, badgeCount, loading, fetchTasks, fetchBadge, clearBadge, enqueueTask, cancelTask, pauseTask, resumeTask }
}
