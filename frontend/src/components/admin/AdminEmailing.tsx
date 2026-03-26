import { useCallback, useEffect, useRef, useState } from 'react'
import { LuLoader, LuZap, LuCalendar, LuChartBar, LuAtSign } from 'react-icons/lu'
import { useToast } from '../../hooks/useToast'
import { apiUrl } from '../../lib/api'

// ── Types ────────────────────────────────────────────────────────────────

type UserResult = {
  uid: string
  name: string | null
  email: string | null
  avatar_url: string | null
  plan?: string | null
}

// ── Helpers ───────────────────────────────────────────────────────────────

function SpinnerIcon({ className }: { className?: string }) {
  return <LuLoader className={`animate-spin ${className ?? 'h-4 w-4'}`} />
}

function Avatar({ user }: { user: UserResult }) {
  if (user.avatar_url) {
    return <img src={user.avatar_url} alt='' className='h-7 w-7 rounded-full object-cover' />
  }
  const initial = (user.name?.[0] || user.email?.[0] || '?').toUpperCase()
  return (
    <span className='flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-[11px] font-bold text-zinc-200'>
      {initial}
    </span>
  )
}

// ── Component ─────────────────────────────────────────────────────────────

export function AdminEmailing() {
  // Recipient state
  const [sendToAll, setSendToAll] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<UserResult[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserResult | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)

  // From field state
  const [fromName, setFromName] = useState('')
  const [fromUsername, setFromUsername] = useState('')

  // Email state
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [sending, setSending] = useState(false)
  const [sentResult, setSentResult] = useState<{ sent: number; failed: number } | null>(null)

  const searchRef = useRef<HTMLDivElement>(null)
  const toast = useToast()

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Debounced search
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchResults([])
      setShowDropdown(false)
      return
    }
    setSearchLoading(true)
    try {
      const res = await fetch(
        apiUrl(`/api/admin/users/?search=${encodeURIComponent(q)}&limit=10`),
        { credentials: 'include' },
      )
      if (res.ok) {
        const data = (await res.json()) as { users: UserResult[] }
        setSearchResults(data.users ?? [])
        setShowDropdown(true)
      }
    } catch {
      // ignore
    } finally {
      setSearchLoading(false)
    }
  }, [])

  useEffect(() => {
    if (sendToAll) return
    const t = setTimeout(() => void doSearch(searchQuery), 300)
    return () => clearTimeout(t)
  }, [searchQuery, sendToAll, doSearch])

  const selectUser = (user: UserResult) => {
    setSelectedUser(user)
    setSearchQuery(user.name || user.email || user.uid)
    setShowDropdown(false)
    setSearchResults([])
  }

  const clearRecipient = () => {
    setSelectedUser(null)
    setSearchQuery('')
    setSendToAll(false)
  }

  // Sanitize username — lowercase, alphanumeric + dots/hyphens/underscores
  const safeUsername = fromUsername.toLowerCase().replace(/[^a-z0-9._-]/g, '')
  const fromAddress = safeUsername
    ? fromName.trim()
      ? `${fromName.trim()} <${safeUsername}@mohex.org>`
      : `${safeUsername}@mohex.org`
    : ''

  const canSend = (sendToAll || selectedUser !== null) && subject.trim() && body.trim() && !sending

  const handleSend = async () => {
    if (!canSend) return
    setSending(true)
    setSentResult(null)
    try {
      const res = await fetch(apiUrl('/api/admin/email/send'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_ids: sendToAll ? 'all' : [selectedUser!.uid],
          subject: subject.trim(),
          body: body.trim(),
          from_address: fromAddress || undefined,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? `Server error (${res.status})`)
      }
      const result = (await res.json()) as { sent: number; failed: number }
      setSentResult(result)
      if (result.sent > 0) {
        toast.success(
          'Email sent',
          `Delivered to ${result.sent} recipient${result.sent !== 1 ? 's' : ''}${result.failed ? ` (${result.failed} failed)` : ''}.`,
        )
        // Reset form only on success
        setSubject('')
        setBody('')
        clearRecipient()
      } else {
        toast.error('Email not delivered', `${result.failed} failed to send. Check Railway logs for details.`)
      }
    } catch (err) {
      toast.error('Send failed', err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className='space-y-6 max-w-2xl'>

      {/* Header */}
      <div>
        <h2 className='text-lg font-semibold text-white'>Email Users</h2>
        <p className='mt-0.5 text-xs text-zinc-400'>
          Send an email directly to a specific user or broadcast to all users.
        </p>
      </div>

      {/* Last send result */}
      {sentResult && (
        <div className='flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/8 px-4 py-3'>
          <LuZap className='h-4 w-4 shrink-0 text-emerald-400' />
          <p className='text-sm text-emerald-300'>
            Sent to <strong>{sentResult.sent}</strong> recipient{sentResult.sent !== 1 ? 's' : ''}
            {sentResult.failed > 0 && (
              <span className='text-amber-400'> · {sentResult.failed} failed</span>
            )}
          </p>
        </div>
      )}

      {/* From */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5 space-y-4'>
        <p className='text-xs font-semibold uppercase tracking-wider text-zinc-500'>From</p>

        <div className='flex gap-3'>
          {/* Display name */}
          <div className='flex-1 space-y-1'>
            <label className='text-xs text-zinc-400'>Display name</label>
            <input
              type='text'
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder='e.g. Jesse'
              className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-500 transition'
            />
          </div>

          {/* Username prefix */}
          <div className='flex-1 space-y-1'>
            <label className='text-xs text-zinc-400'>Username</label>
            <div className='flex items-center gap-1.5 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2.5 focus-within:border-zinc-500 transition'>
              <LuAtSign className='h-3.5 w-3.5 shrink-0 text-zinc-500' />
              <input
                type='text'
                value={fromUsername}
                onChange={(e) => setFromUsername(e.target.value)}
                placeholder='hello'
                className='min-w-0 flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 outline-none'
              />
              <span className='shrink-0 text-[11px] text-zinc-600'>@mohex.org</span>
            </div>
          </div>
        </div>

        {/* Preview */}
        <div className='flex items-center gap-2 rounded-lg bg-[#0f0f0f] border border-[#1a1a1a] px-3 py-2'>
          <span className='text-[11px] text-zinc-500'>Sends as:</span>
          <span className='text-[12px] text-zinc-300 font-mono'>
            {fromAddress
              ? fromAddress
              : <span className='text-zinc-600 italic'>fill in username above</span>}
          </span>
        </div>
      </div>

      {/* Recipient */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5 space-y-4'>
        <p className='text-xs font-semibold uppercase tracking-wider text-zinc-500'>Recipient</p>

        {/* Send to all toggle */}
        <button
          type='button'
          onClick={() => {
            setSendToAll((v) => !v)
            if (!sendToAll) {
              setSelectedUser(null)
              setSearchQuery('')
            }
          }}
          className={`flex w-full items-center justify-between rounded-lg border px-4 py-3 text-sm transition ${
            sendToAll
              ? 'border-cyan-500/50 bg-cyan-500/8 text-cyan-300'
              : 'border-[#2a2a2a] text-zinc-400 hover:border-zinc-600'
          }`}
        >
          <span className='font-medium'>Send to all users</span>
          <div className={`relative h-5 w-9 rounded-full transition-colors ${sendToAll ? 'bg-cyan-600' : 'bg-zinc-700'}`}>
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                sendToAll ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </div>
        </button>

        {/* Or search */}
        {!sendToAll && (
          <div ref={searchRef} className='relative'>
            <div className='flex items-center gap-2 rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2.5 focus-within:border-zinc-500'>
              {searchLoading ? (
                <SpinnerIcon className='h-3.5 w-3.5 shrink-0 text-zinc-500' />
              ) : (
                <LuChartBar className='h-3.5 w-3.5 shrink-0 text-zinc-500' />
              )}
              <input
                type='text'
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  if (selectedUser) setSelectedUser(null)
                }}
                onFocus={() => { if (searchResults.length > 0) setShowDropdown(true) }}
                placeholder='Search user by name or email…'
                className='flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 outline-none'
              />
              {(searchQuery || selectedUser) && (
                <button
                  type='button'
                  onClick={clearRecipient}
                  className='text-zinc-600 hover:text-zinc-400 text-xs'
                >
                  ✕
                </button>
              )}
            </div>

            {/* Dropdown */}
            {showDropdown && searchResults.length > 0 && (
              <div className='absolute left-0 right-0 z-20 mt-1.5 rounded-xl border border-[#2a2a2a] bg-[#111] shadow-xl overflow-hidden'>
                {searchResults.map((user) => (
                  <button
                    key={user.uid}
                    type='button'
                    onClick={() => selectUser(user)}
                    className='flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-white/[0.04] transition'
                  >
                    <Avatar user={user} />
                    <div className='min-w-0 flex-1'>
                      <p className='truncate text-sm font-medium text-zinc-200'>
                        {user.name || '(no name)'}
                      </p>
                      <p className='truncate text-[11px] text-zinc-500'>{user.email}</p>
                    </div>
                    {user.plan && (
                      <span className='rounded-full bg-zinc-700/60 px-2 py-0.5 text-[10px] capitalize text-zinc-400'>
                        {user.plan}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {showDropdown && !searchLoading && searchResults.length === 0 && searchQuery.trim() && (
              <div className='absolute left-0 right-0 z-20 mt-1.5 rounded-xl border border-[#2a2a2a] bg-[#111] px-4 py-3 text-xs text-zinc-500'>
                No users found matching "{searchQuery}"
              </div>
            )}

            {/* Selected user chip */}
            {selectedUser && (
              <div className='mt-2 flex items-center gap-2 rounded-lg border border-cyan-500/30 bg-cyan-500/8 px-3 py-2'>
                <Avatar user={selectedUser} />
                <div className='min-w-0 flex-1'>
                  <p className='truncate text-sm font-medium text-cyan-200'>
                    {selectedUser.name || selectedUser.email}
                  </p>
                  {selectedUser.name && (
                    <p className='truncate text-[11px] text-zinc-500'>{selectedUser.email}</p>
                  )}
                </div>
                <button
                  type='button'
                  onClick={clearRecipient}
                  className='text-zinc-600 hover:text-zinc-400 text-xs'
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Compose */}
      <div className='rounded-xl border border-[#2a2a2a] bg-[#111] p-5 space-y-4'>
        <p className='text-xs font-semibold uppercase tracking-wider text-zinc-500'>Compose</p>

        {/* Subject */}
        <div className='space-y-1.5'>
          <label className='text-xs text-zinc-400'>Subject</label>
          <input
            type='text'
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder='Enter email subject…'
            className='w-full rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-500 transition'
          />
        </div>

        {/* Body */}
        <div className='space-y-1.5'>
          <label className='text-xs text-zinc-400'>Message</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder='Write your message here. Plain text is fine — it will be wrapped in the Aegis branded email template.'
            rows={7}
            className='w-full resize-none rounded-lg border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-500 transition'
          />
          <p className='text-[11px] text-zinc-600'>
            Plain text is automatically styled with the Aegis email template.
          </p>
        </div>
      </div>

      {/* Send button */}
      <button
        type='button'
        onClick={() => void handleSend()}
        disabled={!canSend}
        className='flex w-full items-center justify-center gap-2 rounded-full bg-cyan-500 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40'
      >
        {sending ? (
          <>
            <SpinnerIcon className='h-4 w-4' />
            Sending…
          </>
        ) : (
          <>
            <LuCalendar className='h-4 w-4' />
            {sendToAll ? 'Send to all users' : selectedUser ? `Send to ${selectedUser.name || selectedUser.email}` : 'Send email'}
          </>
        )}
      </button>

      <p className='text-center text-[11px] text-zinc-600'>
        Emails are sent via Resend using the Aegis branded template from your chosen @mohex.org address
      </p>
    </div>
  )
}
