import { useCallback, useState } from 'react'
import { apiUrl } from '../../lib/api'

type ImpersonationStatus = {
  impersonating: boolean
  target_user?: { uid: string; email: string; name: string }
  admin_uid?: string
}

export function useImpersonation() {
  const [status, setStatus] = useState<ImpersonationStatus | null>(null)
  const [loading, setLoading] = useState(false)

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/status'), { credentials: 'include' })
      if (res.ok) {
        const data = (await res.json()) as ImpersonationStatus
        setStatus(data)
      }
    } catch {
      // Ignore
    }
  }, [])

  const startImpersonation = useCallback(async (target: string): Promise<boolean> => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/start'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: string }
        throw new Error(err.detail || 'Impersonation failed')
      }
      return true
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  const stopImpersonation = useCallback(async (): Promise<boolean> => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/admin/impersonate/stop'), {
        method: 'POST',
        credentials: 'include',
      })
      return res.ok
    } catch {
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  return { status, loading, checkStatus, startImpersonation, stopImpersonation }
}
