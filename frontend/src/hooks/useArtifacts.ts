import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type ArtifactItem = {
  id: string
  title: string
  filename: string
  artifact_type: string
  created_at: string | null
}

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(apiUrl('/api/artifacts/'), { credentials: 'include' })
      const data = await response.json()
      if (response.ok && data?.ok) setArtifacts(data.artifacts ?? [])
    } finally {
      setLoading(false)
    }
  }, [])

  const getDownloadUrl = useCallback((id: string) => apiUrl(`/api/artifacts/${id}/download`), [])

  return { artifacts, loading, load, getDownloadUrl }
}
