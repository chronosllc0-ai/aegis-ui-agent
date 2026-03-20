import { useCallback, useEffect, useState, useMemo } from 'react'
import type { ReactNode } from 'react'
import { ToastContext } from '../hooks/useToast'
import type { ToastItem, ToastVariant } from '../hooks/useToast'



/* ─── Icons (inline SVG) ────────────────────────────────────────────── */

const ICONS: Record<ToastVariant, ReactNode> = {
  success: (
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='currentColor' className='h-5 w-5 text-emerald-400'>
      <path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z' clipRule='evenodd' />
    </svg>
  ),
  error: (
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='currentColor' className='h-5 w-5 text-red-400'>
      <path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z' clipRule='evenodd' />
    </svg>
  ),
  warning: (
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='currentColor' className='h-5 w-5 text-amber-400'>
      <path fillRule='evenodd' d='M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z' clipRule='evenodd' />
    </svg>
  ),
  info: (
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='currentColor' className='h-5 w-5 text-cyan-400'>
      <path fillRule='evenodd' d='M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z' clipRule='evenodd' />
    </svg>
  ),
}

const BORDER_COLORS: Record<ToastVariant, string> = {
  success: 'border-emerald-500/30',
  error: 'border-red-500/30',
  warning: 'border-amber-500/30',
  info: 'border-cyan-500/30',
}

/* ─── Individual Toast Card ─────────────────────────────────────────── */

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const showTimer = window.setTimeout(() => setVisible(true), 10)
    const hideTimer = window.setTimeout(() => {
      setVisible(false)
      window.setTimeout(() => onDismiss(item.id), 300)
    }, item.duration ?? 4000)
    return () => {
      window.clearTimeout(showTimer)
      window.clearTimeout(hideTimer)
    }
  }, [item.id, item.duration, onDismiss])

  return (
    <div
      className={`pointer-events-auto flex w-80 items-start gap-3 rounded-xl border bg-[#1a1a1a] px-4 py-3 shadow-xl transition-all duration-300 ${BORDER_COLORS[item.variant]} ${
        visible ? 'translate-x-0 opacity-100' : 'translate-x-8 opacity-0'
      }`}
    >
      <span className='mt-0.5 shrink-0'>{ICONS[item.variant]}</span>
      <div className='min-w-0 flex-1'>
        <p className='text-sm font-medium text-white'>{item.title}</p>
        {item.message && <p className='mt-0.5 text-xs text-zinc-400'>{item.message}</p>}
      </div>
      <button
        type='button'
        onClick={() => {
          setVisible(false)
          window.setTimeout(() => onDismiss(item.id), 300)
        }}
        className='shrink-0 text-zinc-500 transition hover:text-zinc-300'
        aria-label='Dismiss'
      >
        <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='currentColor' className='h-4 w-4'>
          <path d='M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z' />
        </svg>
      </button>
    </div>
  )
}

/* ─── Toast Provider ────────────────────────────────────────────────── */

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback((item: Omit<ToastItem, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    setToasts((prev) => [...prev, { ...item, id }])
  }, [])

  const value = useMemo(
    () => ({
      toast: addToast,
      success: (title: string, message?: string) => addToast({ variant: 'success' as const, title, message }),
      error: (title: string, message?: string) => addToast({ variant: 'error' as const, title, message }),
      info: (title: string, message?: string) => addToast({ variant: 'info' as const, title, message }),
      warning: (title: string, message?: string) => addToast({ variant: 'warning' as const, title, message }),
    }),
    [addToast],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className='pointer-events-none fixed right-4 top-4 z-[9999] flex flex-col gap-2'>
        {toasts.map((t) => (
          <ToastCard key={t.id} item={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
