import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type BackgroundTaskItem = {
  id: string
  title: string
  task_type: string
  status: string
  progress_pct: number
  progress_message: string | null
}

export function useBackgroundTasks() {
  const [tasks, setTasks] = useState<BackgroundTaskItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(apiUrl('/api/tasks/'), { credentials: 'include' })
      const data = await response.json()
      if (response.ok && data?.ok) setTasks(data.tasks ?? [])
    } finally {
      setLoading(false)
    }
  }, [])

  const runResearchTask = useCallback(async (topic: string) => {
    const response = await fetch(apiUrl('/api/tasks/'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_type: 'research', title: `Research: ${topic}`, payload: { topic } }),
    })
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to enqueue task')
    setTasks((prev) => [data.task, ...prev])
  }, [])

  const cancel = useCallback(async (id: string) => {
    const response = await fetch(apiUrl(`/api/tasks/${id}/cancel`), { method: 'POST', credentials: 'include' })
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to cancel')
    setTasks((prev) => prev.map((task) => (task.id === id ? { ...task, status: 'cancelled' } : task)))
  }, [])

  return { tasks, loading, load, runResearchTask, cancel }
}
