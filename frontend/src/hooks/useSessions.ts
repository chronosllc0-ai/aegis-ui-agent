import { useCallback, useEffect, useRef, useState } from 'react'

const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '') ?? ''

export type ServerSession = {
  session_id: string
  parent_session_id: string | null
  title: string
  status: string
  created_at: string | null
  updated_at: string | null
}

export type ServerMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  metadata: Record<string, unknown> | null
  created_at: string | null
}

export function useSessions(userUid: string | null) {
  const [sessions, setSessions] = useState<ServerSession[]>([])
  const fetchedRef = useRef(false)

  const fetchSessions = useCallback(async () => {
    if (!userUid) {
      setSessions([])
      return
    }
    try {
      const res = await fetch(`${API}/api/sessions`, { credentials: 'include' })
      if (!res.ok) return
      const data = await res.json() as { ok: boolean; sessions: ServerSession[] }
      if (data.ok) setSessions(data.sessions)
    } catch {
      // keep existing cached state when network fetch fails
    }
  }, [userUid])

  useEffect(() => {
    if (!userUid) {
      fetchedRef.current = false
      return
    }
    if (fetchedRef.current) return
    fetchedRef.current = true
    void fetchSessions()
  }, [fetchSessions, userUid])

  useEffect(() => {
    fetchedRef.current = false
  }, [userUid])

  const fetchMessages = useCallback(async (sessionId: string): Promise<ServerMessage[]> => {
    if (!userUid) return []
    try {
      const res = await fetch(`${API}/api/sessions/${encodeURIComponent(sessionId)}/messages`, { credentials: 'include' })
      if (!res.ok) return []
      const data = await res.json() as { ok: boolean; messages: ServerMessage[] }
      if (data.ok) return data.messages
    } catch {
      return []
    }
    return []
  }, [userUid])

  return { sessions, fetchSessions, fetchMessages }
}
