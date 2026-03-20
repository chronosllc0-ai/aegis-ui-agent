import { useCallback, useEffect, useState } from 'react'
import { Icons } from '../icons'
import { useToast } from '../../hooks/useToast'
import { apiUrl } from '../../lib/api'

/* ─── Types ─────────────────────────────────────────────────────────── */

type ThreadUser = {
  uid: string
  name: string | null
  email: string | null
  avatar_url: string | null
}

type AdminThread = {
  id: string
  subject: string
  status: string
  priority: string
  created_at: string | null
  updated_at: string | null
  message_count: number
  last_message: string | null
  last_message_at: string | null
  user: ThreadUser | null
}

type AdminMessage = {
  id: string
  sender_id: string
  sender_role: string
  content: string
  created_at: string | null
  sender: { uid: string; name: string | null; avatar_url: string | null; role: string } | null
}

/* ─── Priority / Status badges ──────────────────────────────────────── */

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
  resolved: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  closed: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
}

const PRIORITY_COLORS: Record<string, string> = {
  low: 'text-zinc-500',
  normal: 'text-zinc-300',
  high: 'text-amber-300',
  urgent: 'text-red-300',
}

/* ─── Component ─────────────────────────────────────────────────────── */

export function AdminMessaging() {
  const [threads, setThreads] = useState<AdminThread[]>([])
  const [activeThread, setActiveThread] = useState<AdminThread | null>(null)
  const [messages, setMessages] = useState<AdminMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('open')
  const toast = useToast()

  const loadThreads = useCallback(async () => {
    setLoading(true)
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : ''
      const res = await fetch(apiUrl(`/api/admin/messaging/threads${qs}`), { credentials: 'include' })
      const data = await res.json().catch(() => ({}))
      if (data?.threads) setThreads(data.threads)
    } catch {
      toast.error('Failed to load support threads')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, toast])

  useEffect(() => {
    void loadThreads()
  }, [loadThreads])

  const openThread = async (thread: AdminThread) => {
    setActiveThread(thread)
    try {
      const res = await fetch(apiUrl(`/api/admin/messaging/threads/${thread.id}`), { credentials: 'include' })
      const data = await res.json().catch(() => ({}))
      if (data?.messages) setMessages(data.messages)
    } catch {
      toast.error('Failed to load messages')
    }
  }

  const sendReply = async () => {
    if (!reply.trim() || !activeThread) return
    setSending(true)
    try {
      const res = await fetch(apiUrl(`/api/admin/messaging/threads/${activeThread.id}/reply`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ content: reply.trim() }),
      })
      if (!res.ok) throw new Error('Failed to send reply')
      const data = await res.json().catch(() => ({}))
      if (data?.message) setMessages((prev) => [...prev, data.message])
      toast.success('Reply sent')
      setReply('')
    } catch {
      toast.error('Failed to send reply')
    } finally {
      setSending(false)
    }
  }

  const updateThread = async (threadId: string, patch: { status?: string; priority?: string }) => {
    try {
      const res = await fetch(apiUrl(`/api/admin/messaging/threads/${threadId}`), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(patch),
      })
      if (!res.ok) throw new Error('Failed to update thread')
      toast.success('Thread updated')
      if (activeThread?.id === threadId) {
        setActiveThread((prev) => prev ? { ...prev, ...patch } : prev)
      }
      await loadThreads()
    } catch {
      toast.error('Failed to update thread')
    }
  }

  /* ── Thread detail ── */
  if (activeThread) {
    return (
      <div className='flex h-full flex-col'>
        <div className='flex items-center justify-between border-b border-[#2a2a2a] pb-3'>
          <button
            type='button'
            onClick={() => setActiveThread(null)}
            className='flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200'
          >
            {Icons.back({ className: 'h-3.5 w-3.5' })}
            <span>All threads</span>
          </button>
          <div className='flex items-center gap-2'>
            <select
              value={activeThread.status}
              onChange={(e) => updateThread(activeThread.id, { status: e.target.value })}
              className='rounded border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'
            >
              <option value='open'>Open</option>
              <option value='resolved'>Resolved</option>
              <option value='closed'>Closed</option>
            </select>
            <select
              value={activeThread.priority}
              onChange={(e) => updateThread(activeThread.id, { priority: e.target.value })}
              className='rounded border border-[#2a2a2a] bg-[#111] px-2 py-1 text-xs text-zinc-300'
            >
              <option value='low'>Low</option>
              <option value='normal'>Normal</option>
              <option value='high'>High</option>
              <option value='urgent'>Urgent</option>
            </select>
          </div>
        </div>

        <div className='mt-3 mb-3'>
          <h3 className='text-sm font-semibold text-white'>{activeThread.subject}</h3>
          {activeThread.user && (
            <p className='mt-0.5 text-[11px] text-zinc-500'>
              From: {activeThread.user.name || activeThread.user.email || activeThread.user.uid}
            </p>
          )}
        </div>

        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4'>
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                msg.sender_role === 'admin'
                  ? 'ml-auto bg-blue-600/20 text-zinc-100'
                  : msg.sender_role === 'user'
                    ? 'bg-[#1a1a1a] text-zinc-200'
                    : 'bg-zinc-800/50 text-zinc-400 italic'
              }`}
            >
              <p className='mb-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-500'>
                {msg.sender_role === 'admin'
                  ? `Admin${msg.sender?.name ? ` (${msg.sender.name})` : ''}`
                  : msg.sender_role === 'user'
                    ? msg.sender?.name || 'Customer'
                    : 'System'}
              </p>
              <p className='whitespace-pre-wrap'>{msg.content}</p>
              {msg.created_at && (
                <p className='mt-1 text-[10px] text-zinc-600'>{new Date(msg.created_at).toLocaleString()}</p>
              )}
            </div>
          ))}
          {!messages.length && <p className='text-center text-xs text-zinc-500'>No messages</p>}
        </div>

        <div className='mt-3 flex gap-2'>
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendReply() } }}
            placeholder='Type your reply as admin...'
            rows={2}
            className='flex-1 resize-none rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm'
          />
          <button
            type='button'
            onClick={sendReply}
            disabled={sending || !reply.trim()}
            className='self-end rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium hover:bg-blue-500 disabled:opacity-50'
          >
            Reply
          </button>
        </div>
      </div>
    )
  }

  /* ── Thread list ── */
  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <div>
          <h2 className='text-lg font-semibold text-white'>Customer Messages</h2>
          <p className='text-xs text-zinc-400'>Support threads from customers using "Talk to us"</p>
        </div>
        <div className='flex gap-1'>
          {['open', 'resolved', 'closed', ''].map((s) => (
            <button
              key={s || 'all'}
              type='button'
              onClick={() => setStatusFilter(s)}
              className={`rounded-full px-3 py-1 text-xs transition ${
                statusFilter === s ? 'bg-blue-600 text-white' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className='text-xs text-zinc-500'>Loading threads...</p>}

      {!loading && !threads.length && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-8 text-center'>
          <p className='text-sm text-zinc-400'>No support threads {statusFilter ? `with status "${statusFilter}"` : ''}</p>
        </div>
      )}

      <div className='space-y-2'>
        {threads.map((thread) => (
          <button
            key={thread.id}
            type='button'
            onClick={() => openThread(thread)}
            className='w-full rounded-xl border border-[#2a2a2a] bg-[#111] p-4 text-left transition hover:border-blue-500/30'
          >
            <div className='flex items-center justify-between'>
              <div className='flex items-center gap-2'>
                {thread.user?.avatar_url ? (
                  <img src={thread.user.avatar_url} alt='' className='h-6 w-6 rounded-full' />
                ) : (
                  <span className='flex h-6 w-6 items-center justify-center rounded-full bg-zinc-700 text-[10px] font-bold text-zinc-300'>
                    {(thread.user?.name?.[0] || thread.user?.email?.[0] || '?').toUpperCase()}
                  </span>
                )}
                <span className='text-sm font-medium text-white'>{thread.subject}</span>
              </div>
              <div className='flex items-center gap-2'>
                <span className={`text-[10px] font-medium ${PRIORITY_COLORS[thread.priority] ?? 'text-zinc-400'}`}>
                  {thread.priority}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] ${STATUS_COLORS[thread.status] ?? STATUS_COLORS.open}`}>
                  {thread.status}
                </span>
              </div>
            </div>
            <div className='mt-2 flex items-center justify-between text-[11px] text-zinc-500'>
              <span>{thread.user?.name || thread.user?.email || 'Unknown user'} • {thread.message_count} messages</span>
              {thread.last_message_at && <span>{new Date(thread.last_message_at).toLocaleDateString()}</span>}
            </div>
            {thread.last_message && (
              <p className='mt-1.5 truncate text-xs text-zinc-400'>{thread.last_message}</p>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
