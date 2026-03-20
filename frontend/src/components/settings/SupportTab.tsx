import { useCallback, useEffect, useState } from 'react'
import { Icons } from '../icons'
import { useToast } from '../../hooks/useToast'
import { apiUrl } from '../../lib/api'

/* ─── Types ─────────────────────────────────────────────────────────── */

type SupportThread = {
  id: string
  subject: string
  status: string
  priority: string
  created_at: string | null
  updated_at: string | null
}

type SupportMessage = {
  id: string
  sender_role: string
  content: string
  created_at: string | null
}

/* ─── Component ─────────────────────────────────────────────────────── */

export function SupportTab() {
  const [threads, setThreads] = useState<SupportThread[]>([])
  const [activeThread, setActiveThread] = useState<SupportThread | null>(null)
  const [messages, setMessages] = useState<SupportMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [composing, setComposing] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const toast = useToast()

  const loadThreads = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/api/support/threads'), { credentials: 'include' })
      const data = await res.json().catch(() => ({}))
      if (data?.threads) setThreads(data.threads)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadThreads()
  }, [loadThreads])

  const openThread = async (thread: SupportThread) => {
    setActiveThread(thread)
    try {
      const res = await fetch(apiUrl(`/api/support/threads/${thread.id}`), { credentials: 'include' })
      const data = await res.json().catch(() => ({}))
      if (data?.messages) setMessages(data.messages)
    } catch {
      toast.error('Failed to load messages')
    }
  }

  const createThread = async () => {
    if (!subject.trim() || !body.trim()) return
    setSending(true)
    try {
      const res = await fetch(apiUrl('/api/support/threads'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ subject: subject.trim(), message: body.trim() }),
      })
      if (!res.ok) throw new Error('Failed to create thread')
      toast.success('Message sent', 'Our team will respond shortly.')
      setSubject('')
      setBody('')
      setComposing(false)
      await loadThreads()
    } catch {
      toast.error('Failed to send message')
    } finally {
      setSending(false)
    }
  }

  const sendReply = async () => {
    if (!reply.trim() || !activeThread) return
    setSending(true)
    try {
      const res = await fetch(apiUrl(`/api/support/threads/${activeThread.id}/reply`), {
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

  /* ── Thread detail view ── */
  if (activeThread) {
    return (
      <div className='flex h-full flex-col'>
        <button
          type='button'
          onClick={() => setActiveThread(null)}
          className='mb-4 flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200'
        >
          {Icons.back({ className: 'h-3.5 w-3.5' })}
          <span>Back to threads</span>
        </button>

        <div className='mb-4'>
          <h3 className='text-sm font-semibold text-white'>{activeThread.subject}</h3>
          <p className='mt-0.5 text-[11px] text-zinc-500'>
            Status: <span className={activeThread.status === 'open' ? 'text-cyan-300' : 'text-zinc-400'}>{activeThread.status}</span>
          </p>
        </div>

        <div className='min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-[#2a2a2a] bg-[#0f0f0f] p-4'>
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                msg.sender_role === 'user'
                  ? 'ml-auto bg-blue-600/20 text-zinc-100'
                  : msg.sender_role === 'admin'
                    ? 'bg-[#1a1a1a] text-zinc-200'
                    : 'bg-zinc-800/50 text-zinc-400 italic'
              }`}
            >
              <p className='mb-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-500'>
                {msg.sender_role === 'user' ? 'You' : msg.sender_role === 'admin' ? 'Support' : 'System'}
              </p>
              <p className='whitespace-pre-wrap'>{msg.content}</p>
              {msg.created_at && (
                <p className='mt-1 text-[10px] text-zinc-600'>
                  {new Date(msg.created_at).toLocaleString()}
                </p>
              )}
            </div>
          ))}
          {!messages.length && <p className='text-center text-xs text-zinc-500'>No messages yet</p>}
        </div>

        <div className='mt-3 flex gap-2'>
          <input
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendReply()}
            placeholder='Type a reply...'
            className='flex-1 rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm'
          />
          <button
            type='button'
            onClick={sendReply}
            disabled={sending || !reply.trim()}
            className='rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium hover:bg-blue-500 disabled:opacity-50'
          >
            Send
          </button>
        </div>
      </div>
    )
  }

  /* ── New thread compose ── */
  if (composing) {
    return (
      <div className='space-y-4'>
        <button
          type='button'
          onClick={() => setComposing(false)}
          className='flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200'
        >
          {Icons.back({ className: 'h-3.5 w-3.5' })}
          <span>Back</span>
        </button>
        <h3 className='text-sm font-semibold text-white'>New support message</h3>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder='Subject'
          className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm'
        />
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder='Describe your question or issue...'
          rows={6}
          className='w-full rounded-lg border border-[#2a2a2a] bg-[#111] px-3 py-2 text-sm'
        />
        <button
          type='button'
          onClick={createThread}
          disabled={sending || !subject.trim() || !body.trim()}
          className='w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-medium hover:bg-blue-500 disabled:opacity-50'
        >
          {sending ? 'Sending...' : 'Send message'}
        </button>
      </div>
    )
  }

  /* ── Thread list ── */
  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <div>
          <h3 className='text-sm font-semibold text-white'>Support</h3>
          <p className='mt-0.5 text-xs text-zinc-400'>Talk to our team — we typically respond within a few hours.</p>
        </div>
        <button
          type='button'
          onClick={() => setComposing(true)}
          className='rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium hover:bg-blue-500'
        >
          New message
        </button>
      </div>

      {loading && <p className='text-xs text-zinc-500'>Loading...</p>}

      {!loading && !threads.length && (
        <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-6 text-center'>
          <p className='text-sm text-zinc-400'>No conversations yet.</p>
          <p className='mt-1 text-xs text-zinc-500'>Start a new message to reach our support team.</p>
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
              <p className='text-sm font-medium text-white'>{thread.subject}</p>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${
                  thread.status === 'open'
                    ? 'bg-cyan-500/10 text-cyan-300'
                    : thread.status === 'resolved'
                      ? 'bg-emerald-500/10 text-emerald-300'
                      : 'bg-zinc-500/10 text-zinc-400'
                }`}
              >
                {thread.status}
              </span>
            </div>
            {thread.updated_at && (
              <p className='mt-1 text-[11px] text-zinc-500'>
                Updated {new Date(thread.updated_at).toLocaleDateString()}
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
