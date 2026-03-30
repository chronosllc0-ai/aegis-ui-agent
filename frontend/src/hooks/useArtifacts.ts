import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type ArtifactEntry = {
  id: string
  user_id: string
  conversation_id: string | null
  plan_id: string | null
  step_id: string | null
  title: string
  description: string | null
  artifact_type: string
  mime_type: string
  filename: string
  file_size: number
  storage_path: string
  content_preview: string | null
  metadata: Record<string, unknown>
  is_pinned: boolean
  download_count: number
  created_at: string | null
}

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([])
  const [loading, setLoading] = useState(false)

  const fetchArtifacts = useCallback(async (conversationId?: string, type?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (conversationId) params.set('conversation_id', conversationId)
      if (type) params.set('type', type)
      const query = params.toString()
      const endpoint = query ? `/api/artifacts/?${query}` : '/api/artifacts/'
      const resp = await fetch(apiUrl(endpoint), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setArtifacts(data.artifacts)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [])

  const downloadArtifact = useCallback(async (id: string, filename: string) => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}/download`), { credentials: 'include' })
      if (!resp.ok) return
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // silent
    }
  }, [])

  const togglePin = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}/pin`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setArtifacts((prev) => prev.map((a) => (a.id === id ? data.artifact : a)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const deleteArtifact = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}`), { method: 'DELETE', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setArtifacts((prev) => prev.filter((a) => a.id !== id))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  return { artifacts, loading, fetchArtifacts, downloadArtifact, togglePin, deleteArtifact }
}
