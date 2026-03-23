import { useEffect, useRef, useState } from 'react'
import { useNotifications, type Notification, type NotifType } from '../context/NotificationContext'

function timeAgo(date: Date): string {
  const secs = Math.floor((Date.now() - date.getTime()) / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const TYPE_STYLES: Record<NotifType, { dot: string; icon: string }> = {
  error:   { dot: 'bg-red-500',    icon: '✕' },
  warning: { dot: 'bg-yellow-400', icon: '!' },
  info:    { dot: 'bg-blue-400',   icon: 'i' },
  success: { dot: 'bg-emerald-400',icon: '✓' },
}

function NotifRow({ n, onRead }: { n: Notification; onRead: (id: string) => void }) {
  const s = TYPE_STYLES[n.type]
  return (
    <button
      type='button'
      onClick={() => onRead(n.id)}
      className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-zinc-800 ${n.read ? 'opacity-60' : ''}`}
    >
      <div className='flex items-start gap-2.5'>
        <span className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white ${s.dot}`}>
          {s.icon}
        </span>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center justify-between gap-1'>
            <span className={`truncate text-xs font-medium ${n.read ? 'text-zinc-400' : 'text-zinc-100'}`}>{n.title}</span>
            {!n.read && <span className='h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400' />}
          </div>
          {n.message && <p className='mt-0.5 text-[11px] leading-relaxed text-zinc-500 line-clamp-2'>{n.message}</p>}
          <span className='mt-1 block text-[10px] text-zinc-600'>{timeAgo(n.timestamp)}</span>
        </div>
      </div>
    </button>
  )
}

export function NotificationBell() {
  const { notifications, unreadCount, markRead, markAllRead, clearAll } = useNotifications()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Mark all read when opening
  const toggle = () => {
    setOpen((v) => {
      if (!v && unreadCount > 0) markAllRead()
      return !v
    })
  }

  return (
    <div ref={ref} className='relative'>
      {/* Bell button */}
      <button
        type='button'
        onClick={toggle}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        className='relative rounded-md border border-[#2a2a2a] p-1.5 hover:bg-zinc-800 transition-colors'
      >
        <svg
          className='h-4 w-4 text-zinc-300'
          viewBox='0 0 24 24'
          fill='none'
          stroke='currentColor'
          strokeWidth={2}
          strokeLinecap='round'
          strokeLinejoin='round'
        >
          <path d='M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9' />
          <path d='M13.73 21a2 2 0 0 1-3.46 0' />
        </svg>
        {unreadCount > 0 && (
          <span className='absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white'>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className='absolute right-0 top-full z-50 mt-2 w-80 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] shadow-2xl'>
          {/* Header */}
          <div className='flex items-center justify-between border-b border-[#2a2a2a] px-3 py-2'>
            <span className='text-xs font-semibold text-zinc-200'>Notifications</span>
            {notifications.length > 0 && (
              <button
                type='button'
                onClick={clearAll}
                className='text-[10px] text-zinc-500 hover:text-zinc-300'
              >
                Clear all
              </button>
            )}
          </div>

          {/* List */}
          <div className='max-h-80 overflow-y-auto p-1.5'>
            {notifications.length === 0 ? (
              <div className='py-8 text-center'>
                <svg className='mx-auto mb-2 h-8 w-8 text-zinc-700' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth={1.5}>
                  <path strokeLinecap='round' strokeLinejoin='round' d='M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9' />
                  <path strokeLinecap='round' strokeLinejoin='round' d='M13.73 21a2 2 0 0 1-3.46 0' />
                </svg>
                <p className='text-xs text-zinc-500'>No notifications yet</p>
              </div>
            ) : (
              <div className='space-y-0.5'>
                {notifications.map((n) => (
                  <NotifRow key={n.id} n={n} onRead={markRead} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
