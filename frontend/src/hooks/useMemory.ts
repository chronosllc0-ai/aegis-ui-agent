import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type MemoryEntry = {
  id: string
  user_id: string
  content: string
  category: string
  source: string
  source_conversation_id: string | null
  embedding_model: string | null
  importance: number
  access_count: number
  is_pinned: boolean
  last_accessed_at: string | null
  created_at: string | null
  updated_at: string | null
  relevance_score?: number
}

export type MemoryStats = {
  total_memories: number
  pinned_memories: number
  by_category: Record<string, number>
}

export function useMemory() {
  const [memories, setMemories] = useState<MemoryEntry[]>([])
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchMemories = useCallback(async (category?: string) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (category) params.set('category', category)
      const query = params.toString()
      const endpoint = query ? `/api/memory/?${query}` : '/api/memory/'
      const resp = await fetch(apiUrl(endpoint), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setMemories(data.memories)
      else setError(data.detail || 'Failed to load memories')
    } catch {
      setError('Failed to load memories')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/memory/stats'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setStats(data.stats)
    } catch {
      // silent
    }
  }, [])

  const createMemory = useCallback(async (content: string, category = 'general', importance = 0.5): Promise<MemoryEntry | null> => {
    try {
      const resp = await fetch(apiUrl('/api/memory/'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, category, importance }),
      })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => [data.memory, ...prev])
        return data.memory
      }
      return null
    } catch {
      return null
    }
  }, [])

  const updateMemory = useCallback(async (id: string, updates: Partial<Pick<MemoryEntry, 'content' | 'category' | 'importance' | 'is_pinned'>>): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/memory/${id}`), {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => prev.map((m) => (m.id === id ? data.memory : m)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const deleteMemory = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/memory/${id}`), { method: 'DELETE', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => prev.filter((m) => m.id !== id))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const searchMemories = useCallback(async (query: string, category?: string): Promise<MemoryEntry[]> => {
    try {
      const params = new URLSearchParams({ q: query })
      if (category) params.set('category', category)
      const resp = await fetch(apiUrl(`/api/memory/search?${params}`), { credentials: 'include' })
      const data = await resp.json()
      return data.ok ? data.memories : []
    } catch {
      return []
    }
  }, [])

  return { memories, stats, loading, error, fetchMemories, fetchStats, createMemory, updateMemory, deleteMemory, searchMemories }
}
