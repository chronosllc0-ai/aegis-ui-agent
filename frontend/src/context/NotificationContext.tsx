import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

export type NotifType = 'error' | 'warning' | 'info' | 'success'

export interface Notification {
  id: string
  type: NotifType
  title: string
  message?: string
  timestamp: Date
  read: boolean
  source?: string // 'websocket' | 'credit' | 'api_key' | 'system'
}

interface NotificationContextValue {
  notifications: Notification[]
  unreadCount: number
  addNotification: (n: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void
  markRead: (id: string) => void
  markAllRead: () => void
  clearAll: () => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

const MAX_NOTIFICATIONS = 50

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const idRef = useRef(0)

  const addNotification = useCallback((n: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
    setNotifications((prev) => {
      const next: Notification = { ...n, id: String(++idRef.current), timestamp: new Date(), read: false }
      return [next, ...prev].slice(0, MAX_NOTIFICATIONS)
    })
  }, [])

  const markRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }, [])

  const clearAll = useCallback(() => setNotifications([]), [])

  const unreadCount = notifications.filter((n) => !n.read).length

  return (
    <NotificationContext.Provider value={{ notifications, unreadCount, addNotification, markRead, markAllRead, clearAll }}>
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotifications must be used within <NotificationProvider>')
  return ctx
}
