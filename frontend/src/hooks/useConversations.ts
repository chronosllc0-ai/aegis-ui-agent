/**
 * useConversations — server-side conversation + message persistence.
 *
 * All data lives in the backend DB (conversations / conversation_messages tables).
 * localStorage is used ONLY as a read-cache to make the UI feel instant.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '') ?? ''

// ── Types ──────────────────────────────────────────────────────────────
export type ServerConversation = {
  id: string
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

// ── Cache keys ─────────────────────────────────────────────────────────
const CONV_CACHE_KEY = 'aegis.server.conversations'
const MSG_CACHE_KEY = (id: string) => `aegis.server.msgs.${id}`

function readCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}
function writeCache(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* quota */ }
}

// ── Hook ───────────────────────────────────────────────────────────────
export function useConversations() {
  const [conversations, setConversations] = useState<ServerConversation[]>(
    () => readCache<ServerConversation[]>(CONV_CACHE_KEY) ?? []
  )
  const [loadingMessages, setLoadingMessages] = useState(false)
  const fetchedConvsRef = useRef(false)

  // Load conversation list from server once on mount
  const fetchConversations = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/conversations`, { credentials: 'include' })
      if (!res.ok) return
      const data = await res.json() as { ok: boolean; conversations: ServerConversation[] }
      if (data.ok) {
        setConversations(data.conversations)
        writeCache(CONV_CACHE_KEY, data.conversations)
      }
    } catch { /* network error — cache serves */ }
  }, [])

  useEffect(() => {
    if (fetchedConvsRef.current) return
    fetchedConvsRef.current = true
    void fetchConversations()
  }, [fetchConversations])

  // Fetch messages for a specific conversation (with cache-first)
  const fetchMessages = useCallback(async (conversationId: string): Promise<ServerMessage[]> => {
    const cacheKey = MSG_CACHE_KEY(conversationId)
    const cached = readCache<ServerMessage[]>(cacheKey)
    setLoadingMessages(true)
    try {
      const res = await fetch(`${API}/api/conversations/${conversationId}/messages`, { credentials: 'include' })
      if (!res.ok) return cached ?? []
      const data = await res.json() as { ok: boolean; messages: ServerMessage[]; conversation: ServerConversation }
      if (data.ok) {
        writeCache(cacheKey, data.messages)
        // Update conversation title in local list if server has a better one
        setConversations(prev =>
          prev.map(c => c.id === conversationId ? { ...c, title: data.conversation.title ?? c.title } : c)
        )
        return data.messages
      }
    } catch { /* return cache */ }
    finally { setLoadingMessages(false) }
    return cached ?? []
  }, [])

  // Delete a conversation (soft-delete on server + remove from local list)
  const deleteConversation = useCallback(async (conversationId: string) => {
    setConversations(prev => prev.filter(c => c.id !== conversationId))
    try {
      await fetch(`${API}/api/conversations/${conversationId}`, {
        method: 'DELETE',
        credentials: 'include',
      })
    } catch { /* best effort */ }
    try { localStorage.removeItem(MSG_CACHE_KEY(conversationId)) } catch { /* ok */ }
  }, [])

  // Called when the WS emits a conversation_id — adds/refreshes that conversation in our list
  const onNewConversationId = useCallback((conversationId: string, title?: string) => {
    setConversations(prev => {
      const exists = prev.find(c => c.id === conversationId)
      if (exists) return prev
      const newConv: ServerConversation = {
        id: conversationId,
        title: title ?? 'New task',
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      const next = [newConv, ...prev]
      writeCache(CONV_CACHE_KEY, next)
      return next
    })
    // Refresh from server after a short delay to get the real title
    window.setTimeout(() => { void fetchConversations() }, 2000)
  }, [fetchConversations])

  return { conversations, fetchMessages, deleteConversation, onNewConversationId, refreshConversations: fetchConversations, loadingMessages }
}
