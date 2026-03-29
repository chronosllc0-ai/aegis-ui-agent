import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type MemoryItem = {
  id: string
  content: string
  category: string
  importance: number
  is_pinned: boolean
  access_count: number
  created_at: string | null
}

export function useMemory() {
  const [items, setItems] = useState<MemoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/api/memory/'), { credentials: 'include' })
      const data = await response.json()
      if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to load memories')
      setItems(data.memories ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load memories')
    } finally {
      setLoading(false)
    }
  }, [])

  const create = useCallback(async (content: string, category: string, importance: number) => {
    const response = await fetch(apiUrl('/api/memory/'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, category, importance }),
    })
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to create memory')
    setItems((prev) => [data.memory, ...prev])
  }, [])

  const remove = useCallback(async (id: string) => {
    const response = await fetch(apiUrl(`/api/memory/${id}`), { method: 'DELETE', credentials: 'include' })
    const data = await response.json()
    if (!response.ok || !data?.ok) throw new Error(data?.detail ?? 'Failed to delete memory')
    setItems((prev) => prev.filter((item) => item.id !== id))
  }, [])

  return { items, loading, error, load, create, remove }
}
